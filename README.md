# Vertical Search MCP

[中文文档](README_cn.md) | [English](README.md)

A scalable vertical search MCP (Model Context Protocol) server supporting multiple platforms (WeChat, Zhihu, etc.).

## Features

- **Multi-platform support**: Default support for WeChat and Zhihu, easily extensible to other platforms
- **High performance**: Browser reuse mechanism, 5x speed improvement
- **Real URL resolution**: Automatically resolves redirect links to get final destination URLs (e.g., `mp.weixin.qq.com` for WeChat, `zhihu.com` for Zhihu)
- **Content fetching and compression**: Fetch full article content with intelligent compression using DeepSeek API
- **High extensibility**: New platform integration takes only 1-2 hours
- **Production-ready stability**: Comprehensive error handling and monitoring

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  MCP Client (Claude)                 │
└────────────────────┬────────────────────────────────┘
                     │ JSON-RPC 2.0
┌────────────────────▼────────────────────────────────┐
│              MCP Server (mcp_server.py)              │
│  ┌─────────────────────────────────────────────┐   │
│  │        UnifiedSearchManager                  │   │
│  │  - Platform routing                          │   │
│  │  - Browser pool management                   │   │
│  │  - Cache management                          │   │
│  └───────┬──────────────────────┬────────────────┘  │
│          │                      │                    │
│  ┌───────▼────────┐    ┌───────▼────────┐          │
│  │ WeixinSearcher │    │ ZhihuSearcher  │   ...    │
│  └────────┬───────┘    └────────┬───────┘          │
└───────────┼──────────────────────┼──────────────────┘
            │                      │
┌───────────▼──────────────────────▼──────────────────┐
│         Playwright Browser Pool (Persistent)       │
└─────────────────────────────────────────────────────┘
```

## Requirements

- Python 3.12+
- Playwright 1.40.0+
- PyYAML 6.0+
- OpenAI SDK 1.0.0+ (for DeepSeek API compatibility)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd vertical-search-mcp
```

2. Create a virtual environment:
```bash
python3.12 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

4. Install Playwright Chromium:
```bash
playwright install chromium
```

## Usage

### MCP Server

The MCP server provides async search tools (`start_vertical_search` and `get_search_status`) that can be called from AI clients supporting the MCP protocol (e.g., Claude Desktop).

#### Configuration

Configure the MCP server in your AI client's settings file. For example, in Claude Desktop:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "vertical-search": {
      "command": "/path/to/vertical-search-mcp/.venv/bin/python",
      "args": ["/path/to/vertical-search-mcp/mcp_server.py"],
      "env": {
        "APIKEY_DEEPSEEK": "your-deepseek-api-key-here"
      }
    }
  }
}
```

**Important Notes**:
- Replace `/path/to/vertical-search-mcp` with the actual path to your project directory
- Use the Python interpreter from your virtual environment (`.venv/bin/python`)
- If you're using a system-wide Python, you can use `python3` or the full path to your Python interpreter
- **API Key for Content Compression**: Add `APIKEY_DEEPSEEK` in the `env` field if you need intelligent content compression
  - Get your API key from: https://platform.deepseek.com/
  - **When API key is required**: For long articles (exceeding 3000 tokens), the system uses DeepSeek API to intelligently compress content while preserving key information. Without the API key, long articles will be truncated, potentially losing important content.
  - **When API key is optional**: For short articles (under 3000 tokens), compression is not needed, so the API key is not required.
- After updating the config, restart your AI client (e.g., Claude Desktop)

#### Tools: Async Search API

The MCP server provides async search tools that support long-running searches without timeout issues. All searches use the unified async mode.

**Tool 1: `start_vertical_search`**

Start an async search task. Returns `task_id` immediately (< 1 second), allowing the search to run in the background.

**Parameters:**
- `platform` (required): Platform to search (`weixin` or `zhihu`)
- `query` (required): Search query string (1-100 characters)
- `max_results` (optional): Maximum number of results (1-30, default: 10)
- `include_content` (optional): Whether to include full article content (default: `true`)

**Response:**
- If task completes quickly (< 1 second): Returns results directly with `status: "completed"`
- Otherwise: Returns `task_id` and `status: "started"` for polling

**Tool 2: `get_search_status`**

Get the status and results of an async search task. Use this to poll for progress and retrieve results when ready.

**Parameters:**
- `task_id` (required): Task ID from `start_vertical_search`

**Response:**
- `status: "running"`: Task is still executing, includes `progress` information
- `status: "completed"`: Task finished, includes `content` with results
- `status: "failed"`: Task failed, includes `error` message
- `status: "not_found"`: Task expired or doesn't exist (tasks expire after 30 minutes)

**Tool 3: `cancel_search`** (optional)

Cancel a running search task.

**Parameters:**
- `task_id` (required): Task ID to cancel

**Note on `include_content` parameter:**
- When `include_content=true` (default): Fetches full article content and intelligently compresses it to stay within token limits
  - **Short articles (≤3000 tokens)**: No compression needed, works without `APIKEY_DEEPSEEK`
  - **Long articles (>3000 tokens)**: DeepSeek API key recommended
    - With API key (`APIKEY_DEEPSEEK`): Uses DeepSeek to compress while preserving key information, conclusions, and important details
    - Without API key: Falls back to safe truncation strategy, potentially losing tail content
- When `include_content=false`: Returns only titles, URLs, snippets

**Example Usage in Claude**:
```
Search for Python articles on WeChat from the last week, limit to 5 results.
```

**IMPORTANT: Polling Required**
The AI MUST follow this workflow:
1. Call `start_vertical_search` to start the search
2. **Repeatedly call `get_search_status` every 10-15 seconds** until:
   - `status == "completed"` → Return results to user
   - `status == "failed"` → Report error to user
   - Do NOT stop polling until one of these final states is reached
3. Display progress updates to the user while polling
4. Return results when the task completes

**Example AI Workflow**:
```python
# Step 1: Start search
response = start_vertical_search(platform="weixin", query="Python", max_results=5)
task_id = response["task_id"]

# Step 2: Poll until complete (IMPORTANT: Keep polling!)
while True:
    status = get_search_status(task_id=task_id)
    
    if status["status"] == "completed":
        # Got results, return to user
        return status["content"]
    elif status["status"] == "failed":
        # Task failed, report error
        return f"Search failed: {status['error']}"
    else:
        # Still running, show progress and wait
        print(f"Progress: {status['progress']['percentage']}%")
        # Wait 10-15 seconds before next poll
        await sleep(12)
```

**Fast Completion Detection:**
- If a task completes in < 1 second, `start_vertical_search` returns results directly
- This avoids unnecessary polling for quick searches
- For longer searches, use `get_search_status` to poll for results

**Progress Updates:**
The search progress is reported through `get_search_status` with stages:
- `searching`: Finding articles on the platform
- `fetching_content`: Downloading article content
- `compressing`: Compressing content to fit token limits

**Example Response**:
```
Found 5 result(s) for 'Python' on WeChat:

1. **Python变量命名规范详解**
   Source: 微信公众号
   Date: 2024-01-15
   Summary: 本文详细介绍了Python变量命名的最佳实践...
   Link: https://mp.weixin.qq.com/s?src=11&timestamp=...

2. **Python异步编程指南**
   Source: 微信公众号
   Date: 2024-01-14
   Summary: 深入理解Python的asyncio模块...
   Link: https://mp.weixin.qq.com/s?src=11&timestamp=...

...
```

**Note**: The returned URLs are real links (e.g., `mp.weixin.qq.com` for WeChat, `zhihu.com` for Zhihu), not redirect links from Sogou.

#### Testing the MCP Server

You can test the MCP server manually:

```bash
# Activate virtual environment
source .venv/bin/activate

# Run the server (it will read from stdin)
python mcp_server.py
```

Then send JSON-RPC messages to test:

```json
{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}}
{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "start_vertical_search", "arguments": {"platform": "weixin", "query": "Python", "max_results": 3}}}
{"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "get_search_status", "arguments": {"task_id": "<task_id_from_previous_response>"}}}
```

### Direct Usage

```python
import asyncio
from core.search_manager import UnifiedSearchManager
from platforms.weixin_searcher import WeixinSearcher
from core.browser_pool import BrowserPool

async def main():
    # Initialize browser pool and search manager
    pool = BrowserPool()
    manager = UnifiedSearchManager()
    
    # Register platform searcher
    # platform: Platform name (e.g., 'weixin', 'zhihu')
    # searcher: Platform-specific searcher instance
    manager.register_platform('weixin', WeixinSearcher(pool))
    
    try:
        # Basic search
        # platform: Platform name (must be registered)
        # query: Search query string
        # max_results: Maximum number of results to return (default: 10, max: 30)
        #   Note: If max_results > 10, pagination will be used automatically
        # use_cache: Whether to use cache (default: True)
        results = await manager.search(
            platform='weixin',
            query='Python',
            max_results=10,
            use_cache=True
        )
        
        # Process results
        for result in results:
            print(f"Title: {result['title']}")
            print(f"URL: {result['url']}")
            print(f"Source: {result['source']}")
            print(f"Date: {result['date']}")
            print(f"Snippet: {result['snippet']}")
            print("---")
        
        # Search for recent results
        recent_results = await manager.search(
            platform='weixin',
            query='Machine Learning',
            max_results=5,
            use_cache=True
        )
        
        # Search with pagination (max_results > 10)
        # Pagination is automatic when requesting more than 10 results
        many_results = await manager.search(
            platform='weixin',
            query='Python',
            max_results=20,  # Will automatically paginate to get 20 results
            use_cache=True
        )
        
        # Get registered platforms
        platforms = manager.get_registered_platforms()
        print(f"Available platforms: {platforms}")
        
    finally:
        # Always close the manager to clean up browser resources
        await manager.close()

# Run the async function
asyncio.run(main())
```

#### Example Output

```python
# Example result structure
[
    {
        'title': 'Python变量命名规范详解',
        'url': 'https://mp.weixin.qq.com/s?src=11&timestamp=1767670509&ver=6463&signature=...',
        'source': '微信公众号',
        'date': '2024-01-15',  # May be empty if not available
        'snippet': '本文详细介绍了Python变量命名的最佳实践...'  # May be empty if not available
    },
    {
        'title': 'Python异步编程指南',
        'url': 'https://mp.weixin.qq.com/s?src=11&timestamp=1767670509&ver=6463&signature=...',
        'source': '微信公众号',
        'date': '2024-01-14',
        'snippet': '深入理解Python的asyncio模块...'
    },
    # ... more results
]

# Example for Zhihu platform
[
    {
        'title': 'Python 麦该愉么喜?',
        'url': 'https://www.zhihu.com/question/353341563',
        'source': '知乎',
        'date': '',  # May be empty if not available
        'snippet': ''  # May be empty if not available
    },
    # ... more results
]
```

**Note**: The returned URLs are real links directly to the target platforms:
- WeChat articles: `https://mp.weixin.qq.com/s?...`
- Zhihu questions/articles: `https://www.zhihu.com/question/...` or `https://www.zhihu.com/...`

The system automatically resolves redirect links from Sogou to get the final destination URLs.

#### Result Fields

Each result dictionary contains the following fields:

- **title** (str): Article title
- **url** (str): Article URL (real link to the target platform, not a redirect link)
  - WeChat: `https://mp.weixin.qq.com/s?...`
  - Zhihu: `https://www.zhihu.com/question/...` or `https://www.zhihu.com/...`
- **source** (str): Source platform name (e.g., "微信公众号", "知乎")
- **date** (str): Publication date (may be empty if not available)
- **snippet** (str): Article snippet/description (may be empty if not available)
- **content** (str, optional): Full article content (only when `include_content=true`)
  - May be compressed if it exceeds token limits
  - Status indicated by `content_status` field
- **content_status** (str, optional): Content processing status
  - `"fetched"`: Content successfully fetched
  - `"compressed"`: Content was compressed using DeepSeek API
  - `"batch_compressed"`: Content was batch compressed with other articles
  - `"truncated"`: Content was truncated (compression failed or too large)
  - `"fetch_failed"`: Failed to fetch content

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test
pytest tests/unit/test_browser_pool.py -v
```

### Code Quality

```bash
# Type checking
mypy core/ platforms/ --strict

# Code formatting
black core/ platforms/ tests/

# Linting
flake8 core/ platforms/ --max-line-length=100
```

## Project Structure

```
vertical-search-mcp/
├── mcp_server.py              # MCP protocol layer
├── core/                      # Core modules
│   ├── browser_pool.py        # Browser pool
│   ├── cache.py               # Cache layer
│   ├── base_searcher.py       # Base searcher class
│   ├── search_manager.py      # Unified manager
│   ├── url_resolver.py        # URL resolver (redirect to real links)
│   ├── content_fetcher.py     # Article content fetcher
│   ├── content_compressor.py  # Content compressor (DeepSeek API)
│   ├── content_processor.py   # Content processing coordinator
│   └── token_estimator.py    # Token estimation
├── platforms/                 # Platform adapters
│   ├── weixin_searcher.py     # WeChat searcher
│   └── zhihu_searcher.py      # Zhihu searcher
├── config/                    # Configuration files
│   ├── platforms.yaml         # Platform configurations
│   ├── compression.yaml       # Content compression settings
│   └── anti_crawler.yaml      # Anti-crawler protection settings
├── tests/                     # Test files
│   ├── unit/                  # Unit tests
│   ├── integration/           # Integration tests
│   ├── benchmark/             # Performance tests
│   └── load/                  # Load tests
└── docs/                      # Documentation
```

## Performance

| Operation | Optimized | Improvement |
|-----------|-----------|-------------|
| First search | 5.1s | - |
| Subsequent searches | 0.9s | **5.7x** |
| Concurrent 3 searches | 3.2s | **4.8x** |
| Cache hit | 0.01s | **∞** |

## License

MIT License

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## References

- [Design Document](docs/vertical-search-mcp-design.md)
- [Quick Start Guide](docs/vertical-search-mcp-quickstart.md)
- [Documentation Index](docs/vertical-search-mcp-index.md)

