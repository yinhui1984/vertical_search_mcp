### Iteration 3: 微信搜索重构 (1-1.5 天)

**目标**: 将原项目微信搜索逻辑重构到新架构

#### 性能基准测试设计

**测试1: 浏览器复用性能**

```python
# tests/benchmark/test_weixin_performance.py

import time
import pytest
from core.browser_pool import BrowserPool
from platforms.weixin_searcher import WeixinSearcher


@pytest.mark.asyncio
async def test_browser_reuse_performance():
    """验证浏览器复用带来的性能收益"""

    pool = BrowserPool()
    await pool.init()
    searcher = WeixinSearcher(pool)

    # 首次搜索（包含浏览器初始化时间）
    start1 = time.time()
    results1 = await searcher.search("Python", max_results=5)
    time_first = time.time() - start1

    # 第二次搜索（浏览器已复用）
    start2 = time.time()
    results2 = await searcher.search("AI", max_results=5)
    time_second = time.time() - start2

    print(f"\n性能对比:")
    print(f"首次搜索(含初始化): {time_first:.2f}s")
    print(f"第二次搜索(复用浏览器): {time_second:.2f}s")

    # 验收标准：第二次搜索显著快于首次（阈值可根据实际情况调整）
    assert time_second < time_first / 2, f"浏览器复用加速效果不足: {time_first / time_second:.2f}x"

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
- [x] 实现翻页功能（支持 max_results > 10）
  - [x] 在 `BasePlatformSearcher` 中添加 `_parse_results_with_pagination()` 方法
  - [x] 在 `config/platforms.yaml` 中添加 `next_page` 选择器配置
  - [x] 在 `WeixinSearcher` 中集成翻页功能
  - [x] 添加 max_results 上限验证（上限 30）
  - [x] 编写翻页功能测试

**阶段2: 配置完善 (1小时)**
- [x] 完善 `config/platforms.yaml` 中的微信平台配置
- [x] 配置选择器列表（多重备用）
- [x] 配置 URL 参数
- [x] 配置时间筛选映射
- [x] 配置翻页选择器（next_page）

**阶段3: 集成测试 (2小时)**
- [x] 创建 `tests/integration/test_weixin_search.py`
- [x] 测试基本搜索功能
- [x] 测试时间筛选
- [x] 测试结果解析
- [x] 测试错误处理
- [x] 测试浏览器复用效果
- [x] 测试翻页功能（max_results > 10）
- [x] 测试 max_results 上限验证（上限 30）

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