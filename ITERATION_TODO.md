# 垂直搜索 MCP 项目迭代开发 TODO

## 📋 项目概览

**项目目标**: 构建可扩展的垂直搜索 MCP，支持多平台（微信、知乎等）  
**技术栈**: Python 3.12+, Playwright, pytest  
**预计总时间**: 4-5 天（按文档）  
**代码质量要求**: 测试覆盖率 > 80%，类型注解完整

---

## 🔄 迭代规划

### Iteration 0: 项目初始化与环境搭建 (0.5 天)

**目标**: 搭建项目基础结构，配置开发环境

#### TODO 清单

- [x] **项目结构创建**
  - [x] 创建根目录 `vertical-search-mcp/`
  - [x] 创建 `core/` 目录（核心模块）
  - [x] 创建 `platforms/` 目录（平台适配器）
  - [x] 创建 `config/` 目录（配置文件）
  - [x] 创建 `tests/` 目录（测试文件）
  - [x] 创建 `docs/` 目录（文档）

- [x] **依赖管理**
  - [x] 创建 `requirements.txt`
  - [x] 创建 `requirements-dev.txt`（开发依赖）
  - [x] 创建 `pyproject.toml`（项目配置）
  - [x] 配置 `mypy.ini`（类型检查）
  - [x] 配置 `pytest.ini`（测试配置）

- [x] **基础文件**
  - [x] 创建 `README.md`
  - [x] 创建 `.gitignore`
  - [x] 创建 `LICENSE`
  - [x] 创建各模块的 `__init__.py`

- [x] **开发环境**
  - [x] 创建虚拟环境
  - [x] 安装依赖
  - [x] 安装 Playwright Chromium
  - [x] 验证环境可用

**验收标准**:
- ✅ 项目结构符合设计文档
- ✅ 所有依赖可正常安装
- ✅ Playwright 可正常启动浏览器
- ✅ 可以运行 `pytest --version`

**依赖**: 无

---

### Iteration 1: 核心架构 - 浏览器池与缓存 (1-1.5 天)

**目标**: 实现浏览器复用和缓存机制，为后续开发打基础

#### 执行阶段（按顺序）

**阶段1: BrowserPool 实现 (4小时)**

**实现参考**:

```python
# core/browser_pool.py

import asyncio
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from typing import Optional

class BrowserPool:
    """
    浏览器池 - 单例模式
    核心改进：浏览器常驻，只创建新页面，性能提升5倍
    """
    
    _instance: Optional['BrowserPool'] = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.playwright = None
            self.browser: Optional[Browser] = None
            self.context: Optional[BrowserContext] = None
            self.initialized = True
    
    async def init(self) -> None:
        """初始化浏览器 - 只调用一次"""
        async with self._lock:
            if self.browser:
                return
            
            self.playwright = await async_playwright().start()
            
            # 关键配置
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',  # Docker环境必需
                ]
            )
            
            self.context = await self.browser.new_context(
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='zh-CN',
                timezone_id='Asia/Shanghai',
            )
            
            # 请求拦截 - 性能提升30-50%
            await self.context.route("**/*", lambda route: (
                route.abort() if route.request.resource_type in [
                    "image", "media", "font", "stylesheet"
                ] else route.continue_()
            ))
    
    async def get_page(self) -> Page:
        """获取新页面（不是新浏览器）"""
        if not self.browser:
            await self.init()
        return await self.context.new_page()
    
    async def close(self) -> None:
        """清理资源"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        
        # 重置单例
        BrowserPool._instance = None
```

**TODO清单**:
- [x] 创建 `core/browser_pool.py`，定义类结构和方法签名
- [x] 实现单例模式（使用 `__new__` 方法）
- [x] 实现 `init()` 方法，使用 `asyncio.Lock` 保证线程安全
- [x] 实现 `get_page()` 方法，复用浏览器实例，只创建新页面
- [x] 实现 `close()` 方法，优雅关闭并释放资源
- [x] 配置浏览器启动参数（参考上面代码）
- [x] 配置 Context（user-agent, viewport, locale）
- [x] 实现请求拦截器，禁用图片、字体、样式表

**阶段2: SearchCache 实现 (2小时)**

**实现参考**:

```python
# core/cache.py

import time
from typing import Any, Optional, Tuple
import hashlib
import json

class SearchCache:
    """
    简单的内存缓存
    特点：
    - TTL 过期机制
    - 自动清理
    """
    
    def __init__(self, ttl: int = 300):
        self.cache: dict[str, Tuple[Any, float]] = {}
        self.ttl = ttl
    
    def _generate_key(self, platform: str, query: str, params: dict) -> str:
        """生成缓存键"""
        params_str = json.dumps(params, sort_keys=True)
        key_str = f"{platform}:{query}:{params_str}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return value
            else:
                del self.cache[key]
        return None
    
    def set(self, key: str, value: Any) -> None:
        """设置缓存值"""
        self.cache[key] = (value, time.time())
    
    def clear(self) -> None:
        """清理所有缓存"""
        self.cache.clear()
```

**TODO清单**:
- [x] 创建 `core/cache.py`
- [x] 实现 `get(key)` / `set(key, value)` / `clear()` 方法
- [x] 实现 TTL 过期机制（在 get 时检查时间戳）
- [x] 实现缓存键生成逻辑: `f"{platform}:{query}:{hash(params)}"`

**阶段3: 单元测试 (2小时)**
- [x] 创建 `tests/unit/test_browser_pool.py`
- [x] 测试浏览器单例模式（多次初始化只创建一个浏览器）
- [x] 测试页面创建性能（应 < 1秒）
- [x] 测试并发安全性
- [x] 创建 `tests/unit/test_cache.py`
- [x] 测试缓存 CRUD 和 TTL 过期

#### ⚠️ 风险预警

**风险1: Playwright 安装失败**
- **触发条件**: 网络问题或系统依赖缺失
- **影响**: 无法初始化浏览器，项目无法进行
- **应对策略**: 
  - 使用国内镜像: `PLAYWRIGHT_DOWNLOAD_HOST=https://playwright.azureedge.net playwright install chromium`
  - 准备离线安装包
  - 检查系统依赖: `playwright install-deps chromium`

**风险2: 浏览器初始化耗时过长**
- **触发条件**: 系统资源不足或配置不当
- **影响**: 首次搜索超时，用户体验差
- **应对策略**: 
  - 在服务启动时预初始化浏览器
  - 添加初始化超时检测（> 10秒报警）
  - 考虑使用 `persistent_context` 进一步加速

**风险3: 单例模式线程安全问题**
- **触发条件**: 多线程/多协程并发初始化
- **影响**: 可能创建多个浏览器实例，资源浪费
- **应对策略**: 
  - 使用 `asyncio.Lock` 保证初始化原子性
  - 添加单元测试验证并发安全性

**验收标准**:

- ✅ **浏览器池可正常初始化和复用** ✅ 已完成
  - 测量命令: `pytest tests/unit/test_browser_pool.py::test_browser_singleton -v`
  - 预期结果: 测试通过，日志显示只初始化一次浏览器
  - 实际结果: ✅ 测试通过，单例模式正常工作

- ✅ **创建新页面时间 < 1 秒（浏览器已存在时）** ✅ 已完成
  - 测量命令: `pytest tests/unit/test_browser_pool.py::test_page_creation_time -v`
  - 预期结果: `assert elapsed < 1.0` 通过
  - 实际结果: ✅ 页面创建时间 < 1 秒，性能达标

- ✅ **缓存可正常存储和读取** ✅ 已完成
  - 测量命令: `pytest tests/unit/test_cache.py::test_cache_basic -v`
  - 预期结果: 所有 get/set 测试通过
  - 实际结果: ✅ 所有 CRUD 操作测试通过

- ✅ **缓存 TTL 机制工作正常** ✅ 已完成
  - 测量命令: `pytest tests/unit/test_cache.py::test_cache_ttl -v`
  - 预期结果: 过期条目返回 None
  - 实际结果: ✅ TTL 过期机制正常工作

- ✅ **单元测试覆盖率 > 90%** ✅ 已完成
  - 测量命令: `pytest tests/unit/ --cov=core --cov-report=term-missing`
  - 预期结果: 终端显示 `TOTAL ... 90%` 以上
  - 实际结果: ✅ 覆盖率 93%，超过目标

- ✅ **所有测试通过** ✅ 已完成
  - 测量命令: `pytest tests/unit/ -v`
  - 预期结果: 无失败、无跳过
  - 实际结果: ✅ 21 个测试全部通过

**依赖**: Iteration 0

**完成时间**: 2026-01-05

**额外完成**:
- ✅ 创建了 Makefile，支持便捷的测试命令
- ✅ 所有代码包含完整的类型注解和文档字符串
- ✅ 代码质量符合项目规范

---

### Iteration 2: 核心架构 - 基类与管理器 (0.5 天)

**目标**: 实现平台抽象基类和统一管理器

#### 执行阶段（按顺序）

**阶段1: BasePlatformSearcher 实现 (2小时)**

**实现参考**:

```python
# core/base_searcher.py

from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from core.browser_pool import BrowserPool
from playwright.async_api import Page

class BasePlatformSearcher(ABC):
    """
    平台搜索器基类
    所有平台搜索器必须继承此类并实现抽象方法
    """
    
    def __init__(self, browser_pool: BrowserPool):
        self.browser_pool = browser_pool
        self.config: Dict = {}
    
    @abstractmethod
    def _load_config(self) -> Dict:
        """加载平台配置（从YAML或代码）"""
        pass
    
    @abstractmethod
    async def search(self, query: str, max_results: int = 10, **kwargs) -> List[Dict]:
        """执行搜索"""
        pass
    
    @abstractmethod
    async def _extract_item(self, element, index: int) -> Optional[Dict]:
        """从DOM元素提取单个结果项"""
        pass
    
    def _sanitize_query(self, query: str) -> str:
        """清理搜索查询"""
        import re
        query = re.sub(r'[<>"\']', '', query)
        return query.strip()[:100]
    
    def _clean_text(self, text: str) -> str:
        """清理文本"""
        if not text:
            return ""
        import re
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    async def _parse_results(self, page: Page, max_results: int) -> List[Dict]:
        """通用结果解析方法"""
        results = []
        selectors = self.config.get('selectors', {}).get('article_list', [])
        
        for selector in selectors:
            elements = await page.query_selector_all(selector)
            if elements:
                for i, element in enumerate(elements[:max_results]):
                    item = await self._extract_item(element, i)
                    if item:
                        results.append(item)
                break
        
        return results[:max_results]
```

**TODO清单**:
- [x] 创建 `core/base_searcher.py`
- [x] 定义抽象基类（继承 ABC）
- [x] 定义抽象方法：`search()`, `_load_config()`, `_extract_item()`
- [x] 实现通用方法：`_parse_results()`, `_sanitize_query()`, `_clean_text()`
- [x] 添加完整的类型注解

**阶段2: UnifiedSearchManager 实现 (2小时)**

**实现参考**:

```python
# core/search_manager.py

from typing import Dict, List, Optional
from core.browser_pool import BrowserPool
from core.cache import SearchCache
from core.base_searcher import BasePlatformSearcher
import logging

class UnifiedSearchManager:
    """
    统一搜索管理器
    负责平台路由、缓存管理、错误处理
    """
    
    def __init__(self):
        self.browser_pool = BrowserPool()
        self.cache = SearchCache(ttl=300)
        self.searchers: Dict[str, BasePlatformSearcher] = {}
        self.logger = logging.getLogger(__name__)
    
    def register_platform(self, platform: str, searcher: BasePlatformSearcher):
        """注册平台搜索器"""
        self.searchers[platform] = searcher
        self.logger.info(f"Platform '{platform}' registered")
    
    async def search(
        self,
        platform: str,
        query: str,
        max_results: int = 10,
        time_filter: Optional[str] = None,
        use_cache: bool = True
    ) -> List[Dict]:
        """执行搜索"""
        # 检查缓存
        if use_cache:
            cache_key = self.cache._generate_key(platform, query, {
                'max_results': max_results,
                'time_filter': time_filter
            })
            cached = self.cache.get(cache_key)
            if cached:
                self.logger.info(f"Cache hit for {platform}:{query}")
                return cached
        
        # 路由到对应平台
        if platform not in self.searchers:
            raise ValueError(f"Platform '{platform}' not registered")
        
        searcher = self.searchers[platform]
        
        # 执行搜索
        try:
            results = await searcher.search(
                query=query,
                max_results=max_results,
                time_filter=time_filter
            )
            
            # 缓存结果
            if use_cache:
                self.cache.set(cache_key, results)
            
            return results
        except Exception as e:
            self.logger.error(f"Search failed for {platform}:{query}: {e}")
            raise
```

**TODO清单**:
- [x] 创建 `core/search_manager.py`
- [x] 实现管理器类，集成 BrowserPool 和 SearchCache
- [x] 实现平台注册机制 `register_platform()`
- [x] 实现 `search()` 方法（路由到对应平台）
- [x] 实现缓存检查逻辑（先查缓存，再执行搜索）
- [x] 实现错误处理和日志记录

**阶段3: 配置文件 (1小时)**
- [x] 创建 `config/platforms.yaml`
- [x] 定义 YAML 配置格式
- [x] 添加微信平台配置模板
- [x] 实现配置加载和验证逻辑

**阶段4: 单元测试 (1小时)**
- [x] 创建 `tests/unit/test_base_searcher.py`
- [x] 测试抽象基类接口
- [x] 创建 `tests/unit/test_search_manager.py`
- [x] 测试平台注册机制
- [x] 测试路由和缓存集成

#### ⚠️ 风险预警

**风险1: 配置加载失败**
- **触发条件**: YAML 文件格式错误或路径不正确
- **影响**: 平台搜索器无法初始化
- **应对策略**: 
  - 添加配置验证逻辑
  - 提供默认配置
  - 添加详细的错误提示

**风险2: 平台注册顺序问题**
- **触发条件**: 在浏览器池初始化前注册平台
- **影响**: 搜索时浏览器未就绪
- **应对策略**: 
  - 在管理器初始化时预初始化浏览器池
  - 添加延迟初始化机制

**验收标准**:

- ✅ **基类接口定义清晰** ✅ 已完成
  - 测量命令: `mypy core/base_searcher.py --strict`
  - 预期结果: 类型检查通过，所有抽象方法正确定义
  - 实际结果: ✅ 类型检查通过，所有抽象方法正确定义

- ✅ **管理器可正确路由请求** ✅ 已完成
  - 测量命令: `pytest tests/unit/test_search_manager.py::test_search_basic -v`
  - 预期结果: 测试通过，请求正确路由到对应平台
  - 实际结果: ✅ 测试通过，请求正确路由到对应平台

- ✅ **缓存机制集成正常** ✅ 已完成
  - 测量命令: `pytest tests/unit/test_search_manager.py::test_search_with_cache -v`
  - 预期结果: 测试通过，缓存命中时直接返回
  - 实际结果: ✅ 测试通过，缓存命中时直接返回

- ✅ **配置可正常加载** ✅ 已完成
  - 测量方法: 检查 `config/platforms.yaml` 文件存在且格式正确
  - 预期结果: 配置文件存在，包含微信平台配置
  - 实际结果: ✅ 配置文件已创建，包含完整的微信平台配置

- ✅ **单元测试通过** ✅ 已完成
  - 测量命令: `pytest tests/unit/ -v`
  - 预期结果: 无失败、无跳过
  - 实际结果: ✅ 40 个测试全部通过

- ✅ **类型检查通过** ✅ 已完成
  - 测量命令: `mypy core/ platforms/ --strict`
  - 预期结果: 无类型错误
  - 实际结果: ✅ 所有类型检查通过

- ✅ **代码质量检查通过** ✅ 已完成
  - 测量命令: `flake8 core/ platforms/ tests/ --max-line-length=100`
  - 预期结果: 无 lint 错误
  - 实际结果: ✅ 所有 lint 检查通过

- ✅ **测试覆盖率达标** ✅ 已完成
  - 测量命令: `pytest tests/unit/ --cov=core --cov-report=term-missing`
  - 预期结果: 覆盖率 > 80%
  - 实际结果: ✅ 覆盖率 88%，超过目标

**依赖**: Iteration 1

**完成时间**: 2026-01-05

**额外完成**:
- ✅ 所有代码包含完整的类型注解和文档字符串
- ✅ 代码质量符合项目规范
- ✅ 所有验收标准均已达成

---

### Iteration 3: 微信搜索重构 (1-1.5 天)

**目标**: 将原项目微信搜索逻辑重构到新架构

#### 性能基准测试设计

**测试1: 对比原项目性能**

```python
# tests/benchmark/test_weixin_performance.py

import time
import sys
import pytest
sys.path.append('/Users/z/Documents/github/weixin-search-playwright-mcp')
from app.search.playwright_search import WeChatArticleSearcher as OriginalSearcher

from core.browser_pool import BrowserPool
from platforms.weixin_searcher import WeixinSearcher

@pytest.mark.asyncio
async def test_compare_with_original():
    """对比原项目性能"""
    
    # 原项目测试
    original = OriginalSearcher()
    await original.__aenter__()
    try:
        start1 = time.time()
        results1 = await original.search_articles("Python", max_results=5)
        time_original = time.time() - start1
    finally:
        await original.__aexit__(None, None, None)
    
    # 新项目测试（首次）
    pool = BrowserPool()
    searcher = WeixinSearcher(pool)
    start2 = time.time()
    results2 = await searcher.search("Python", max_results=5)
    time_new_first = time.time() - start2
    
    # 新项目测试（第二次，浏览器已启动）
    start3 = time.time()
    results3 = await searcher.search("AI", max_results=5)
    time_new_second = time.time() - start3
    
    print(f"\n性能对比:")
    print(f"原项目: {time_original:.2f}s")
    print(f"新项目(首次): {time_new_first:.2f}s")
    print(f"新项目(第二次): {time_new_second:.2f}s")
    print(f"提升倍数: {time_original / time_new_second:.2f}x")
    
    # 验收标准
    assert time_new_second < time_original / 3, f"速度提升未达到3倍: {time_original / time_new_second:.2f}x"
    
    await pool.close()
```

**测试2: 连续搜索稳定性**

```python
@pytest.mark.asyncio
async def test_continuous_search():
    """连续搜索10次无错误"""
    pool = BrowserPool()
    searcher = WeixinSearcher(pool)
    
    try:
        for i in range(10):
            results = await searcher.search(f"测试{i}", max_results=5)
            assert len(results) > 0, f"第{i+1}次搜索失败"
            assert all('title' in r for r in results), f"第{i+1}次搜索结果格式错误"
    finally:
        await pool.close()
```

**测试3: 缓存效果验证**

```python
@pytest.mark.asyncio
async def test_cache_effectiveness():
    """验证缓存效果"""
    from core.search_manager import UnifiedSearchManager
    
    manager = UnifiedSearchManager()
    manager.register_platform('weixin', WeixinSearcher(manager.browser_pool))
    
    # 第一次搜索（无缓存）
    start1 = time.time()
    results1 = await manager.search('weixin', 'Python', max_results=5, use_cache=False)
    time_no_cache = time.time() - start1
    
    # 第二次搜索（有缓存）
    start2 = time.time()
    results2 = await manager.search('weixin', 'Python', max_results=5, use_cache=True)
    time_with_cache = time.time() - start2
    
    print(f"\n缓存效果:")
    print(f"无缓存: {time_no_cache:.2f}s")
    print(f"有缓存: {time_with_cache:.2f}s")
    print(f"加速比: {time_no_cache / time_with_cache:.2f}x")
    
    assert time_with_cache < 0.01, "缓存响应时间应 < 0.01s"
    assert results1 == results2, "缓存结果应与原结果一致"
    
    await manager.browser_pool.close()
```

#### 执行阶段（按顺序）

**阶段1: WeixinSearcher 实现 (4小时)**

**实现参考**:

```python
# platforms/weixin_searcher.py

from typing import List, Dict, Optional
from core.base_searcher import BasePlatformSearcher
from core.browser_pool import BrowserPool
from playwright.async_api import Page
import yaml
from urllib.parse import urlencode

class WeixinSearcher(BasePlatformSearcher):
    """微信搜索器"""
    
    def __init__(self, browser_pool: BrowserPool):
        super().__init__(browser_pool)
        self.config = self._load_config()
        self.base_url = self.config['base_url']
    
    def _load_config(self) -> Dict:
        """从YAML加载配置"""
        with open('config/platforms.yaml', 'r', encoding='utf-8') as f:
            configs = yaml.safe_load(f)
        return configs['weixin']
    
    async def search(
        self,
        query: str,
        max_results: int = 10,
        time_filter: Optional[str] = None
    ) -> List[Dict]:
        """执行微信搜索"""
        query = self._sanitize_query(query)
        
        # 构建搜索URL
        params = {
            'query': query,
            'type': '2',
            'ie': 'utf8'
        }
        
        if time_filter:
            time_code = self.config['time_filters'].get(time_filter)
            if time_code:
                params['tsn'] = time_code
        
        url = f"{self.base_url}?{urlencode(params)}"
        
        # 获取页面
        page = await self.browser_pool.get_page()
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            
            # 等待搜索结果加载
            selectors = self.config['selectors']['article_list']
            page_loaded = False
            for selector in selectors:
                try:
                    await page.wait_for_selector(selector, timeout=10000)
                    page_loaded = True
                    break
                except:
                    continue
            
            if not page_loaded:
                return []
            
            # 解析结果
            return await self._parse_results(page, max_results)
        finally:
            await page.close()
    
    async def _extract_item(self, element, index: int) -> Optional[Dict]:
        """提取单个文章信息"""
        try:
            title_elem = await element.query_selector("a")
            if not title_elem:
                return None
            
            title = await title_elem.inner_text()
            link = await title_elem.get_attribute("href")
            
            if not title or not link:
                return None
            
            # 查找父容器获取更多信息
            parent = await element.evaluate_handle("el => el.closest('li')")
            if parent:
                # 获取描述、来源、时间等
                # ... 实现细节
                pass
            
            return {
                'title': self._clean_text(title),
                'url': self._resolve_url(link),
                'source': '微信公众号',
                'date': '',  # 从页面解析
                'snippet': ''  # 从页面解析
            }
        except Exception as e:
            return None
```

**TODO清单**:
- [x] 创建 `platforms/weixin_searcher.py`
- [x] 继承 BasePlatformSearcher
- [x] 实现 `_load_config()`（从 YAML 加载）
- [x] 实现 `search()` 方法
- [x] 实现 `_extract_item()` 方法
- [x] 迁移原项目的多重选择器策略
- [x] 迁移原项目的时间筛选逻辑
- [x] 迁移原项目的元信息解析
- [x] 使用 BrowserPool 而非直接创建浏览器
- [x] 添加错误处理
- [x] 优化等待策略（选择器超时从 10s 降到 2s）

**阶段2: 配置完善 (1小时)**
- [x] 完善 `config/platforms.yaml` 中的微信平台配置
- [x] 配置选择器列表（多重备用）
- [x] 配置 URL 参数
- [x] 配置时间筛选映射

**阶段3: 集成测试 (2小时)**
- [x] 创建 `tests/integration/test_weixin_search.py`
- [x] 测试基本搜索功能
- [x] 测试时间筛选
- [x] 测试结果解析
- [x] 测试错误处理
- [x] 测试浏览器复用效果

**阶段4: 性能验证 (1小时)**
- [x] 创建性能基准测试（复制上面代码）
- [x] 运行对比测试，记录基准数据
- [x] 验证速度提升（优化后从 10s 降到 ~3s）
- [x] 验证缓存效果
- [x] 创建性能诊断工具

#### ⚠️ 风险预警

**风险1: 页面结构变化导致选择器失效**
- **触发条件**: 搜狗微信页面改版
- **影响**: 搜索结果解析失败
- **应对策略**: 
  - 使用多重备用选择器
  - 添加选择器有效性检测
  - 定期检查页面结构

**风险2: 反爬虫检测**
- **触发条件**: 请求频率过高或行为异常
- **影响**: IP被封或返回验证码
- **应对策略**: 
  - 控制请求频率
  - 使用随机延迟
  - 添加User-Agent轮换

**风险3: 性能提升未达预期**
- **触发条件**: 浏览器池未正确复用或缓存未生效
- **影响**: 性能提升不明显
- **应对策略**: 
  - 检查浏览器池单例模式
  - 验证缓存键生成逻辑
  - 添加性能监控日志

**验收标准**:

- ✅ **微信搜索功能完全正常**
  - 测量命令: `pytest tests/integration/test_weixin_search.py::test_basic_search -v`
  - 预期结果: 测试通过，返回有效搜索结果

- ✅ **搜索速度提升 3 倍+（相比原项目）**
  - 测量命令: `pytest tests/benchmark/test_weixin_performance.py::test_compare_with_original -v -s`
  - 预期结果: 终端显示提升倍数 >= 3.0x

- ✅ **连续搜索 10 次无错误**
  - 测量命令: `pytest tests/benchmark/test_weixin_performance.py::test_continuous_search -v`
  - 预期结果: 所有搜索成功，无异常

- ✅ **结果格式与原项目一致**
  - 测量命令: `pytest tests/integration/test_weixin_search.py::test_result_format -v`
  - 预期结果: 结果包含 title, url, source, date, snippet 字段

- ✅ **集成测试通过**
  - 测量命令: `pytest tests/integration/test_weixin_search.py -v`
  - 预期结果: 无失败、无跳过

**依赖**: Iteration 2

**性能基准**:
- 首次搜索: ~5s
- 后续搜索: <1s
- 缓存命中: <0.01s

---

### Iteration 4: 知乎平台集成 (1 天)

**目标**: 验证架构扩展性，实现知乎搜索

#### 执行阶段（按顺序）

**阶段1: 研究搜狗知乎页面结构 (1小时)**
- [ ] 访问 zhihu.sogou.com
- [ ] 分析搜索结果页面结构
- [ ] 识别选择器（使用浏览器开发者工具）
- [ ] 分析 URL 参数
- [ ] 记录页面特点（与微信对比）

**阶段2: ZhihuSearcher 实现 (2小时)**
- [ ] 创建 `platforms/zhihu_searcher.py`
- [ ] 继承 BasePlatformSearcher
- [ ] 实现 `_load_config()`（参考 WeixinSearcher）
- [ ] 实现 `search()` 方法
- [ ] 实现 `_extract_item()` 方法
- [ ] 配置知乎特定的选择器
- [ ] 处理知乎特定的数据格式

**阶段3: 配置和注册 (0.5小时)**
- [ ] 在 `config/platforms.yaml` 中添加知乎平台配置
- [ ] 配置知乎选择器
- [ ] 配置知乎 URL 参数
- [ ] 在管理器中注册知乎平台

**阶段4: 测试验证 (0.5小时)**
- [ ] 创建 `tests/integration/test_zhihu_search.py`
- [ ] 测试知乎搜索功能
- [ ] 测试结果解析
- [ ] 测试与微信搜索共存
- [ ] 测试两个平台并发搜索

#### ⚠️ 风险预警

**风险1: 页面结构与预期不符**
- **触发条件**: 知乎页面结构与微信差异较大
- **影响**: 需要更多时间调整选择器
- **应对策略**: 
  - 预留额外时间（最多+1小时）
  - 使用更通用的选择器策略

**风险2: 新平台接入时间超预期**
- **触发条件**: 页面结构复杂或选择器难以定位
- **影响**: 无法在2小时内完成
- **应对策略**: 
  - 记录实际耗时，分析瓶颈
  - 优化基类通用方法
  - 提供更详细的接入文档

**验收标准**:

- ✅ **知乎搜索功能正常**
  - 测量命令: `pytest tests/integration/test_zhihu_search.py::test_basic_search -v`
  - 预期结果: 测试通过，返回有效搜索结果

- ✅ **新平台接入时间 < 2 小时（从研究到完成）**
  - 测量方法: 记录开始和结束时间
  - 预期结果: 总耗时 < 2 小时

- ✅ **两个平台可并发使用**
  - 测量命令: `pytest tests/integration/test_zhihu_search.py::test_concurrent_platforms -v`
  - 预期结果: 两个平台同时搜索成功

- ✅ **结果格式统一**
  - 测量命令: `pytest tests/integration/test_zhihu_search.py::test_result_format -v`
  - 预期结果: 结果包含 title, url, source, date, snippet 字段

- ✅ **所有测试通过**
  - 测量命令: `pytest tests/integration/test_zhihu_search.py -v`
  - 预期结果: 无失败、无跳过

**依赖**: Iteration 3

**扩展性验证**:
- 新平台接入时间: < 2 小时
- 代码复用率: > 80%

---

### Iteration 5: MCP 服务器集成 (0.5 天)

**目标**: 集成 MCP 协议，使 Claude 可调用

#### 执行阶段（按顺序）

**阶段1: MCP Server 实现 (3小时)**
- [ ] 创建 `mcp_server.py`
- [ ] 参考原项目 MCP 实现
- [ ] 实现 JSON-RPC 2.0 协议
- [ ] 实现 `handle_initialize()`
- [ ] 实现 `handle_list_tools()`
- [ ] 实现 `handle_call_tool()`
- [ ] 集成 UnifiedSearchManager
- [ ] 实现工具：`search_vertical`
- [ ] 实现结果格式化
- [ ] 实现错误处理

**阶段2: 工具定义和测试 (1小时)**
- [ ] 定义 `search_vertical` 工具 schema
- [ ] 支持 platform 参数（weixin, zhihu）
- [ ] 支持 query, max_results, time_filter
- [ ] 添加参数验证
- [ ] 创建 `tests/integration/test_mcp_server.py`
- [ ] 测试 MCP 协议处理
- [ ] 测试工具调用
- [ ] 测试错误响应

**阶段3: 文档更新 (0.5小时)**
- [ ] 更新 README
- [ ] 添加 MCP 配置示例
- [ ] 添加使用说明

#### ⚠️ 风险预警

**风险1: MCP 协议版本不兼容**
- **触发条件**: Claude Desktop 使用不同版本的 MCP 协议
- **影响**: 无法正常通信
- **应对策略**: 
  - 参考原项目实现，保持兼容
  - 测试多个版本的 Claude Desktop

**风险2: 参数验证失败**
- **触发条件**: Claude 传入无效参数
- **影响**: 搜索失败或返回错误
- **应对策略**: 
  - 添加严格的参数验证
  - 提供清晰的错误信息

**验收标准**:

- ✅ **MCP 服务器可正常启动**
  - 测量命令: `python mcp_server.py` (检查无错误)
  - 预期结果: 服务器启动成功，输出初始化信息

- ✅ **Claude 可正常调用工具**
  - 测量方法: 在 Claude Desktop 中测试调用
  - 预期结果: 工具调用成功，返回搜索结果

- ✅ **搜索结果正确返回**
  - 测量命令: `pytest tests/integration/test_mcp_server.py::test_tool_call -v`
  - 预期结果: 测试通过，返回格式正确

- ✅ **错误信息清晰**
  - 测量命令: `pytest tests/integration/test_mcp_server.py::test_error_handling -v`
  - 预期结果: 错误信息包含原因和解决建议

- ✅ **集成测试通过**
  - 测量命令: `pytest tests/integration/test_mcp_server.py -v`
  - 预期结果: 无失败、无跳过

**依赖**: Iteration 4

---

### Iteration 6: 稳定性与错误处理 (1 天)

**目标**: 提升生产级可靠性

#### 执行阶段（按顺序）

**阶段1: 错误处理增强 (2小时)**
- [ ] 实现重试机制（最多 3 次）
- [ ] 实现指数退避策略
- [ ] 添加超时处理
- [ ] 添加网络错误处理
- [ ] 添加页面解析错误处理
- [ ] 实现优雅降级

**阶段2: 日志系统 (2小时)**
- [ ] 创建 `core/logger.py`
- [ ] 配置日志格式
- [ ] 添加日志级别（DEBUG, INFO, WARNING, ERROR）
- [ ] 记录搜索请求和响应
- [ ] 记录性能指标
- [ ] 记录错误详情

**阶段3: 性能监控 (2小时)**
- [ ] 创建 `core/metrics.py`
- [ ] 记录响应时间
- [ ] 记录成功率
- [ ] 记录缓存命中率
- [ ] 记录浏览器池状态
- [ ] 实现简单的统计接口

**阶段3.5: 反爬虫应对策略 (2小时)**
- [ ] 实现 User-Agent 轮换机制
  - [ ] 在 `core/browser_pool.py` 中添加 User-Agent 池
  - [ ] 实现随机选择 User-Agent 的逻辑
  - [ ] 支持配置自定义 User-Agent 列表
- [ ] 实现随机延迟机制
  - [ ] 在 `platforms/weixin_searcher.py` 的 `search()` 方法中添加延迟
  - [ ] 使用随机延迟（例如 1-3 秒）避免请求过于频繁
  - [ ] 支持配置延迟范围
- [ ] 实现请求频率控制
  - [ ] 创建 `core/rate_limiter.py` 限流器
  - [ ] 实现基于时间的请求频率限制（例如每分钟最多 N 次）
  - [ ] 在 `core/search_manager.py` 中集成限流器
  - [ ] 支持配置请求频率限制参数
- [ ] 添加反爬虫检测和响应
  - [ ] 检测验证码页面
  - [ ] 检测 IP 封禁提示
  - [ ] 实现自动延迟和重试机制
  - [ ] 记录反爬虫事件到日志

**阶段4: 压力测试 (2小时)**
- [ ] 创建 `tests/load/test_concurrent.py`
- [ ] 测试并发 5 个搜索
- [ ] 测试并发 10 个搜索
- [ ] 测试长时间运行（1 小时）
- [ ] 测试内存泄漏
- [ ] 测试浏览器稳定性

**阶段5: 文档完善 (0.5小时)**
- [ ] 添加错误处理文档
- [ ] 添加故障排除指南
- [ ] 添加性能调优指南
- [ ] 添加反爬虫应对策略配置说明

#### ⚠️ 风险预警

**风险1: 重试机制导致性能下降**
- **触发条件**: 网络不稳定，频繁重试
- **影响**: 响应时间增加
- **应对策略**: 
  - 使用指数退避，避免频繁重试
  - 设置合理的超时时间
  - 监控重试率

**风险2: 日志文件过大**
- **触发条件**: 高频搜索产生大量日志
- **影响**: 磁盘空间不足
- **应对策略**: 
  - 使用日志轮转
  - 设置日志级别过滤
  - 定期清理旧日志

**风险3: 并发测试失败**
- **触发条件**: 浏览器池并发能力不足
- **影响**: 高并发场景不稳定
- **应对策略**: 
  - 增加浏览器池大小
  - 实现请求队列
  - 添加并发限制

**风险4: 反爬虫检测触发**
- **触发条件**: 请求频率过高或行为异常
- **影响**: IP被封或返回验证码
- **应对策略**: 
  - 实现 User-Agent 轮换（阶段3.5）
  - 实现随机延迟（阶段3.5）
  - 实现请求频率控制（阶段3.5）
  - 检测并响应反爬虫事件（阶段3.5）

**验收标准**:

- ✅ **单次搜索成功率 > 95%**
  - 测量命令: `pytest tests/load/test_concurrent.py::test_success_rate -v`
  - 预期结果: 成功率 >= 95%

- ✅ **带重试后成功率 > 99%**
  - 测量命令: `pytest tests/load/test_concurrent.py::test_retry_success_rate -v`
  - 预期结果: 成功率 >= 99%

- ✅ **错误信息清晰可追踪**
  - 测量方法: 检查日志文件
  - 预期结果: 错误包含堆栈信息和上下文

- ✅ **并发 5 个搜索无问题**
  - 测量命令: `pytest tests/load/test_concurrent.py::test_concurrent_5 -v`
  - 预期结果: 所有搜索成功完成

- ✅ **日志完整可查**
  - 测量方法: 检查日志文件内容
  - 预期结果: 包含请求、响应、错误信息

- ✅ **压力测试通过**
  - 测量命令: `pytest tests/load/ -v`
  - 预期结果: 无失败、无内存泄漏

- ✅ **反爬虫应对策略生效**
  - 测量方法: 检查 User-Agent 是否轮换
  - 测量方法: 验证请求之间有延迟
  - 测量方法: 验证请求频率被限制
  - 预期结果: 所有策略正常工作，无 IP 封禁

**依赖**: Iteration 5

---

### Iteration 7: 测试完善与代码质量 (0.5 天)

**目标**: 确保代码质量和测试覆盖率

#### 执行阶段（按顺序）

**阶段1: 测试覆盖率提升 (2小时)**
- [ ] 检查当前覆盖率: `pytest --cov=. --cov-report=term-missing`
- [ ] 补充单元测试（目标 > 80%）
- [ ] 补充集成测试
- [ ] 补充边界测试
- [ ] 补充错误场景测试

**阶段2: 类型检查 (1小时)**
- [ ] 为所有函数添加类型注解
- [ ] 运行 mypy 检查: `mypy core/ platforms/ --strict`
- [ ] 修复所有类型错误
- [ ] 配置 strict 模式

**阶段3: 代码规范 (1小时)**
- [ ] 运行 black 格式化: `black core/ platforms/`
- [ ] 运行 flake8 检查: `flake8 core/ platforms/ --max-line-length=100`
- [ ] 修复所有 lint 错误
- [ ] 添加 pre-commit hooks

**阶段4: 文档完善 (0.5小时)**
- [ ] API 文档（docstring）
- [ ] 架构文档
- [ ] 使用示例
- [ ] 贡献指南

**阶段5: CI/CD 准备 (0.5小时)**
- [ ] 创建 `.github/workflows/ci.yml`
- [ ] 配置自动测试
- [ ] 配置代码质量检查
- [ ] 配置覆盖率报告

#### ⚠️ 风险预警

**风险1: 测试覆盖率难以达到 80%**
- **触发条件**: 某些代码路径难以测试
- **影响**: 覆盖率不达标
- **应对策略**: 
  - 重构代码提高可测试性
  - 使用 mock 覆盖边界情况
  - 考虑降低覆盖率要求（但需说明原因）

**风险2: 类型检查错误过多**
- **触发条件**: 代码缺少类型注解或类型不匹配
- **影响**: 无法通过类型检查
- **应对策略**: 
  - 逐步添加类型注解
  - 使用 `# type: ignore` 标记暂时无法修复的
  - 配置 mypy 为渐进式检查

**验收标准**:

- ✅ **测试覆盖率 > 80%**
  - 测量命令: `pytest --cov=. --cov-report=html --cov-report=term-missing`
  - 预期结果: 终端显示 `TOTAL ... 80%` 以上

- ✅ **所有类型检查通过**
  - 测量命令: `mypy core/ platforms/ --strict`
  - 预期结果: 无错误输出

- ✅ **所有 lint 检查通过**
  - 测量命令: `flake8 core/ platforms/ --max-line-length=100`
  - 预期结果: 无错误输出

- ✅ **文档完整**
  - 测量方法: 检查所有模块的 docstring
  - 预期结果: 所有公共 API 都有文档

- ✅ **CI/CD 配置完成**
  - 测量方法: 检查 `.github/workflows/ci.yml` 文件
  - 预期结果: CI 配置完整，可正常运行

**依赖**: Iteration 6

---

## 📊 迭代时间表

| 迭代 | 名称 | 预计时间 | 优先级 | 状态 |
|------|------|----------|--------|------|
| Iteration 0 | 项目初始化 | 0.5 天 | P0 | ✅ 已完成 |
| Iteration 1 | 浏览器池与缓存 | 1-1.5 天 | P0 | ✅ 已完成 |
| Iteration 2 | 基类与管理器 | 0.5 天 | P0 | ✅ 已完成 |
| Iteration 3 | 微信搜索重构 | 1-1.5 天 | P0 | ⬜ 未开始 |
| Iteration 4 | 知乎平台集成 | 1 天 | P1 | ⬜ 未开始 |
| Iteration 5 | MCP 服务器集成 | 0.5 天 | P0 | ⬜ 未开始 |
| Iteration 6 | 稳定性与错误处理 | 1 天 | P1 | ⬜ 未开始 |
| Iteration 7 | 测试完善与代码质量 | 0.5 天 | P1 | ⬜ 未开始 |

**总计**: 5.5-7 天

---

## 🎯 里程碑

### Milestone 1: 核心架构完成 (Iteration 0-2)
- ✅ 项目结构搭建完成
- ✅ 浏览器池和缓存实现完成
- ✅ 基类和管理器实现完成

### Milestone 2: 功能可用 (Iteration 3-5)
- ✅ 微信搜索功能正常
- ✅ 知乎搜索功能正常
- ✅ MCP 服务器可调用

### Milestone 3: 生产就绪 (Iteration 6-7)
- ✅ 稳定性达到生产级
- ✅ 测试覆盖率达标
- ✅ 代码质量达标

---

## 📝 注意事项

1. **依赖关系**: 严格按照迭代顺序执行，不能跳过
2. **测试优先**: 每个迭代都要有对应的测试
3. **代码审查**: 每个迭代完成后进行代码审查
4. **文档同步**: 代码和文档同步更新
5. **性能监控**: 从 Iteration 3 开始关注性能指标

---

## 🔄 迭代回顾

每个迭代结束后，进行：
- [ ] 代码审查
- [ ] 测试验证
- [ ] 性能检查
- [ ] 文档更新
- [ ] 问题记录和修复

---

## 🎯 迭代质量检查清单

**每个迭代完成后，必须运行以下检查**:

### 基础检查（所有迭代）

```bash
# 1. 测试通过
pytest tests/ -v

# 2. 类型检查通过（Iteration 2 开始）
mypy core/ platforms/ --strict

# 3. 代码风格检查（Iteration 2 开始）
flake8 core/ platforms/ --max-line-length=100

# 4. Git提交
git add .
git commit -m "feat(iteration-N): completed"
```

### 性能检查（Iteration 3 开始）

```bash
# 运行性能基准测试
pytest tests/benchmark/ -v

# 验证无性能退化
# 检查响应时间是否符合预期
```

### 覆盖率检查（Iteration 7）

```bash
# 测试覆盖率 > 80%
pytest --cov=. --cov-report=html --cov-report=term-missing

# 查看覆盖率报告
open htmlcov/index.html
```

### 代码质量检查（Iteration 7）

```bash
# 格式化代码
black core/ platforms/ tests/

# 类型检查
mypy core/ platforms/ --strict

# Lint 检查
flake8 core/ platforms/ tests/ --max-line-length=100

# 安全检查（可选）
bandit -r core/ platforms/
```

### 集成测试（Iteration 5 开始）

```bash
# 测试 MCP 服务器
pytest tests/integration/test_mcp_server.py -v

# 测试端到端流程
pytest tests/integration/ -v
```

### 压力测试（Iteration 6）

```bash
# 并发测试
pytest tests/load/test_concurrent.py -v

# 长时间运行测试（可选）
pytest tests/load/test_long_running.py -v --duration=3600
```

**如果检查不通过，不要进入下一个迭代！**

---

**最后更新**: 2026-01-05  
**维护者**: jaxk

