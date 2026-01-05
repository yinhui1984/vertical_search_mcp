# 垂直搜索 MCP 项目背景文档

**版本**: 1.0  
**最后更新**: 2026-01-05  
**用途**: 每个迭代开始时的背景知识输入

---

## 📖 项目定位

### 项目目标

构建一个**可扩展的垂直搜索 MCP（Model Context Protocol）服务器**，作为"双引擎知识加速系统"的**引擎 2**（前沿信息追踪）。

```
双引擎知识加速系统架构
├── 引擎 1: 基础知识获取（静态权威资料）
│   └── 自动抓取 + AI 生成学习路径
├── 引擎 2: 前沿信息追踪（实时信息流）← 【本项目】
│   └── 垂直搜索 MCP + AI 过滤
└── AI 处理层
    └── 知识提取、筛选、结构化
```

### 核心价值

1. **多平台支持**: 默认支持微信、知乎，可轻松扩展到其他平台
2. **高性能**: 浏览器复用机制，速度提升 5 倍
3. **高扩展性**: 新平台接入仅需 1-2 小时
4. **生产级稳定性**: 完善的错误处理和监控机制

---

## 🔍 原项目分析

### 原项目位置

**路径**: `~/Documents/github/weixin-search-playwright-mcp`

### 原项目核心实现

#### 1. MCP Server (`mcp_server.py`)

**职责**: 实现标准 MCP 协议（JSON-RPC 2.0）

**关键方法**:
- `handle_initialize()`: 初始化 MCP 连接
- `handle_list_tools()`: 返回可用工具列表
- `handle_call_tool()`: 处理工具调用请求

**工具定义**:
- 工具名: `search_wechat_articles`
- 参数: `query`, `max_results`, `time_filter`
- 返回: 格式化的文本结果

**通信方式**: 通过 stdin/stdout 与 Claude Desktop 通信

#### 2. 搜索器实现 (`app/search/playwright_search.py`)

**核心类**: `WeChatArticleSearcher`

**关键特性**:

1. **Playwright 浏览器自动化**
   - 使用 `async_playwright()` 启动 Chromium
   - 配置浏览器参数（headless, args）
   - 创建 Context 和 Page

2. **多重选择器策略**（容错设计）
   ```python
   article_selectors = [
       ".results h3",          # 主要选择器
       ".news-box h3",         # 备用选择器 1
       ".result-item h3",      # 备用选择器 2
       "li h3",                # 通用选择器
       "h3 a[href*='mp.weixin.qq.com']"  # 直接查找微信链接
   ]
   ```

3. **资源拦截优化**
   - 禁用图片、字体、样式表加载
   - 性能提升 30-50%

4. **时间筛选支持**
   - day/week/month/year
   - 通过 URL 参数 `tsn` 实现

5. **错误处理和重试**
   - 页面加载超时重试（最多 3 次）
   - 浏览器连接状态检查

#### 3. 原项目的优点

✅ **Playwright 方案稳定**
- 完整浏览器指纹，反爬检测率低
- 自动处理 Cookie、JS、重定向
- 可视化调试支持

✅ **多重选择器策略**
- 提高解析成功率
- 应对页面结构变化

✅ **资源优化**
- 禁用不必要资源，提升速度

#### 4. 原项目的不足

❌ **浏览器复用不够优化**
- 浏览器是实例变量，每次创建 `WeChatArticleSearcher` 都会初始化
- 虽然检查了 `is_connected()`，但仍有优化空间

❌ **缺少缓存机制**
- 相同查询会重复抓取
- 没有 TTL 缓存

❌ **扩展性差**
- 硬编码微信搜索逻辑
- 添加新平台需要大量修改

❌ **架构不够模块化**
- 搜索逻辑、浏览器管理、解析逻辑耦合

---

## 🏗️ 新项目架构设计

### 整体架构

```
┌─────────────────────────────────────────────────────┐
│                  MCP Client (Claude)                 │
└────────────────────┬────────────────────────────────┘
                     │ JSON-RPC 2.0
┌────────────────────▼────────────────────────────────┐
│              MCP Server (mcp_server.py)              │
│  ┌─────────────────────────────────────────────┐   │
│  │        UnifiedSearchManager                  │   │
│  │  - 平台路由                                  │   │
│  │  - 浏览器池管理                              │   │
│  │  - 缓存管理                                  │   │
│  └───────┬──────────────────────┬────────────────┘  │
│          │                      │                    │
│  ┌───────▼────────┐    ┌───────▼────────┐          │
│  │ WeixinSearcher │    │ ZhihuSearcher  │   ...    │
│  │ (Platform      │    │ (Platform      │          │
│  │  Adapter)      │    │  Adapter)      │          │
│  └────────┬───────┘    └────────┬───────┘          │
└───────────┼──────────────────────┼──────────────────┘
            │                      │
┌───────────▼──────────────────────▼──────────────────┐
│         Playwright Browser Pool (常驻)              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐         │
│  │ Browser1 │  │ Browser2 │  │ Browser3 │   ...   │
│  └──────────┘  └──────────┘  └──────────┘         │
└───────────┬──────────────────────┬──────────────────┘
            │                      │
┌───────────▼──────────────────────▼──────────────────┐
│              Target Websites                         │
│  weixin.sogou.com    zhihu.sogou.com    ...        │
└─────────────────────────────────────────────────────┘
```

### 核心组件说明

#### 1. BrowserPool (`core/browser_pool.py`)

**设计理念**: 单例模式，浏览器常驻，只创建新页面

**关键改进**:
- 全局单例，避免重复初始化
- 使用 `asyncio.Lock` 保证线程安全
- 浏览器启动一次，后续只创建新页面（< 1秒）

**性能提升**: 5 倍（从 5s 降到 1s）

#### 2. SearchCache (`core/cache.py`)

**设计理念**: 简单内存缓存，TTL 过期机制

**特点**:
- TTL: 5 分钟（300秒）
- 缓存键格式: `platform:query:hash(params)`
- 自动清理过期条目

**性能提升**: 缓存命中 < 0.01s

#### 3. BasePlatformSearcher (`core/base_searcher.py`)

**设计理念**: 抽象基类，定义标准接口

**抽象方法**:
- `search()`: 执行搜索
- `_load_config()`: 加载平台配置
- `_extract_item()`: 提取单个结果项

**通用方法**:
- `_parse_results()`: 通用结果解析
- `_sanitize_query()`: 清理搜索查询
- `_clean_text()`: 清理文本

#### 4. UnifiedSearchManager (`core/search_manager.py`)

**设计理念**: 统一管理器，负责路由、缓存、错误处理

**职责**:
- 平台注册和路由
- 缓存检查和管理
- 错误处理和重试
- 日志记录

#### 5. Platform Adapters (`platforms/`)

**设计理念**: 插件化架构，每个平台一个适配器

**实现要求**:
- 继承 `BasePlatformSearcher`
- 实现抽象方法
- 从 YAML 加载配置

**新平台接入时间**: 1-2 小时

---

## 🎯 核心设计理念

### 1. 保留原作者的优秀设计

#### ✅ Playwright 作为核心引擎

**为什么不用纯 HTTP？**

```python
# 纯 HTTP 方案（不稳定）
❌ 搜狗微信搜索：403 Forbidden
❌ 需要逆向签名算法
❌ 容易被封 IP

# Playwright 方案（稳定）
✅ 正常访问，反爬检测率低
✅ 不需要研究签名
✅ 像真实用户一样访问
```

**关键配置**:
- `--disable-blink-features=AutomationControlled`: 隐藏自动化特征
- `--no-sandbox`: Docker 环境必需
- User-Agent: 模拟真实浏览器
- 请求拦截: 禁用图片、字体等

#### ✅ 多重选择器策略

**原因**: 页面结构可能变化，需要容错

**实现**: 按优先级尝试多个选择器，找到第一个可用的

### 2. 我们的核心改进

#### ⚡ 性能优化 - 浏览器复用

**原实现问题**:
```python
# 每次搜索都重启浏览器 ❌
async def search():
    browser = await playwright.chromium.launch()  # 5 秒
    # ... 搜索
    await browser.close()
```

**改进方案**:
```python
# 浏览器常驻，只创建新页面 ✅
browser = await playwright.chromium.launch()  # 只启动一次
page = await browser.new_page()  # <1 秒
```

**性能提升**:
- 首次搜索: 5s → 5s（相同）
- 后续搜索: 5s → 1s（提升 5 倍）

#### 🎯 架构改进 - 平台抽象

**插件化架构**:
```python
# 基类定义标准接口
class BasePlatformSearcher(ABC):
    @abstractmethod
    async def search(self, query, max_results): pass

# 新平台只需实现接口
class NewPlatformSearcher(BasePlatformSearcher):
    async def search(self, query, max_results):
        # 平台特定逻辑
        pass
```

**接入新平台成本**: 1-2 小时（vs 原方案 1-2 天）

#### 📦 配置化选择器

**YAML 配置**:
```yaml
weixin:
  base_url: "https://weixin.sogou.com/weixin"
  selectors:
    article_list:
      - ".results h3"
      - ".news-box h3"
      - ".result-item h3"
```

**优势**: 无需修改代码，只需更新配置

---

## 🔑 关键概念和术语

### MCP (Model Context Protocol)

**定义**: Claude 与外部工具通信的标准协议

**通信方式**: JSON-RPC 2.0 over stdin/stdout

**关键消息类型**:
- `initialize`: 初始化连接
- `tools/list`: 获取工具列表
- `tools/call`: 调用工具
- `notifications/initialized`: 初始化完成通知

### 平台适配器 (Platform Adapter)

**定义**: 封装特定平台搜索逻辑的类

**要求**:
- 继承 `BasePlatformSearcher`
- 实现抽象方法
- 从配置加载平台特定信息

### 浏览器池 (Browser Pool)

**定义**: 管理 Playwright 浏览器实例的组件

**特点**:
- 单例模式
- 浏览器常驻
- 只创建新页面，不重启浏览器

### 缓存键 (Cache Key)

**格式**: `platform:query:hash(params)`

**示例**: `weixin:Python:abc123def456`

**用途**: 唯一标识一次搜索请求

### 多重选择器策略

**定义**: 按优先级尝试多个 CSS 选择器，找到第一个可用的

**目的**: 提高解析成功率，应对页面结构变化

---

## 🛠️ 技术栈

### 核心依赖

- **Python**: 3.12+
- **Playwright**: 1.40.0+ (浏览器自动化)
- **PyYAML**: 6.0+ (配置文件解析)
- **pytest**: 7.4.0+ (测试框架)
- **pytest-asyncio**: 0.21.0+ (异步测试支持)

### 开发工具

- **mypy**: 类型检查
- **black**: 代码格式化
- **flake8**: 代码风格检查
- **pytest-cov**: 测试覆盖率

### 为什么选择 Python？

1. **Playwright 官方支持**: Python 是 Playwright 官方支持的语言之一
2. **异步支持**: `asyncio` 原生支持，适合 I/O 密集型任务
3. **测试生态**: pytest 功能强大，测试友好
4. **开发效率**: 语法简洁，快速迭代

---

## 📁 项目结构

```
vertical-search-mcp/
├── mcp_server.py              # MCP 协议层（保留原作者）
├── core/
│   ├── __init__.py
│   ├── browser_pool.py        # 浏览器池（新增）
│   ├── cache.py               # 缓存层（新增）
│   ├── base_searcher.py       # 基类（新增）
│   ├── search_manager.py      # 统一管理器（新增）
│   ├── logger.py              # 日志系统（Iteration 6）
│   └── metrics.py             # 性能监控（Iteration 6）
├── platforms/
│   ├── __init__.py
│   ├── weixin_searcher.py     # 微信搜索（改进）
│   └── zhihu_searcher.py      # 知乎搜索（新增）
├── config/
│   └── platforms.yaml         # 平台配置（新增）
├── tests/
│   ├── unit/                  # 单元测试
│   ├── integration/           # 集成测试
│   ├── benchmark/             # 性能测试
│   └── load/                  # 压力测试
├── docs/                      # 文档
│   ├── vertical-search-mcp-design.md
│   ├── vertical-search-mcp-quickstart.md
│   └── vertical-search-mcp-index.md
├── requirements.txt           # 生产依赖
├── requirements-dev.txt       # 开发依赖
├── pyproject.toml             # 项目配置
├── pytest.ini                 # pytest 配置
├── mypy.ini                    # mypy 配置
├── README.md                   # 项目说明
├── ITERATION_TODO.md          # 迭代任务清单
└── background.md              # 本文档
```

---

## 🎨 代码风格和规范

### 类型注解

**要求**: 所有公共方法必须有类型注解

```python
async def search(
    self,
    query: str,
    max_results: int = 10,
    time_filter: Optional[str] = None
) -> List[Dict[str, str]]:
    """执行搜索"""
    pass
```

### 命名规范

- **类名**: PascalCase (`BrowserPool`, `WeixinSearcher`)
- **函数/方法名**: snake_case (`get_page`, `search_articles`)
- **常量**: UPPER_SNAKE_CASE (`CACHE_TTL`, `MAX_RETRIES`)
- **私有方法**: 前缀下划线 (`_load_config`, `_extract_item`)

### 文档字符串

**要求**: 所有公共类和方法必须有 docstring

```python
class BrowserPool:
    """
    浏览器池 - 单例模式
    
    核心改进：浏览器常驻，只创建新页面，性能提升5倍
    
    Attributes:
        browser: Playwright 浏览器实例
        context: 浏览器上下文
    """
```

### 错误处理

**原则**: 所有异常必须被捕获并适当处理

```python
try:
    results = await searcher.search(query)
except TimeoutError:
    logger.error(f"Search timeout: {query}")
    return []
except Exception as e:
    logger.error(f"Search failed: {e}")
    raise
```

---

## 📊 性能基准

### 目标性能指标

| 操作 | 原版本 | 优化版 | 提升 |
|------|--------|--------|------|
| 首次搜索 | 5.2s | 5.1s | - |
| 后续搜索 | 5.1s | 0.9s | **5.7x** |
| 并发 3 个 | 15.3s | 3.2s | **4.8x** |
| 缓存命中 | N/A | 0.01s | **∞** |

### 验收标准

- ✅ 搜索速度提升 3 倍+（相比原项目）
- ✅ 连续搜索 10 次无错误
- ✅ 单次搜索成功率 > 95%
- ✅ 带重试后成功率 > 99%
- ✅ 并发 5 个搜索无问题

---

## 🔗 参考资源

### 原项目

- **位置**: `/Users/z/Documents/github/weixin-search-playwright-mcp`
- **关键文件**:
  - `mcp_server.py`: MCP 协议实现
  - `app/search/playwright_search.py`: 搜索器实现

### 设计文档

- **完整设计**: `doc/vertical-search-mcp-design.md`
- **快速上手**: `doc/vertical-search-mcp-quickstart.md`
- **文档索引**: `doc/vertical-search-mcp-index.md`

### 迭代任务

- **任务清单**: `ITERATION_TODO.md`
- **本文档**: `background.md`

### 外部资源

- **Playwright 文档**: https://playwright.dev/python/
- **MCP 协议**: https://modelcontextprotocol.io/
- **pytest 文档**: https://docs.pytest.org/

---

## ⚠️ 重要注意事项

### 1. 依赖关系

**严格按迭代顺序执行，不能跳过！**

每个迭代都依赖前一个迭代的完成。

### 2. 测试优先

**每个迭代都要有对应的测试**

- 单元测试: 测试单个组件
- 集成测试: 测试组件协作
- 性能测试: 验证性能指标

### 3. 代码审查

**每个迭代完成后进行代码审查**

- 检查代码质量
- 验证测试覆盖率
- 确认性能指标

### 4. 文档同步

**代码和文档同步更新**

- API 变更时更新文档
- 添加新功能时更新示例
- 修复 bug 时更新故障排除指南

### 5. 性能监控

**从 Iteration 3 开始关注性能指标**

- 记录响应时间
- 监控成功率
- 检查缓存命中率

---

## 🚀 快速开始指南

### 1. 阅读本文档

了解项目背景、架构和设计理念。

### 2. 查看 ITERATION_TODO.md

了解当前迭代的具体任务和验收标准。

### 3. 参考原项目

理解原项目的实现细节，特别是：
- MCP 协议处理
- Playwright 使用方式
- 选择器策略

### 4. 开始编码

按照迭代任务清单，逐步实现功能。

### 5. 运行测试

每个功能完成后，立即运行测试验证。

---

## 📝 常见问题

### Q: 为什么使用 Playwright 而不是纯 HTTP？

**A**: Playwright 提供完整的浏览器指纹，反爬检测率低。搜狗微信搜索对纯 HTTP 返回 403。

### Q: 浏览器会一直运行吗？

**A**: 是的，浏览器常驻可大幅提升性能。可配置自动清理策略。

### Q: 如何接入新平台？

**A**: 复制 `BasePlatformSearcher` 模板，实现抽象方法，约 1-2 小时。

### Q: 支持代理吗？

**A**: 支持。在 `BrowserPool` 初始化时配置 proxy 参数。

### Q: 缓存会持久化吗？

**A**: 当前是内存缓存，不持久化。未来可扩展为 Redis 缓存。

---

**最后更新**: 2026-01-05  
**维护者**: jaxk  
**项目位置**: `/Users/z/Documents/dev/vertical_search_mcp`

