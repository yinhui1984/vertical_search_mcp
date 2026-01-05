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
from core.search_manager import UnifiedSearchManager
from platforms.weixin_searcher import WeixinSearcher
from core.browser_pool import BrowserPool

# Initialize
pool = BrowserPool()
manager = UnifiedSearchManager()
manager.register_platform('weixin', WeixinSearcher(pool))

# Search
results = await manager.search('weixin', 'Python', max_results=10)
```

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

