# Vertical Search MCP

A scalable vertical search MCP (Model Context Protocol) server supporting multiple platforms (WeChat, Zhihu, etc.).

## Features

- **Multi-platform support**: Default support for WeChat and Zhihu, easily extensible to other platforms
- **High performance**: Browser reuse mechanism, 5x speed improvement
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

Configure the MCP server in Claude Desktop's settings:

```json
{
  "mcpServers": {
    "vertical-search": {
      "command": "python",
      "args": ["/path/to/vertical-search-mcp/mcp_server.py"]
    }
  }
}
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
        # max_results: Maximum number of results to return (default: 10)
        # time_filter: Optional time filter - 'day', 'week', 'month', or 'year' (default: None)
        # use_cache: Whether to use cache (default: True)
        results = await manager.search(
            platform='weixin',
            query='Python',
            max_results=10,
            time_filter=None,  # Optional: 'day', 'week', 'month', 'year'
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
        
        # Search with time filter
        recent_results = await manager.search(
            platform='weixin',
            query='Machine Learning',
            max_results=5,
            time_filter='week',  # Search within last week
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
        'url': 'https://weixin.sogou.com/link?url=...',
        'source': '微信公众号',
        'date': '2024-01-15',  # May be empty if not available
        'snippet': '本文详细介绍了Python变量命名的最佳实践...'  # May be empty if not available
    },
    {
        'title': 'Python异步编程指南',
        'url': 'https://weixin.sogou.com/link?url=...',
        'source': '微信公众号',
        'date': '2024-01-14',
        'snippet': '深入理解Python的asyncio模块...'
    },
    # ... more results
]
```

#### Result Fields

Each result dictionary contains the following fields:

- **title** (str): Article title
- **url** (str): Article URL (absolute URL)
- **source** (str): Source platform name (e.g., "微信公众号")
- **date** (str): Publication date (may be empty if not available)
- **snippet** (str): Article snippet/description (may be empty if not available)

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
│   └── search_manager.py      # Unified manager
├── platforms/                 # Platform adapters
│   ├── weixin_searcher.py     # WeChat searcher
│   └── zhihu_searcher.py      # Zhihu searcher
├── config/                    # Configuration files
│   └── platforms.yaml         # Platform configurations
├── tests/                     # Test files
│   ├── unit/                  # Unit tests
│   ├── integration/           # Integration tests
│   ├── benchmark/             # Performance tests
│   └── load/                  # Load tests
└── docs/                      # Documentation
```

## Performance

| Operation | Original | Optimized | Improvement |
|-----------|----------|-----------|-------------|
| First search | 5.2s | 5.1s | - |
| Subsequent searches | 5.1s | 0.9s | **5.7x** |
| Concurrent 3 searches | 15.3s | 3.2s | **4.8x** |
| Cache hit | N/A | 0.01s | **∞** |

## License

MIT License

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## References

- [Design Document](docs/vertical-search-mcp-design.md)
- [Quick Start Guide](docs/vertical-search-mcp-quickstart.md)
- [Documentation Index](docs/vertical-search-mcp-index.md)

