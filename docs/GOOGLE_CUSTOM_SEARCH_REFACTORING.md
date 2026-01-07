# Google Custom Search Refactoring Plan

## Overview

This document outlines the refactoring plan to integrate Google Custom Search API while maintaining clean architecture and backward compatibility. The main challenge is that Google Custom Search uses a REST API instead of browser-based scraping, requiring a different implementation approach.

## Current Architecture Analysis

### BasePlatformSearcher Interface

The current `BasePlatformSearcher` abstract class has these abstract methods:

1. `_load_config()`: Load platform configuration
2. `search()`: Execute search
3. `_extract_item()`: Extract single result from DOM element

**Problem**: `_extract_item()` is designed for DOM parsing (browser-based), but API-based search returns JSON directly.

### Current Implementation Pattern

**Browser-based searchers** (Weixin, Zhihu):
```python
async def search(self, query, max_results):
    # 1. Navigate to search page
    # 2. Wait for results to load
    # 3. Parse DOM using selectors
    # 4. Extract items using _extract_item()
    # 5. Return results
```

**API-based searchers** (Google):
```python
async def search(self, query, max_results):
    # 1. Make API request
    # 2. Parse JSON response
    # 3. Transform to standard format
    # 4. Return results (no DOM parsing needed)
```

## Refactoring Options

### Option 1: Keep Current Interface (Recommended)

**Approach**: Make `_extract_item()` optional or provide default implementation.

**Pros**:
- Minimal changes to existing code
- Backward compatible
- Simple implementation

**Cons**:
- `_extract_item()` is not semantically correct for API-based searchers
- Slight interface pollution

**Implementation**:

1. **Modify BasePlatformSearcher**:
   ```python
   class BasePlatformSearcher(ABC):
       # ... existing code ...
       
       async def _extract_item(self, element: ElementHandle, index: int) -> Optional[Dict[str, str]]:
           """
           Extract a single result item from DOM element.
           
           Default implementation returns None.
           Browser-based searchers should override this method.
           API-based searchers can ignore this method.
           
           Args:
               element: Playwright ElementHandle (not used for API-based)
               index: Index of the element (not used for API-based)
           
           Returns:
               Dictionary containing result item data, or None
           """
           return None
   ```

2. **GoogleSearcher Implementation**:
   ```python
   class GoogleSearcher(BasePlatformSearcher):
       # _extract_item() not overridden (uses default None implementation)
       # search() directly transforms API JSON response
   ```

**Changes Required**:
- Modify `BasePlatformSearcher._extract_item()` to have default implementation
- Remove `@abstractmethod` decorator (make it optional)
- Update docstring to clarify usage

### Option 2: Create Separate Base Classes

**Approach**: Create `BrowserBasedSearcher` and `APIBasedSearcher` base classes.

**Pros**:
- Clear separation of concerns
- Type safety
- Better semantic correctness

**Cons**:
- More complex inheritance hierarchy
- Requires refactoring existing searchers
- More code to maintain

**Implementation**:

```python
class BasePlatformSearcher(ABC):
    """Base class with common functionality."""
    # Common methods only
    
class BrowserBasedSearcher(BasePlatformSearcher):
    """Base class for browser-based searchers."""
    @abstractmethod
    async def _extract_item(self, element, index):
        pass
    
class APIBasedSearcher(BasePlatformSearcher):
    """Base class for API-based searchers."""
    @abstractmethod
    async def _transform_api_response(self, api_response):
        pass
```

**Changes Required**:
- Refactor `WeixinSearcher` and `ZhihuSearcher` to inherit from `BrowserBasedSearcher`
- Create `GoogleSearcher` inheriting from `APIBasedSearcher`
- Update type hints throughout codebase

### Option 3: Use Composition Pattern

**Approach**: Separate search strategy from searcher class.

**Pros**:
- Very flexible
- Easy to add new search strategies
- Clean separation

**Cons**:
- Major architectural change
- Requires significant refactoring
- Over-engineered for current needs

## Recommended Approach: Option 1

**Rationale**:
- Minimal changes required
- Maintains backward compatibility
- Simple and pragmatic
- Easy to understand and maintain

## Detailed Refactoring Steps

### Step 1: Modify BasePlatformSearcher

**File**: `core/base_searcher.py`

**Changes**:

1. Remove `@abstractmethod` from `_extract_item()`
2. Add default implementation that returns `None`
3. Update docstring to clarify that API-based searchers can ignore this

**Code**:

```python
# Before:
@abstractmethod
async def _extract_item(self, element: ElementHandle, index: int) -> Optional[Dict[str, str]]:
    """Extract a single result item from DOM element."""
    pass

# After:
async def _extract_item(self, element: ElementHandle, index: int) -> Optional[Dict[str, str]]:
    """
    Extract a single result item from DOM element.
    
    This method is used by browser-based searchers to extract results from DOM.
    API-based searchers should override this to return None (default implementation).
    
    Args:
        element: Playwright ElementHandle representing a search result
        index: Index of the element in the results list
    
    Returns:
        Dictionary containing result item data, or None if not applicable
    """
    return None
```

**Impact**: 
- No breaking changes (existing searchers already implement this)
- New API-based searchers can use default implementation

### Step 2: Create GoogleSearcher

**File**: `platforms/google_searcher.py` (new file)

**Implementation**:

```python
class GoogleSearcher(BasePlatformSearcher):
    def __init__(self, browser_pool: BrowserPool):
        super().__init__(browser_pool)
        self.config = self._load_config()
        self.api_key = os.getenv("APIKEY_GOOGLE_CUSTOM_SEARCH")
        self.search_engine_id = os.getenv("APIKEY_GOOGLE_SEARCH_ID")
    
    def _load_config(self) -> Dict[str, Any]:
        # Load from platforms.yaml
        ...
    
    async def search(self, query: str, max_results: int = 10, **kwargs: Any) -> List[Dict[str, str]]:
        # 1. Validate API credentials
        # 2. Sanitize query
        # 3. Make paginated API requests (start=1, 11, 21, ...)
        # 4. Transform JSON response to standard format
        # 5. Return results
        ...
    
    # _extract_item() not overridden - uses default None implementation
```

**Key Implementation Details**:

1. **API Request Parameters**:
   - Base URL: `https://www.googleapis.com/customsearch/v1`
   - Parameters: `key`, `cx`, `q`, `num=10`, `start` (1, 11, 21, ...)
   - For max_results=30, make 3 requests with start=1, 11, 21

2. **Result Format Transformation**:
   ```python
   {
       "title": item["title"],
       "url": item["link"],
       "source": "Google",  # or from config metadata.display_name
       "snippet": item.get("snippet", ""),
       "date": item.get("pagemap", {}).get("metatags", [{}])[0].get("article:published_time", "")
   }
   ```

3. **Error Handling**:
   - Missing credentials: Log warning, return []
   - 429 (Rate Limit): Exponential backoff retry (max 3), return partial results
   - 400 (Invalid Query): Log error, return []
   - 401 (Invalid Credentials): Log error, return []
   - Network errors: Exponential backoff retry (max 3), return partial results

**Key Points**:
- Inherits from `BasePlatformSearcher`
- Implements `search()` with API calls using `httpx`
- Does NOT override `_extract_item()` (uses default)
- Still uses `browser_pool` for content fetching (via ContentProcessor)

### Step 3: Update Configuration

**File**: `config/platforms.yaml`

**Add**:
```yaml
google:
  # ... (as described in design doc)
```

**File**: `config/anti_crawler.yaml`

**Add**:
```yaml
google:
  rate_limit:
    requests_per_minute: 10
    requests_per_hour: 100
  delay:
    min_seconds: 1.0
    max_seconds: 3.0
```

### Step 4: Update MCP Server

**File**: `mcp_server.py`

**Changes**:

1. Import GoogleSearcher at the top:
   ```python
   from platforms.google_searcher import GoogleSearcher
   ```

2. Register platform in `start()` method:
   ```python
   async def start(self) -> None:
       self.manager = UnifiedSearchManager()
       
       # Register existing platforms
       self.manager.register_platform("weixin", WeixinSearcher(self.manager.browser_pool))
       
       # Register Google (if credentials available)
       google_api_key = os.getenv("APIKEY_GOOGLE_CUSTOM_SEARCH")
       google_search_id = os.getenv("APIKEY_GOOGLE_SEARCH_ID")
       if google_api_key and google_search_id:
           self.manager.register_platform("google", GoogleSearcher(self.manager.browser_pool))
           self.logger.info("Google Custom Search platform registered")
       else:
           self.logger.warning(
               "Google Custom Search not available: "
               "APIKEY_GOOGLE_CUSTOM_SEARCH or APIKEY_GOOGLE_SEARCH_ID not set"
           )
   ```

3. Update tool schema to include "google" in platform enum:
   ```python
   "platform": {
       "type": "string",
       "enum": ["weixin", "google"],  # Add "google"
       "description": "Platform to search (weixin, google). Note: zhihu is disabled by default due to anti-crawler measures."
   }
   ```

### Step 5: Update Platforms Module (if needed)

**File**: `platforms/__init__.py`

**Check if file exists and is used for exports**:
- If the file exists and exports searchers, add:
  ```python
  from .google_searcher import GoogleSearcher
  ```
- If the file doesn't exist or doesn't export searchers, skip this step

### Step 6: Verify Dependencies

**File**: `requirements.txt`

**Status**: 
- `httpx[socks]>=0.28.0` is already present (used by ContentCompressor)
- No new dependencies needed

**Note**: 
- `httpx` is already used in the codebase for DeepSeek API calls
- We can reuse the same library for Google Custom Search API calls
- No additional installation required

### Step 7: Testing Updates

**No changes needed to existing tests**:
- Existing tests for `BasePlatformSearcher` should still pass
- New tests for `GoogleSearcher` will be added separately

**New test file**: `tests/unit/test_google_searcher.py`

**Note**: For initial implementation, tests are **not required**. However, code should be designed to be testable:
- Use dependency injection
- Separate API call logic from business logic
- Design for easy mocking

Tests will be added in a later phase.

## Backward Compatibility

### Existing Code Impact

**No breaking changes**:
- `WeixinSearcher` and `ZhihuSearcher` continue to work as before
- They already implement `_extract_item()`, so no changes needed
- `BasePlatformSearcher` changes are backward compatible

### API Compatibility

**UnifiedSearchManager**:
- No changes needed
- Works with any `BasePlatformSearcher` subclass
- Content processing works the same way

**ContentProcessor**:
- No changes needed
- Works with any platform that returns URLs
- Content selectors configured per platform in `platforms.yaml`

## Migration Path

### Phase 1: Preparation (No Code Changes)
1. Review design document
2. Set up Google Custom Search API credentials
3. Test API manually to understand response format

### Phase 2: Core Implementation
1. Modify `BasePlatformSearcher._extract_item()` (Step 1)
2. Create `GoogleSearcher` class (Step 2)
3. Add configuration (Step 3)

### Phase 3: Integration
4. Update MCP server (Step 4)
5. Add dependencies (Step 5)

### Phase 4: Testing
6. Write unit tests
7. Write integration tests
8. Test end-to-end with MCP client

### Phase 5: Documentation
9. Update README
10. Add usage examples
11. Document environment variables

## Risk Assessment

### Low Risk
- **BasePlatformSearcher changes**: Default implementation is safe, existing code unaffected
- **Configuration additions**: New sections don't affect existing platforms
- **MCP server registration**: Optional feature, graceful degradation if credentials missing

### Medium Risk
- **API rate limiting**: Need to implement proper rate limiting to avoid quota exhaustion
- **Content extraction**: Generic selectors may not work for all domains

### Mitigation
- Implement conservative rate limits
- Add fallback content extraction (body tag)
- Monitor API usage
- Log warnings for failed content extractions

## Alternative Considerations

### If Option 1 Doesn't Work

If we find that making `_extract_item()` optional causes issues, we can:

1. **Quick Fix**: Override `_extract_item()` in `GoogleSearcher` to raise `NotImplementedError` with clear message
2. **Better Fix**: Implement Option 2 (separate base classes) in a future refactoring

### Future Enhancements

After Google integration is stable, consider:

1. **Refactor to Option 2**: Create separate base classes for better type safety
2. **Add Search Strategy Pattern**: If more API-based searchers are added
3. **Domain-Specific Content Selectors**: Improve content extraction accuracy

## Summary

The recommended refactoring approach (Option 1) is:

- **Minimal**: Only one method change in base class
- **Safe**: Fully backward compatible
- **Simple**: Easy to understand and maintain
- **Pragmatic**: Solves the problem without over-engineering

The key insight is that `_extract_item()` is only used by browser-based searchers, so making it optional doesn't break anything. API-based searchers can simply not use it.

## Code Style Requirements

1. **PEP 8 Compliance**: Follow Python PEP 8 style guide
2. **Type Hints**: Use type hints for all function parameters and return types
3. **Docstrings**: Use Google-style docstrings for all classes and methods
4. **Error Handling**: Explicit and meaningful exception handling
5. **Logging**: Use `self.logger` for all logging (info, warning, error, debug)
6. **Naming**: Use meaningful variable and function names

## Implementation Checklist

- [ ] Modify `BasePlatformSearcher._extract_item()` to have default implementation
- [ ] Create `platforms/google_searcher.py` with:
  - [ ] API credential validation
  - [ ] Query sanitization
  - [ ] Pagination logic (start=1, 11, 21)
  - [ ] JSON response transformation
  - [ ] Error handling (429, 400, 401, network errors)
  - [ ] Exponential backoff retry logic
- [ ] Add `google` section to `config/platforms.yaml`
- [ ] Add `google` section to `config/anti_crawler.yaml`
- [ ] Update `mcp_server.py`:
  - [ ] Import `GoogleSearcher`
  - [ ] Register platform with credential check
  - [ ] Update tool schema enum
- [ ] Update `platforms/__init__.py` (if exists and used for exports)
- [x] Verify `httpx` is in `requirements.txt` (already present)
- [ ] Verify code style compliance
- [ ] Verify error handling and logging
- [ ] Manual testing:
  - [ ] Test without credentials (should not crash)
  - [ ] Test with credentials (should register platform)
  - [ ] Test search functionality
  - [ ] Test content fetching
  - [ ] Test error scenarios

**Note**: Unit tests and integration tests will be added in a later phase.

