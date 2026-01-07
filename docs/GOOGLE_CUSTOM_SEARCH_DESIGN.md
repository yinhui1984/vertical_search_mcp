# Google Custom Search Integration Design

## Overview

This document describes the design for integrating Google Custom Search API into the Vertical Search MCP server as a new search platform. Unlike existing platforms (Weixin, Zhihu) that use browser-based scraping, Google Custom Search uses a REST API, requiring a different implementation approach while maintaining compatibility with the existing architecture.

## Requirements

- **API Credentials**: 
  - API Key via environment variable `APIKEY_GOOGLE_CUSTOM_SEARCH`
  - Custom Search Engine ID (cx) via environment variable `APIKEY_GOOGLE_SEARCH_ID`
- **Search Functionality**: Basic search returning structured data compatible with existing result format
- **Maximum Results**: 30 results (Google API limit: 10 per request, requires pagination)
- **Content Fetching**: Default content fetching and compression (same as Weixin searcher)

## Architecture Analysis

### Current Architecture

The existing architecture follows this pattern:

```
MCP Server
  └── UnifiedSearchManager
       ├── Platform Searchers (BasePlatformSearcher)
       │    ├── WeixinSearcher (browser-based)
       │    └── ZhihuSearcher (browser-based)
       ├── ContentProcessor
       │    ├── ContentFetcher (uses browser pool)
       │    ├── ContentCompressor (uses DeepSeek API)
       │    └── TokenEstimator
       └── BrowserPool (Playwright)
```

### Key Components

1. **BasePlatformSearcher**: Abstract base class defining the interface
   - `search()`: Execute search and return results
   - `_extract_item()`: Extract single result from DOM (not applicable for API-based)
   - `_load_config()`: Load platform configuration

2. **UnifiedSearchManager**: Routes requests, manages cache, coordinates content processing
   - `search()`: Main entry point, handles caching, rate limiting, content processing
   - `_process_content()`: Delegates to ContentProcessor

3. **ContentProcessor**: Coordinates content fetching and compression
   - Uses `ContentFetcher` to fetch article content from URLs
   - Uses `ContentCompressor` to compress content if needed
   - Works with any platform that returns URLs

4. **ContentFetcher**: Fetches full article content from URLs
   - Uses browser pool to navigate to URLs
   - Extracts content using platform-specific selectors from `platforms.yaml`
   - Handles anti-crawler detection

### Design Challenges

1. **API vs Browser-based**: Google Custom Search uses REST API, not browser scraping
   - Solution: Implement API-based search in `GoogleSearcher`, but still use browser pool for content fetching
   - `_extract_item()` is not needed (results come as JSON)

2. **Pagination**: Google API returns max 10 results per request, requires multiple requests
   - Solution: Implement pagination logic in `search()` method

3. **Result Format Compatibility**: Google API returns different structure than DOM parsing
   - Solution: Transform Google API response to match existing format:
     ```python
     {
         "title": "...",
         "url": "...",
         "source": "Google",
         "date": "...",  # May not be available
         "snippet": "..."  # Available from API
     }
     ```

4. **Content Selectors**: Need to configure content extraction selectors for Google search results
   - Solution: Add `google` section to `platforms.yaml` with content selectors
   - Since Google returns results from various domains, we need generic selectors or domain-specific ones

## Detailed Design

### 1. GoogleSearcher Implementation

**Location**: `platforms/google_searcher.py`

**Inheritance**: `BasePlatformSearcher`

**Key Differences from Browser-based Searchers**:

1. **No Browser Usage for Search**: Uses `httpx` or `aiohttp` for API calls
2. **No DOM Parsing**: Directly transforms JSON response
3. **Pagination**: Handles multiple API requests (10 results per page)
4. **Still Uses Browser for Content**: Content fetching still uses browser pool via `ContentFetcher`

**Implementation Structure**:

```python
class GoogleSearcher(BasePlatformSearcher):
    def __init__(self, browser_pool: BrowserPool):
        super().__init__(browser_pool)
        self.config = self._load_config()
        self.api_key = os.getenv("APIKEY_GOOGLE_CUSTOM_SEARCH")
        self.search_engine_id = os.getenv("APIKEY_GOOGLE_SEARCH_ID")
        
    async def search(self, query: str, max_results: int = 10, **kwargs):
        # 1. Validate API credentials
        # 2. Sanitize query
        # 3. Make API requests with pagination
        # 4. Transform results to standard format
        # 5. Return results
        
    def _load_config(self):
        # Load from platforms.yaml
        
    # _extract_item() not overridden - uses default None implementation
```

**Result Format Transformation**:

The Google API returns results in this format:
```json
{
  "items": [
    {
      "title": "Article Title",
      "link": "https://example.com/article",
      "snippet": "Article description...",
      "pagemap": {
        "metatags": [{
          "article:published_time": "2024-01-01T00:00:00Z"
        }]
      }
    }
  ]
}
```

Transform to standard format:
```python
{
    "title": item["title"],
    "url": item["link"],
    "source": "Google",  # or from config metadata.display_name
    "snippet": item.get("snippet", ""),
    "date": item.get("pagemap", {}).get("metatags", [{}])[0].get("article:published_time", "")
}
```

**API Request Logic**:

- Base URL: `https://www.googleapis.com/customsearch/v1`
- Parameters:
  - `key`: API key (from environment variable)
  - `cx`: Search engine ID (from environment variable)
  - `q`: Query string (sanitized)
  - `num`: Results per page (max 10, always use 10 for efficiency)
  - `start`: Start index for pagination (1-based: 1, 11, 21, ...)
- Pagination: Calculate number of requests needed (max_results / 10, rounded up)
  - Example: For max_results=30, need 3 requests with start=1, 11, 21
  - Example: For max_results=15, need 2 requests with start=1, 11

**Error Handling**:

- **Missing credentials**: Log warning, return empty results (don't crash)
- **429 (Rate Limit)**: 
  - Log warning
  - Implement exponential backoff retry (max 3 retries)
  - Return partial results if some requests succeeded
- **400 (Invalid Query)**: 
  - Log error with details
  - Return empty results (don't retry)
- **401 (Invalid Credentials)**: 
  - Log error
  - Return empty results (don't retry, credentials won't change)
- **Network errors**: 
  - Retry with exponential backoff (max 3 retries)
  - Return partial results if some requests succeeded
- **Other errors**: 
  - Log error with details
  - Return empty results or partial results

### 2. Configuration Updates

**File**: `config/platforms.yaml`

**New Section**:

```yaml
google:
  # API configuration (loaded from environment variables)
  api:
    base_url: "https://www.googleapis.com/customsearch/v1"
    max_results_per_request: 10
    max_total_results: 30
  
  # Platform metadata
  metadata:
    name: "Google"
    display_name: "Google Custom Search"
    description: "Search using Google Custom Search API"
  
  # Content extraction selectors
  # Since Google returns results from various domains,
  # we use generic selectors that work for most websites
  content_selectors:
    main_content:
      - "article"
      - "main"
      - ".content"
      - "#content"
      - ".post-content"
      - ".entry-content"
      - ".article-content"
      - "body"  # Fallback to body if no specific container found
    
    elements_to_remove:
      - "nav"
      - "header"
      - "footer"
      - ".sidebar"
      - ".comments"
      - "script"
      - "style"
      - ".ad"
      - ".advertisement"
      - "[class*='ad']"
      - "[id*='ad']"
```

**Note**: Content selectors are generic because Google can return results from any website. The selectors are tried in order, and the first matching element is used.

### 3. MCP Server Integration

**File**: `mcp_server.py`

**Changes**:

1. Import GoogleSearcher:
   ```python
   from platforms.google_searcher import GoogleSearcher
   ```

2. Register platform in `start()` method:
   ```python
   # Check if API credentials are available
   google_api_key = os.getenv("APIKEY_GOOGLE_CUSTOM_SEARCH")
   google_search_id = os.getenv("APIKEY_GOOGLE_SEARCH_ID")
   
   if google_api_key and google_search_id:
       self.manager.register_platform(
           "google", 
           GoogleSearcher(self.manager.browser_pool)
       )
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
       "enum": ["weixin", "google"],
       "description": "Platform to search (weixin, google). Note: zhihu is disabled by default due to anti-crawler measures."
   }
   ```

4. Update platforms/__init__.py (if it exists and is used for exports):
   ```python
   from .google_searcher import GoogleSearcher
   ```

### 4. Content Fetching Considerations

**Challenge**: Google returns results from various domains, each with different HTML structure.

**Solution**: 
- Use generic content selectors (as shown in config)
- ContentFetcher already supports multiple selector fallbacks
- If no selector matches, fallback to extracting text from `<body>` tag
- This is acceptable since we're extracting main content, not specific elements

**Domain-Specific Handling** (Future Enhancement):
- Could add domain-specific selectors in config
- Example: `content_selectors_by_domain` mapping
- For now, generic selectors should work for most cases

### 5. Rate Limiting and Anti-Crawler

**Google API Rate Limits**:
- Free tier: 100 queries per day
- Paid tier: Higher limits

**Implementation**:
- Use existing `RateLimitManager` in `UnifiedSearchManager`
- Add Google-specific rate limit configuration to `anti_crawler.yaml`:
  ```yaml
  google:
    rate_limit:
      requests_per_minute: 10  # Conservative limit
      requests_per_hour: 100
    delay:
      min_seconds: 1.0
      max_seconds: 3.0
  ```

**Anti-Crawler Detection**:
- Not needed for Google API (it's an official API)
- But content fetching from result URLs may still trigger anti-crawler
- Existing `AntiCrawlerDetector` in `ContentFetcher` handles this

### 6. Error Handling Strategy

**API Errors**:

1. **Missing Credentials**: 
   - Log warning, return empty results
   - Don't crash the server

2. **Invalid Credentials (401)**:
   - Log error, return empty results
   - Don't retry (credentials won't change)

3. **Rate Limit (429)**:
   - Log warning
   - Implement exponential backoff retry
   - Return partial results if some requests succeeded

4. **Invalid Query (400)**:
   - Log error with details
   - Return empty results

5. **Network Errors**:
   - Retry with exponential backoff (max 3 retries)
   - Return partial results if some requests succeeded

**Content Fetching Errors**:
- Handled by existing `ContentFetcher` error handling
- Failed fetches result in empty content, but search result still returned

### 7. Testing Strategy

**Unit Tests** (`tests/unit/test_google_searcher.py`):
- Test API request construction
- Test pagination logic
- Test result transformation
- Test error handling
- Mock API responses

**Integration Tests** (`tests/integration/test_google_search.py`):
- Test with real API (if credentials available)
- Test content fetching
- Test end-to-end search with content

**Mock Strategy**:
- Use `responses` library or `httpx` mocking
- Mock different API responses (success, errors, pagination)

## Implementation Steps

### Phase 1: Core Search Implementation

1. Create `platforms/google_searcher.py`
   - Implement `GoogleSearcher` class
   - Implement `search()` method with API calls
   - Implement pagination logic
   - Transform API response to standard format

2. Add configuration to `config/platforms.yaml`
   - Add `google` section with metadata and content selectors

3. Add rate limiting configuration to `config/anti_crawler.yaml`
   - Add `google` section with rate limits

### Phase 2: Integration

4. Update `mcp_server.py`
   - Import `GoogleSearcher`
   - Register platform (with credential check)
   - Update tool schema

5. Update `platforms/__init__.py` (if needed)
   - Export `GoogleSearcher`

### Phase 3: Content Fetching

6. Content fetching should work automatically via `ContentProcessor`
   - Verify content selectors work for common domains
   - Test with various result URLs

### Phase 4: Testing and Documentation

7. Write unit tests
8. Write integration tests
9. Update README with Google Custom Search setup instructions
10. Add example usage

## Dependencies

**Existing Dependencies**:
- `httpx[socks]>=0.28.0` is already in `requirements.txt` (used by ContentCompressor)
- No new dependencies needed for Google Custom Search integration

**Testing Dependencies**:
- `responses` or `pytest-httpx` for mocking HTTP requests in tests (check if already in `requirements-dev.txt`)

## Configuration Example

**Environment Variables**:
```bash
export APIKEY_GOOGLE_CUSTOM_SEARCH="your-api-key-here"
export APIKEY_GOOGLE_SEARCH_ID="your-search-engine-id-here"
```

**MCP Server Config** (Claude Desktop):
```json
{
  "mcpServers": {
    "vertical-search": {
      "command": "/path/to/python",
      "args": ["/path/to/mcp_server.py"],
      "env": {
        "APIKEY_DEEPSEEK": "your-deepseek-key",
        "APIKEY_GOOGLE_CUSTOM_SEARCH": "your-google-api-key",
        "APIKEY_GOOGLE_SEARCH_ID": "your-search-engine-id"
      }
    }
  }
}
```

## Future Enhancements

1. **Domain-Specific Content Selectors**: 
   - Add mapping of domain -> selectors in config
   - Improve content extraction accuracy

2. **Search Filters**:
   - Date range filtering
   - Site-specific search
   - Language filtering

3. **Result Ranking**:
   - Custom ranking based on relevance
   - Filter by domain reputation

4. **Caching Strategy**:
   - Cache API responses separately from browser-based results
   - Different TTL for API vs scraped results

## Compatibility Notes

- **Backward Compatibility**: Existing platforms (Weixin, Zhihu) unaffected
- **Optional Feature**: Google search only available if credentials provided
- **Graceful Degradation**: If API fails, returns empty results, doesn't crash server

## Security Considerations

1. **API Key Storage**: 
   - Never log API keys
   - Use environment variables only
   - Don't commit keys to repository

2. **Rate Limiting**:
   - Implement conservative rate limits
   - Monitor API usage
   - Handle quota exhaustion gracefully

3. **Input Validation**:
   - Sanitize search queries
   - Validate max_results (max 30)
   - Prevent injection attacks in API requests

## Performance Considerations

1. **API Latency**: 
   - Google API is fast (typically < 500ms)
   - Much faster than browser-based scraping
   - Pagination adds latency (sequential requests)

2. **Concurrent Requests**:
   - Could parallelize pagination requests (but respect rate limits)
   - Content fetching already concurrent via `ContentProcessor`

3. **Caching**:
   - API results cached same as browser-based results
   - Content caching works the same way

## Code Style Requirements

1. **PEP 8 Compliance**: Follow Python PEP 8 style guide
2. **Type Hints**: Use type hints for all function parameters and return types
3. **Docstrings**: Use Google-style docstrings for all classes and methods
4. **Error Handling**: Explicit and meaningful exception handling
5. **Logging**: Use `self.logger` for all logging (info, warning, error, debug)
6. **Naming**: Use meaningful variable and function names

## Testing Requirements

**Note**: For initial implementation, **no tests are required**. However, code should be designed to be testable:

- Use dependency injection (browser_pool passed via constructor)
- Separate API call logic from business logic
- Design for easy mocking (API responses, network errors)

Tests will be added in a later phase:
- Unit tests with mocked API responses
- Integration tests with real API (if credentials available)
- End-to-end tests via MCP client

## Verification Checklist

After implementation, verify:

- [ ] Server starts normally without Google API credentials (no Google search available)
- [ ] Server starts with Google API credentials (Google search available)
- [ ] Google search can be called via MCP tools
- [ ] Returned results match Weixin search format
- [ ] Content fetching works for Google search results
- [ ] Content compression works for Google search results
- [ ] Existing Weixin and Zhihu searches unaffected
- [ ] Code style consistent with existing codebase
- [ ] Complete docstrings for all methods
- [ ] Robust error handling with appropriate logging
- [ ] Rate limiting works correctly

## Summary

This design maintains compatibility with the existing architecture while adding API-based search capability. The key insight is that:

1. **Search** uses REST API (different from browser-based)
2. **Content fetching** still uses browser pool (same as existing platforms)
3. **Content compression** works the same way
4. **Result format** is standardized across all platforms

The implementation is straightforward and requires minimal changes to existing code, mainly:
- New searcher class
- Configuration updates
- MCP server registration

