### Iteration 11: Google Custom Search 支持 (1 天)

**目标**: 集成 Google Custom Search API 作为新的搜索平台，支持基于 REST API 的搜索功能，同时保持与现有浏览器-based 平台的兼容性

**背景**: 
- **需求**: 添加 Google Custom Search API 支持，扩展搜索平台范围
- **技术挑战**: 
  - Google 使用 REST API，不同于现有的浏览器-based 搜索（Weixin, Zhihu）
  - 需要最小化重构，保持向后兼容
  - API-based 搜索不需要 DOM 解析，但内容获取仍使用浏览器
- **设计决策**: 
  - 将 `BasePlatformSearcher._extract_item()` 改为可选方法（默认返回 None）
  - API-based 搜索器不实现 `_extract_item()`，直接转换 JSON 响应
  - 内容获取和压缩复用现有基础设施（ContentProcessor）

#### 执行阶段（按顺序）

**阶段1: 修改基础搜索器类 (30分钟)**
- [ ] 修改 `core/base_searcher.py`
  - [ ] 移除 `_extract_item()` 的 `@abstractmethod` 装饰器
  - [ ] 添加默认实现（返回 None）
  - [ ] 更新 docstring，说明 API-based 搜索器可以使用默认实现
  - [ ] 确保向后兼容（现有搜索器不受影响）

**阶段2: 创建 GoogleSearcher 类 (3小时)**
- [ ] 创建 `platforms/google_searcher.py`
  - [ ] 继承 `BasePlatformSearcher`
  - [ ] 实现 `__init__()` 方法
    - [ ] 从环境变量读取 API key 和 Search Engine ID
    - [ ] 加载平台配置
  - [ ] 实现 `_load_config()` 方法
    - [ ] 从 `config/platforms.yaml` 加载 Google 配置
    - [ ] 处理配置文件不存在或配置缺失的情况
  - [ ] 实现 `search()` 方法
    - [ ] API 凭证验证（缺失时返回空结果）
    - [ ] 查询参数清理（使用 `_sanitize_query()`）
    - [ ] 分页逻辑实现
      - [ ] 计算需要的请求次数（max_results / 10，向上取整）
      - [ ] 实现分页请求（start=1, 11, 21, ...）
      - [ ] 处理每页最多 10 个结果的限制
    - [ ] JSON 响应转换
      - [ ] 将 Google API 响应转换为标准格式
      - [ ] 提取 title, url, snippet, date
      - [ ] 设置 source 字段（从配置读取）
    - [ ] 错误处理
      - [ ] 429 (Rate Limit): 指数退避重试（最多 3 次）
      - [ ] 400 (Invalid Query): 记录错误，返回空结果
      - [ ] 401 (Invalid Credentials): 记录错误，返回空结果
      - [ ] 网络错误: 指数退避重试（最多 3 次）
      - [ ] 其他错误: 记录错误，返回空结果或部分结果
  - [ ] 使用 `httpx` 进行异步 HTTP 请求
  - [ ] 添加详细的日志记录（info, warning, error, debug）
  - [ ] **不实现** `_extract_item()`（使用默认实现）

**阶段3: 更新配置文件 (30分钟)**
- [ ] 更新 `config/platforms.yaml`
  - [ ] 添加 `google` 配置节
    - [ ] API 配置（base_url, max_results_per_request, max_total_results）
    - [ ] 平台元数据（name, display_name, description）
    - [ ] 内容选择器配置
      - [ ] 主内容选择器（通用选择器，适用于各种网站）
      - [ ] 需要移除的元素（nav, header, footer, ads, etc.）
- [ ] 更新 `config/anti_crawler.yaml`
  - [ ] 在 `platforms` 节下添加 `google` 配置
    - [ ] 速率限制（max_requests_per_minute: 10, max_requests_per_hour: 100）
    - [ ] 延迟设置（min_delay_ms: 1000, max_delay_ms: 3000）

**阶段4: 集成到 MCP 服务器 (1小时)**
- [ ] 更新 `mcp_server.py`
  - [ ] 在文件顶部添加导入: `from platforms.google_searcher import GoogleSearcher`
  - [ ] 在 `start()` 方法中注册 Google 平台
    - [ ] 检查环境变量 `APIKEY_GOOGLE_CUSTOM_SEARCH` 和 `APIKEY_GOOGLE_SEARCH_ID`
    - [ ] 如果凭证存在，注册 Google 平台
    - [ ] 如果凭证不存在，记录警告但不影响服务器启动
  - [ ] 更新工具 schema
    - [ ] 在 `platform` enum 中添加 "google"
    - [ ] 更新 platform 描述
- [ ] 更新 `platforms/__init__.py`（如果存在且用于导出）
  - [ ] 添加 `from .google_searcher import GoogleSearcher`

**阶段5: 代码质量检查 (30分钟)**
- [ ] 代码风格检查
  - [ ] 遵循 PEP 8 规范
  - [ ] 使用类型提示（Type Hints）
  - [ ] 添加 Google-style docstrings
  - [ ] 变量命名有意义
- [ ] 类型检查
  - [ ] 运行 `mypy platforms/google_searcher.py --strict`
  - [ ] 修复所有类型错误
- [ ] Lint 检查
  - [ ] 运行 `flake8 platforms/google_searcher.py`
  - [ ] 修复所有 lint 错误

**阶段6: 手动测试验证 (1小时)**
- [ ] 测试无凭证场景
  - [ ] 服务器正常启动
  - [ ] Google 平台未注册（日志中有警告）
  - [ ] 其他平台（Weixin）正常工作
- [ ] 测试有凭证场景
  - [ ] 设置环境变量 `APIKEY_GOOGLE_CUSTOM_SEARCH` 和 `APIKEY_GOOGLE_SEARCH_ID`
  - [ ] 服务器正常启动
  - [ ] Google 平台已注册（日志中确认）
  - [ ] 通过 MCP 工具调用 Google 搜索
  - [ ] 验证返回结果格式正确
- [ ] 测试内容获取
  - [ ] 使用 `include_content=True` 参数
  - [ ] 验证内容获取功能正常
  - [ ] 验证内容压缩功能正常
- [ ] 测试错误场景
  - [ ] 无效的 API key（401 错误）
  - [ ] 无效的查询（400 错误）
  - [ ] 网络错误（模拟断网）
  - [ ] 验证错误处理正确，不导致服务器崩溃

**阶段7: 文档更新 (30分钟)**
- [ ] 更新 `README.md`
  - [ ] 添加 Google Custom Search 说明
  - [ ] 添加环境变量配置说明
  - [ ] 添加使用示例
- [ ] 更新 `README_cn.md`（中文文档）
  - [ ] 同步更新中文文档
- [ ] 更新 `docs/iterations/overview.md`
  - [ ] 标记 Iteration 11 为已完成

#### ⚠️ 风险预警

**风险1: API 凭证缺失导致功能不可用**
- **触发条件**: 环境变量未设置或设置错误
- **影响**: Google 搜索功能不可用
- **应对策略**: 
  - 实现优雅降级（凭证缺失时记录警告但不崩溃）
  - 在文档中明确说明环境变量配置要求
  - 在日志中提供清晰的错误信息

**风险2: API 速率限制**
- **触发条件**: 频繁调用 Google API 超过免费配额（100次/天）
- **影响**: API 调用失败，返回空结果
- **应对策略**: 
  - 实现保守的速率限制（10次/分钟）
  - 实现指数退避重试机制
  - 在配置中设置合理的延迟
  - 记录详细的日志以便监控

**风险3: 内容提取失败**
- **触发条件**: Google 返回的结果来自各种网站，HTML 结构差异大
- **影响**: 内容获取失败或提取不准确
- **应对策略**: 
  - 使用通用内容选择器（article, main, body 等）
  - 实现多选择器回退机制
  - 如果所有选择器失败，回退到 body 标签
  - 记录警告但不影响搜索结果返回

**风险4: 分页逻辑错误**
- **触发条件**: 分页计算错误或 API 返回结果数不足
- **影响**: 返回结果数少于预期
- **应对策略**: 
  - 仔细实现分页逻辑（start=1, 11, 21）
  - 处理 API 返回结果数少于请求数的情况
  - 记录实际返回的结果数
  - 返回部分结果而非失败

**风险5: 向后兼容性问题**
- **触发条件**: 修改 `BasePlatformSearcher` 导致现有搜索器失效
- **影响**: Weixin 和 Zhihu 搜索功能异常
- **应对策略**: 
  - 确保 `_extract_item()` 的默认实现不影响现有搜索器
  - 现有搜索器已实现 `_extract_item()`，不受影响
  - 运行现有测试确保无回归

**验收标准**:

- [ ] **服务器正常启动（无凭证）** 
  - 测量方法: 启动服务器，检查日志
  - 预期结果: 服务器正常启动，Google 平台未注册，其他平台正常
  - 验证方法: 检查日志中的警告信息，验证 Weixin 搜索仍可用

- [ ] **服务器正常启动（有凭证）**
  - 测量方法: 设置环境变量后启动服务器
  - 预期结果: 服务器正常启动，Google 平台已注册
  - 验证方法: 检查日志中的注册信息，验证平台列表包含 "google"

- [ ] **Google 搜索功能正常**
  - 测量方法: 通过 MCP 工具调用 Google 搜索
  - 预期结果: 返回正确格式的搜索结果（title, url, source, snippet, date）
  - 验证方法: 检查返回结果的格式和内容

- [ ] **分页功能正常**
  - 测量方法: 请求 max_results=30 的搜索
  - 预期结果: 返回最多 30 个结果（可能需要 3 次 API 请求）
  - 验证方法: 检查返回结果数量，验证分页逻辑

- [ ] **内容获取功能正常**
  - 测量方法: 使用 `include_content=True` 参数
  - 预期结果: 返回包含文章内容的结果
  - 验证方法: 检查结果中的 `content` 字段

- [ ] **内容压缩功能正常**
  - 测量方法: 获取长文章内容，验证压缩逻辑
  - 预期结果: 内容被正确压缩（如果超过阈值）
  - 验证方法: 检查 `content_status` 字段和压缩后的内容长度

- [ ] **错误处理正确**
  - 测量方法: 测试各种错误场景（无效凭证、网络错误等）
  - 预期结果: 错误被正确捕获和处理，不导致服务器崩溃
  - 验证方法: 检查错误日志和返回结果（应为空结果而非异常）

- [ ] **现有平台不受影响**
  - 测量方法: 运行现有测试套件
  - 预期结果: 所有现有测试通过
  - 验证方法: `pytest tests/integration/test_weixin_search.py -v`

- [ ] **代码质量达标**
  - 测量方法: 运行类型检查和 lint 检查
  - 预期结果: 无类型错误，无 lint 错误
  - 验证方法: `mypy platforms/google_searcher.py --strict` 和 `flake8 platforms/google_searcher.py`

- [ ] **文档完整**
  - 测量方法: 检查 README 和设计文档
  - 预期结果: 包含 Google Custom Search 的配置和使用说明
  - 验证方法: 检查文档中的相关章节

**依赖**: Iteration 10

**完成时间**: TBD

**额外完成**:
- [ ] 所有代码包含完整的类型注解和文档字符串
- [ ] 代码质量符合项目规范（无 lint 错误，类型检查通过）
- [ ] 实现了优雅的错误处理（不导致服务器崩溃）
- [ ] 提供了详细的使用文档和配置说明
- [ ] 实现了速率限制和重试机制

**技术参考**:
- 设计文档: `docs/GOOGLE_CUSTOM_SEARCH_DESIGN.md`
- 重构计划: `docs/GOOGLE_CUSTOM_SEARCH_REFACTORING.md`
- 快速摘要: `docs/GOOGLE_CUSTOM_SEARCH_SUMMARY.md`
- Google Custom Search API: https://developers.google.com/custom-search/v1/overview
- httpx 文档: https://www.python-httpx.org/

---

