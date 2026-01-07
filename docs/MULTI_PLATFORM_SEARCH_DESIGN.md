# Multi-Platform Search Design Document

## Overview

This document describes the design for supporting multi-platform search in the Vertical Search MCP server. The feature allows users to search across multiple platforms (weixin, google, etc.) in a single request, with unified progress reporting and result aggregation.

## Goals

1. **Flexible Platform Selection**: Support searching one or multiple platforms with a simple string format
2. **Unified Task Management**: Single task_id for multi-platform searches
3. **Clear Progress Reporting**: Hierarchical progress showing both platform-level and stage-level progress
4. **Result Aggregation**: Combine and deduplicate results from multiple platforms
5. **Backward Compatibility**: Single platform searches continue to work as before

## Design Decisions

### 1. Platform Parameter Format

**Format**: String with flexible syntax
- `"all"` - Search all registered platforms (default)
- `"weixin"` - Search single platform
- `"weixin,google"` - Search multiple platforms (comma-separated)
- `"weixin, google"` - Handles spaces around commas

**Rationale**:
- Simple and intuitive for users
- Easy to parse and validate
- No need for complex JSON structures
- Default "all" makes it easy to search everything

### 2. Task ID Management

**Single Task ID per Search Request**

- One `task_id` is created for the entire search request (whether single or multi-platform)
- All platform progress updates use the same `task_id`
- User queries progress using the same `task_id` throughout
- Final results are aggregated and returned under the same `task_id`

**Rationale**:
- Consistent API: users don't need to manage multiple task_ids
- Simpler client code: one task_id to track
- Unified progress view: see all platforms in one place
- Matches existing single-platform behavior

### 3. Progress Reporting Architecture

**Two-Level Progress Hierarchy**

#### Level 1: Platform Progress
- Shows which platform is currently being searched
- Format: `"Platform X/Y (platform_name): ..."`
- Tracks completion of each platform

#### Level 2: Stage Progress (within each platform)
- Shows current stage within the platform
- Stages: `searching`, `resolving`, `fetching_content`, `compressing`
- Format: `"[platform_name] Stage: message"`

**Progress Calculation**:
```
Overall Progress = (Completed Platforms × 100 + Current Platform Progress) / Total Platforms
```

**Example**:
- 2 platforms, platform 1 completed (100%), platform 2 at 50%
- Overall = (1 × 100 + 50) / 2 = 75%

**Stage Naming**:
- Single platform: `"searching"`, `"resolving"`, etc.
- Multi-platform: `"{platform}_{stage}"` (e.g., `"weixin_searching"`)

### 4. Result Aggregation

**Process**:
1. Collect results from all platforms
2. Mark each result with its source platform (`result['platform'] = 'weixin'`)
3. Deduplicate by URL (keep first occurrence)
4. Limit to `max_results` total
5. Return combined list

**Result Distribution**:
- Results per platform = `max_results // num_platforms`
- Remaining results allocated to last platform
- Example: 30 results, 2 platforms → 15 each
- Example: 31 results, 2 platforms → 15 + 16

### 5. Error Handling

**Per-Platform Error Isolation**:
- If one platform fails, continue with others
- Record failure in `platform_results` dict
- Report failed platforms in final progress message
- Return partial results (from successful platforms)

**Error Reporting**:
- Progress message: `"Platform X/Y (platform_name): Failed: error_message"`
- Final summary: `"Multi-platform search completed: X/Y platforms, Y total results (Z failed)"`

## Implementation Details

### 1. Platform Parsing

```python
def _parse_platforms(self, platform_str: str) -> List[str]:
    """
    Parse platform string into list of platform names.
    
    - "all" -> all registered platforms
    - "weixin" -> ["weixin"]
    - "weixin,google" -> ["weixin", "google"]
    - Handles spaces: "weixin, google" -> ["weixin", "google"]
    """
```

**Validation**:
- Check all requested platforms exist
- Raise ValueError with available platforms if invalid

### 2. Task Creation

```python
# In _handle_start_vertical_search
platform_str = arguments.get("platform", "all")  # Default to "all"
platforms = self._parse_platforms(platform_str)

task_id = await self.task_manager.create_task(
    query=query,
    platform=",".join(platforms),  # Store as comma-separated string
    max_results=max_results,
    include_content=include_content,
)
```

### 3. Progress Callback Wrapper

```python
def create_platform_progress_callback(platform_name: str, platform_index: int):
    """Create progress callback that adds platform context."""
    async def progress_callback(stage: str, message: str, current: int, total: int):
        # Calculate overall progress
        overall_current = platform_index * 100 + int((current / total) * 100)
        overall_total = total_platforms * 100
        
        # Build message with platform prefix
        if total_platforms > 1:
            full_message = f"Platform {platform_index + 1}/{total_platforms} ({platform_name}): {message}"
        else:
            full_message = message
        
        await self.task_manager.update_task_progress(
            task_id=task_id,
            current=overall_current,
            total=overall_total,
            stage=f"{platform_name}_{stage}" if total_platforms > 1 else stage,
            message=full_message,
        )
    return progress_callback
```

### 4. Multi-Platform Search Execution

```python
async def _execute_search_task(
    self,
    task_id: str,
    platforms: List[str],  # List of platforms to search
    query: str,
    max_results: int,
    include_content: bool,
) -> None:
    """Execute search across multiple platforms."""
    total_platforms = len(platforms)
    all_results = []
    
    # Calculate results per platform
    results_per_platform = max_results // total_platforms
    remaining = max_results % total_platforms
    
    # Search each platform sequentially
    for idx, platform_name in enumerate(platforms):
        # Create platform-specific callback
        callback = create_platform_progress_callback(platform_name, idx)
        
        # Calculate results for this platform
        current_max = results_per_platform
        if idx == total_platforms - 1:
            current_max += remaining
        
        # Execute search
        results = await self.manager.search(
            platform=platform_name,
            query=query,
            max_results=current_max,
            progress_callback=callback,
        )
        
        # Mark platform source
        for result in results:
            result['platform'] = platform_name
        
        all_results.extend(results)
    
    # Deduplicate and limit
    final_results = deduplicate_by_url(all_results)[:max_results]
    
    # Update task with final results
    await self.task_manager.update_task_status(
        task_id=task_id,
        status=TaskStatus.COMPLETED,
        results=final_results,
    )
```

## Progress Message Examples

### Single Platform (unchanged)
```
Searching: Found 10 results
Resolving URLs: 8/10 successful (2 failed)
Fetching content for 8 articles...
Compressing article 1/1 (of 8 total results): 'Title'
```

### Multi-Platform
```
Multi-platform search: Starting search on 2 platforms (weixin, google)
Platform 1/2 (weixin): Starting search...
Platform 1/2 (weixin): Searching: Found 10 results
Platform 1/2 (weixin): Resolving URLs: 8/10 successful (2 failed)
Platform 1/2 (weixin): Fetching content for 8 articles...
Platform 1/2 (weixin): Compressing article 1/1 (of 8 total results): 'Title'
Platform 1/2 (weixin): Completed (8 results)
Platform 2/2 (google): Starting search...
Platform 2/2 (google): Searching: Found 10 results
Platform 2/2 (google): Completed (10 results)
Multi-platform search completed: 2/2 platforms, 18 total results
```

## API Changes

### Input Schema

**Before**:
```json
{
  "platform": {
    "type": "string",
    "enum": ["weixin", "google"],
    "required": true
  }
}
```

**After**:
```json
{
  "platform": {
    "type": "string",
    "description": "Platform(s) to search. Options: 'all' (default), 'weixin', 'google', or comma-separated like 'weixin,google'",
    "default": "all"
  }
}
```

**Required Fields**:
- `platform` is no longer required (has default "all")
- Only `query` is required

### Response Format

**Unchanged**: Same task_id and response structure
- Single task_id returned
- Progress updates use same task_id
- Final results include `platform` field in each result

## Backward Compatibility

### Single Platform Searches
- `platform="weixin"` continues to work
- Progress messages unchanged (no platform prefix)
- Behavior identical to before

### Task ID Usage
- Same API: `get_search_status(task_id)`
- Same response format
- No breaking changes

## Testing Strategy

### Unit Tests
1. Platform parsing: "all", single, multiple, with spaces
2. Invalid platform names
3. Progress calculation for multi-platform
4. Result deduplication

### Integration Tests
1. Single platform search (backward compatibility)
2. Multi-platform search (2 platforms)
3. Multi-platform with one failure
4. Progress reporting accuracy
5. Result aggregation and deduplication

### Manual Testing
1. Test "all" default behavior
2. Test single platform
3. Test multiple platforms
4. Test progress reporting in real-time
5. Test error scenarios

## Performance Considerations

### Sequential vs Parallel

**Current Design: Sequential**
- Platforms searched one after another
- Simpler error handling
- Easier progress tracking
- Predictable resource usage

**Future Optimization: Parallel**
- Could search platforms in parallel
- Faster overall completion
- More complex progress tracking
- Higher resource usage

**Decision**: Start with sequential, optimize later if needed

### Result Limits
- `max_results` is total across all platforms
- Distributed evenly (or with remainder to last platform)
- Deduplication may reduce final count

## Error Scenarios

### Invalid Platform Name
- Error: `ValueError` with available platforms
- Response: Error message in MCP response
- Task: Not created

### Platform Search Failure
- Error: Exception during platform search
- Response: Continue with other platforms
- Task: Completed with partial results
- Progress: Reports failure for that platform

### All Platforms Fail
- Error: All platforms fail
- Response: Task status = FAILED
- Results: Empty list
- Error: Aggregated error message

## Future Enhancements

1. **Parallel Platform Search**: Search platforms concurrently
2. **Platform Priority**: Search important platforms first
3. **Smart Deduplication**: Use content similarity, not just URL
4. **Platform-Specific Limits**: Different max_results per platform
5. **Result Ranking**: Merge and rank results across platforms

## Migration Guide

### For Users
- No changes needed for single platform searches
- To search all platforms: omit `platform` parameter or use `"all"`
- To search multiple: use `"weixin,google"` format

### For Developers
- `_execute_search_task` now accepts `platforms: List[str]` instead of `platform: str`
- Progress callbacks need platform context wrapper
- Result aggregation logic added

## Summary

This design provides a flexible, user-friendly way to search across multiple platforms while maintaining backward compatibility and clear progress reporting. The single task_id approach simplifies client code, and the hierarchical progress reporting gives users clear visibility into the search process.

