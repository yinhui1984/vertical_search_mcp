# Vertical Search MCP

一个可扩展的垂直搜索 MCP（模型上下文协议）服务器，支持多个平台（微信、知乎等）。

## 功能特性

- **多平台支持**：默认支持微信和知乎，可轻松扩展至其他平台
- **高性能**：浏览器复用机制，速度提升 5 倍
- **真实 URL 解析**：自动解析重定向链接，获取最终目标 URL（例如，微信的 `mp.weixin.qq.com`，知乎的 `zhihu.com`）
- **内容获取和压缩**：获取完整文章内容，使用 DeepSeek API 进行智能压缩
- **高可扩展性**：新平台集成仅需 1-2 小时
- **生产级稳定性**：全面的错误处理和监控

## 架构

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

## 系统要求

- Python 3.12+
- Playwright 1.40.0+
- PyYAML 6.0+
- OpenAI SDK 1.0.0+（用于 DeepSeek API 兼容性）

## 安装

1. 克隆仓库：
```bash
git clone <repository-url>
cd vertical-search-mcp
```

2. 创建虚拟环境：
```bash
python3.12 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

3. 安装依赖：
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

4. 安装 Playwright Chromium：
```bash
playwright install chromium
```

## 使用方法

### MCP 服务器

MCP 服务器提供异步搜索工具（`start_vertical_search` 和 `get_search_status`），可以被支持 MCP 协议的 AI 客户端调用（例如 Claude Desktop）。

#### 配置

在您的 AI 客户端设置文件中配置 MCP 服务器。例如，在 Claude Desktop 中：

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

**重要提示**：
- 将 `/path/to/vertical-search-mcp` 替换为项目目录的实际路径
- 使用虚拟环境中的 Python 解释器（`.venv/bin/python`）
- 如果使用系统级 Python，可以使用 `python3` 或 Python 解释器的完整路径
- **内容压缩的 API 密钥**：如果需要智能内容压缩，请在 `env` 字段中添加 `APIKEY_DEEPSEEK`
  - 从以下地址获取 API 密钥：https://platform.deepseek.com/
  - **何时需要 API 密钥**：对于长文章（超过 3000 tokens），系统使用 DeepSeek API 智能压缩内容，同时保留关键信息。没有 API 密钥时，长文章将被截断，可能会丢失重要内容。
  - **何时 API 密钥可选**：对于短文章（少于 3000 tokens），不需要压缩，因此不需要 API 密钥。
- 更新配置后，重启您的 AI 客户端（例如 Claude Desktop）

#### 工具：异步搜索 API

MCP 服务器提供异步搜索工具，支持长时间运行的搜索而不会超时。所有搜索都使用统一的异步模式。

**工具 1: `start_vertical_search`**

启动异步搜索任务。立即返回 `task_id`（< 1 秒），允许搜索在后台运行。

**参数：**
- `platform`（必需）：要搜索的平台（`weixin` 或 `zhihu`）
- `query`（必需）：搜索查询字符串（1-100 个字符）
- `max_results`（可选）：最大结果数（1-30，默认：10）
- `include_content`（可选）：是否包含完整文章内容（默认：`true`）

**响应：**
- 如果任务快速完成（< 1 秒）：直接返回结果，`status: "completed"`
- 否则：返回 `task_id` 和 `status: "started"` 用于轮询

**工具 2: `get_search_status`**

获取异步搜索任务的状态和结果。使用此工具轮询进度并在就绪时检索结果。

**参数：**
- `task_id`（必需）：来自 `start_vertical_search` 的任务 ID

**响应：**
- `status: "running"`：任务仍在执行，包含 `progress` 信息
- `status: "completed"`：任务完成，包含 `content` 和结果
- `status: "failed"`：任务失败，包含 `error` 消息
- `status: "not_found"`：任务已过期或不存在（任务在 30 分钟后过期）

**工具 3: `cancel_search`**（可选）

取消正在运行的搜索任务。

**参数：**
- `task_id`（必需）：要取消的任务 ID

**关于 `include_content` 参数的说明：**
- 当 `include_content=true`（默认）：获取完整文章内容并智能压缩以保持在 token 限制内
  - **短文章（≤3000 tokens）**：不需要压缩，无需 `APIKEY_DEEPSEEK` 即可工作
  - **长文章（>3000 tokens）**：建议使用 DeepSeek API 密钥
    - 有 API 密钥（`APIKEY_DEEPSEEK`）：使用 DeepSeek 压缩，同时保留关键信息、结论和重要细节
    - 无 API 密钥：回退到安全截断策略，可能会丢失尾部内容
- 当 `include_content=false`：仅返回标题、URL、摘要

**在 Claude 中的使用示例**：
```
搜索微信上的 Python 文章，限制为 5 个结果。
```

**重要：需要轮询**
AI 必须遵循以下工作流程：
1. 调用 `start_vertical_search` 启动搜索
2. **每 10-15 秒重复调用 `get_search_status`**，直到：
   - `status == "completed"` → 向用户返回结果
   - `status == "failed"` → 向用户报告错误
   - 在达到这些最终状态之一之前，不要停止轮询
3. 在轮询时向用户显示进度更新
4. 任务完成时返回结果

**示例 AI 工作流程**：
```python
# 步骤 1：启动搜索
response = start_vertical_search(platform="weixin", query="Python", max_results=5)
task_id = response["task_id"]

# 步骤 2：轮询直到完成（重要：持续轮询！）
while True:
    status = get_search_status(task_id=task_id)
    
    if status["status"] == "completed":
        # 获得结果，返回给用户
        return status["content"]
    elif status["status"] == "failed":
        # 任务失败，报告错误
        return f"搜索失败: {status['error']}"
    else:
        # 仍在运行，显示进度并等待
        print(f"进度: {status['progress']['percentage']}%")
        # 等待 10-15 秒后再下次轮询
        await sleep(12)
```

**快速完成检测：**
- 如果任务在 < 1 秒内完成，`start_vertical_search` 直接返回结果
- 这避免了快速搜索的不必要轮询
- 对于较长的搜索，使用 `get_search_status` 轮询结果

**进度更新：**
搜索进度通过 `get_search_status` 报告，包含以下阶段：
- `searching`：在平台上查找文章
- `fetching_content`：下载文章内容
- `compressing`：压缩内容以符合 token 限制

**示例响应**：
```
在微信上找到 5 个 'Python' 结果：

1. **Python变量命名规范详解**
   来源：微信公众号
   日期：2024-01-15
   摘要：本文详细介绍了Python变量命名的最佳实践...
   链接：https://mp.weixin.qq.com/s?src=11&timestamp=...

2. **Python异步编程指南**
   来源：微信公众号
   日期：2024-01-14
   摘要：深入理解Python的asyncio模块...
   链接：https://mp.weixin.qq.com/s?src=11&timestamp=...

...
```

**注意**：返回的 URL 是真实链接（例如，微信的 `mp.weixin.qq.com`，知乎的 `zhihu.com`），而不是来自搜狗的重定向链接。

#### 测试 MCP 服务器

您可以手动测试 MCP 服务器：

```bash
# 激活虚拟环境
source .venv/bin/activate

# 运行服务器（它将从 stdin 读取）
python mcp_server.py
```

然后发送 JSON-RPC 消息进行测试：

```json
{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}
{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "start_vertical_search", "arguments": {"platform": "weixin", "query": "Python", "max_results": 3}}}
{"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "get_search_status", "arguments": {"task_id": "<task_id_from_previous_response>"}}}
```

### 直接使用

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

#### 示例输出

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

**注意**：返回的 URL 是直接指向目标平台的真实链接：
- 微信文章：`https://mp.weixin.qq.com/s?...`
- 知乎问题/文章：`https://www.zhihu.com/question/...` 或 `https://www.zhihu.com/...`

系统自动解析来自搜狗的重定向链接以获取最终目标 URL。

#### 结果字段

每个结果字典包含以下字段：

- **title** (str)：文章标题
- **url** (str)：文章 URL（指向目标平台的真实链接，不是重定向链接）
  - 微信：`https://mp.weixin.qq.com/s?...`
  - 知乎：`https://www.zhihu.com/question/...` 或 `https://www.zhihu.com/...`
- **source** (str)：来源平台名称（例如，"微信公众号"、"知乎"）
- **date** (str)：发布日期（如果不可用可能为空）
- **snippet** (str)：文章摘要/描述（如果不可用可能为空）
- **content** (str, 可选)：完整文章内容（仅在 `include_content=true` 时）
  - 如果超过 token 限制可能会被压缩
  - 状态由 `content_status` 字段指示
- **content_status** (str, 可选)：内容处理状态
  - `"fetched"`：内容成功获取
  - `"compressed"`：内容使用 DeepSeek API 压缩
  - `"batch_compressed"`：内容与其他文章批量压缩
  - `"truncated"`：内容被截断（压缩失败或过大）
  - `"fetch_failed"`：获取内容失败

## 开发

### 运行测试

```bash
# 运行所有测试
pytest

# 运行并生成覆盖率报告
pytest --cov=. --cov-report=html

# 运行特定测试
pytest tests/unit/test_browser_pool.py -v
```

### 代码质量

```bash
# 类型检查
mypy core/ platforms/ --strict

# 代码格式化
black core/ platforms/ tests/

# 代码检查
flake8 core/ platforms/ --max-line-length=100
```

## 项目结构

```
vertical-search-mcp/
├── mcp_server.py              # MCP 协议层
├── core/                      # 核心模块
│   ├── browser_pool.py        # 浏览器池
│   ├── cache.py               # 缓存层
│   ├── base_searcher.py       # 基础搜索器类
│   ├── search_manager.py      # 统一管理器
│   ├── url_resolver.py        # URL 解析器（重定向到真实链接）
│   ├── content_fetcher.py     # 文章内容获取器
│   ├── content_compressor.py  # 内容压缩器（DeepSeek API）
│   ├── content_processor.py   # 内容处理协调器
│   └── token_estimator.py    # Token 估算器
├── platforms/                 # 平台适配器
│   ├── weixin_searcher.py     # 微信搜索器
│   └── zhihu_searcher.py      # 知乎搜索器
├── config/                    # 配置文件
│   ├── platforms.yaml         # 平台配置
│   ├── compression.yaml       # 内容压缩设置
│   └── anti_crawler.yaml      # 反爬虫保护设置
├── tests/                     # 测试文件
│   ├── unit/                  # 单元测试
│   ├── integration/           # 集成测试
│   ├── benchmark/             # 性能测试
│   └── load/                  # 负载测试
└── docs/                      # 文档
```

## 性能

| 操作 | 优化版本 | 改进 |
|------|---------|------|
| 首次搜索 | 5.1s | - |
| 后续搜索 | 0.9s | **5.7x** |
| 并发 3 次搜索 | 3.2s | **4.8x** |
| 缓存命中 | 0.01s | **∞** |

## 许可证

MIT License

## 贡献

详情请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 参考资料

- [设计文档](docs/vertical-search-mcp-design.md)
- [快速开始指南](docs/vertical-search-mcp-quickstart.md)
- [文档索引](docs/vertical-search-mcp-index.md)

