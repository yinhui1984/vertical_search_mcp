# Google Custom Search Integration - Quick Summary

## Overview

Integrate Google Custom Search API as a new search platform in the Vertical Search MCP server. Unlike existing browser-based platforms (Weixin, Zhihu), Google uses a REST API.

## Key Design Decisions

1. **Minimal Refactoring**: Make `_extract_item()` optional in `BasePlatformSearcher` (default implementation returns `None`)
2. **Reuse Existing Infrastructure**: Content fetching and compression work the same way
3. **Backward Compatible**: No changes to existing platforms required

## Architecture

```
GoogleSearcher (API-based)
  ├── Uses httpx for API calls (no browser for search)
  ├── Transforms JSON response to standard format
  └── Still uses browser pool for content fetching (via ContentProcessor)
```

## Implementation Files

1. **New**: `platforms/google_searcher.py` - GoogleSearcher class
2. **Modify**: `core/base_searcher.py` - Make `_extract_item()` optional
3. **Modify**: `mcp_server.py` - Register Google platform
4. **Modify**: `config/platforms.yaml` - Add Google configuration
5. **Modify**: `config/anti_crawler.yaml` - Add Google rate limiting

## Environment Variables

```bash
export APIKEY_GOOGLE_CUSTOM_SEARCH="your-api-key"
export APIKEY_GOOGLE_SEARCH_ID="your-search-engine-id"
```

## Configuration Structure

### platforms.yaml
```yaml
google:
  api:
    base_url: "https://www.googleapis.com/customsearch/v1"
    max_results_per_request: 10
    max_total_results: 30
  metadata:
    name: "Google"
    display_name: "Google Custom Search"
  content_selectors:
    main_content: [generic selectors for various domains]
    elements_to_remove: [common interference elements]
```

### anti_crawler.yaml
```yaml
platforms:
  google:
    rate_limit:
      max_requests_per_minute: 10
      max_requests_per_hour: 100
    delay:
      min_delay_ms: 1000
      max_delay_ms: 3000
```

## Key Implementation Details

### Search Flow
1. Validate API credentials
2. Sanitize query
3. Make paginated API requests (10 results per request)
4. Transform JSON response to standard format:
   ```python
   {
       "title": item["title"],
       "url": item["link"],
       "source": "Google",
       "snippet": item.get("snippet", ""),
       "date": item.get("pagemap", {}).get("metatags", [{}])[0].get("article:published_time", "")
   }
   ```
5. Return results (content fetching happens later via ContentProcessor)

### Pagination
- Google API returns max 10 results per request
- For `max_results=30`, need 3 API requests
- Use `start` parameter: 1, 11, 21

### Error Handling
- Missing credentials: Log warning, return empty results
- Rate limit (429): Exponential backoff retry
- Network errors: Retry with backoff
- Invalid query (400): Log error, return empty results

## Testing Strategy

1. **Unit Tests**: Mock API responses, test pagination, test transformation
2. **Integration Tests**: Test with real API (if credentials available)
3. **End-to-End**: Test via MCP client

## Dependencies

- ✅ `httpx` already in `requirements.txt` (no new dependencies)

## Implementation Details

### API Request Parameters
- Base URL: `https://www.googleapis.com/customsearch/v1`
- Parameters: `key`, `cx`, `q`, `num=10`, `start` (1, 11, 21, ...)
- Pagination: For max_results=30, make 3 requests with start=1, 11, 21

### Result Format Transformation
```python
{
    "title": item["title"],
    "url": item["link"],
    "source": "Google",
    "snippet": item.get("snippet", ""),
    "date": item.get("pagemap", {}).get("metatags", [{}])[0].get("article:published_time", "")
}
```

### Error Handling
- Missing credentials: Log warning, return []
- 429 (Rate Limit): Exponential backoff retry (max 3), return partial results
- 400 (Invalid Query): Log error, return []
- 401 (Invalid Credentials): Log error, return []
- Network errors: Exponential backoff retry (max 3), return partial results

## Code Style Requirements

1. PEP 8 compliance
2. Type hints for all functions
3. Google-style docstrings
4. Explicit error handling
5. Meaningful logging using `self.logger`
6. Meaningful variable names

## Migration Checklist

- [ ] Modify `BasePlatformSearcher._extract_item()` to be optional
- [ ] Create `platforms/google_searcher.py` with:
  - [ ] API credential validation
  - [ ] Query sanitization
  - [ ] Pagination logic
  - [ ] JSON transformation
  - [ ] Error handling with retry
- [ ] Add Google config to `platforms.yaml`
- [ ] Add Google rate limiting to `anti_crawler.yaml`
- [ ] Register Google platform in `mcp_server.py`
- [ ] Update tool schema to include "google"
- [ ] Update `platforms/__init__.py` (if exists)
- [ ] Manual testing (tests will be added later)
- [ ] Update README with setup instructions

## Verification Checklist

- [ ] Server starts without credentials (no Google search)
- [ ] Server starts with credentials (Google search available)
- [ ] Google search works via MCP tools
- [ ] Results match standard format
- [ ] Content fetching works
- [ ] Content compression works
- [ ] Existing platforms unaffected

## Documentation

- **Detailed Design**: `GOOGLE_CUSTOM_SEARCH_DESIGN.md`
- **Refactoring Plan**: `GOOGLE_CUSTOM_SEARCH_REFACTORING.md`
- **This Summary**: `GOOGLE_CUSTOM_SEARCH_SUMMARY.md`

## Notes

- Google search is **optional** - only registered if credentials are provided
- Content fetching uses generic selectors (works for most domains)
- Rate limiting is conservative to avoid quota exhaustion
- Backward compatible with existing platforms

