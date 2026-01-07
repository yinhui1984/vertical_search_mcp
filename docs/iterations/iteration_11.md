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
- [x] 修改 `core/base_searcher.py`
  - [x] 移除 `_extract_item()` 的 `@abstractmethod` 装饰器
  - [x] 添加默认实现（返回 None）
  - [x] 更新 docstring，说明 API-based 搜索器可以使用默认实现
  - [x] 确保向后兼容（现有搜索器不受影响）

**阶段2: 创建 GoogleSearcher 类 (3小时)**
- [x] 创建 `platforms/google_searcher.py`
  - [x] 继承 `BasePlatformSearcher`
  - [x] 实现 `__init__()` 方法
    - [x] 从环境变量读取 API key 和 Search Engine ID
    - [x] 加载平台配置
  - [x] 实现 `_load_config()` 方法
    - [x] 从 `config/platforms.yaml` 加载 Google 配置
    - [x] 处理配置文件不存在或配置缺失的情况
  - [x] 实现 `search()` 方法
    - [x] API 凭证验证（缺失时返回空结果）
    - [x] 查询参数清理（使用 `_sanitize_query()`）
    - [x] 分页逻辑实现
      - [x] 计算需要的请求次数（max_results / 10，向上取整）
      - [x] 实现分页请求（start=1, 11, 21, ...）
      - [x] 处理每页最多 10 个结果的限制
    - [x] JSON 响应转换
      - [x] 将 Google API 响应转换为标准格式
      - [x] 提取 title, url, snippet, date
      - [x] 设置 source 字段（从配置读取）
    - [x] 错误处理
      - [x] 429 (Rate Limit): 指数退避重试（最多 3 次）
      - [x] 400 (Invalid Query): 记录错误，返回空结果
      - [x] 401 (Invalid Credentials): 记录错误，返回空结果
      - [x] 网络错误: 指数退避重试（最多 3 次）
      - [x] 其他错误: 记录错误，返回空结果或部分结果
  - [x] 使用 `httpx` 进行异步 HTTP 请求
  - [x] 添加详细的日志记录（info, warning, error, debug）
  - [x] **不实现** `_extract_item()`（使用默认实现）

**阶段3: 更新配置文件 (30分钟)**
- [x] 更新 `config/platforms.yaml`
  - [x] 添加 `google` 配置节
    - [x] API 配置（base_url, max_results_per_request, max_total_results）
    - [x] 平台元数据（name, display_name, description）
    - [x] 内容选择器配置
      - [x] 主内容选择器（通用选择器，适用于各种网站）
      - [x] 需要移除的元素（nav, header, footer, ads, etc.）
- [x] 更新 `config/anti_crawler.yaml`
  - [x] 在 `platforms` 节下添加 `google` 配置
    - [x] 速率限制（max_requests_per_minute: 10, max_requests_per_hour: 100）
    - [x] 延迟设置（min_delay_ms: 1000, max_delay_ms: 3000）

**阶段4: 集成到 MCP 服务器 (1小时)**
- [x] 更新 `mcp_server.py`
  - [x] 在文件顶部添加导入: `from platforms.google_searcher import GoogleSearcher`
  - [x] 在 `start()` 方法中注册 Google 平台
    - [x] 检查环境变量 `APIKEY_GOOGLE_CUSTOM_SEARCH` 和 `APIKEY_GOOGLE_SEARCH_ID`
    - [x] 如果凭证存在，注册 Google 平台
    - [x] 如果凭证不存在，记录警告但不影响服务器启动
  - [x] 更新工具 schema
    - [x] 在 `platform` enum 中添加 "google"
    - [x] 更新 platform 描述
- [x] 更新 `platforms/__init__.py`（如果存在且用于导出）
  - [x] 添加 `from .google_searcher import GoogleSearcher`

**阶段5: 代码质量检查 (30分钟)**
- [x] 代码风格检查
  - [x] 遵循 PEP 8 规范
  - [x] 使用类型提示（Type Hints）
  - [x] 添加 Google-style docstrings
  - [x] 变量命名有意义
- [x] 类型检查
  - [x] 运行 `mypy platforms/google_searcher.py --strict`
  - [x] 修复所有类型错误
- [x] Lint 检查
  - [x] 运行 `flake8 platforms/google_searcher.py`
  - [x] 修复所有 lint 错误

**阶段6: 手动测试验证 (1小时)**
- [x] 测试无凭证场景
  - [x] 服务器正常启动
  - [x] Google 平台未注册（日志中有警告）
  - [x] 其他平台（Weixin）正常工作
- [x] 测试有凭证场景
  - [x] 设置环境变量 `APIKEY_GOOGLE_CUSTOM_SEARCH` 和 `APIKEY_GOOGLE_SEARCH_ID`
  - [x] 服务器正常启动
  - [x] Google 平台已注册（日志中确认）
  - [x] 通过 MCP 工具调用 Google 搜索
  - [x] 验证返回结果格式正确
- [x] 测试内容获取
  - [x] 使用 `include_content=True` 参数
  - [x] 验证内容获取功能正常
  - [x] 验证内容压缩功能正常
- [x] 测试错误场景
  - [x] 无效的 API key（401 错误）
  - [x] 无效的查询（400 错误）
  - [x] 网络错误（模拟断网）
  - [x] 验证错误处理正确，不导致服务器崩溃

**阶段7: 文档更新 (30分钟)**
- [x] 更新 `README.md`
  - [x] 添加 Google Custom Search 说明
  - [x] 添加环境变量配置说明
  - [x] 添加使用示例
- [x] 更新 `README_cn.md`（中文文档）
  - [x] 同步更新中文文档
- [x] 更新 `docs/iterations/overview.md`
  - [x] 标记 Iteration 11 为已完成

**阶段8: 测试用例编写 (1小时)**
- [x] 创建单元测试 `tests/unit/test_google_searcher.py`
  - [x] 测试初始化（有/无凭证）
  - [x] 测试基本搜索功能
  - [x] 测试分页逻辑
  - [x] 测试错误处理（429, 400, 401, 网络错误）
  - [x] 测试重试机制
  - [x] 测试查询清理
  - [x] 测试结果格式转换
- [x] 创建集成测试 `tests/integration/test_google_search.py`
  - [x] 测试真实 API 调用
  - [x] 测试分页功能（15 和 30 个结果）
  - [x] 测试与 UnifiedSearchManager 集成
  - [x] 测试内容获取集成
  - [x] 测试结果格式验证
- [x] 所有测试通过（25 个测试，全部通过）

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

- [x] **服务器正常启动（无凭证）** 
  - 测量方法: 启动服务器，检查日志
  - 预期结果: 服务器正常启动，Google 平台未注册，其他平台正常
  - 验证方法: 检查日志中的警告信息，验证 Weixin 搜索仍可用
  - ✅ 已验证通过

- [x] **服务器正常启动（有凭证）**
  - 测量方法: 设置环境变量后启动服务器
  - 预期结果: 服务器正常启动，Google 平台已注册
  - 验证方法: 检查日志中的注册信息，验证平台列表包含 "google"
  - ✅ 已验证通过

- [x] **Google 搜索功能正常**
  - 测量方法: 通过 MCP 工具调用 Google 搜索
  - 预期结果: 返回正确格式的搜索结果（title, url, source, snippet, date）
  - 验证方法: 检查返回结果的格式和内容
  - ✅ 已验证通过（集成测试通过）

- [x] **分页功能正常**
  - 测量方法: 请求 max_results=30 的搜索
  - 预期结果: 返回最多 30 个结果（可能需要 3 次 API 请求）
  - 验证方法: 检查返回结果数量，验证分页逻辑
  - ✅ 已验证通过（单元测试和集成测试通过）

- [x] **内容获取功能正常**
  - 测量方法: 使用 `include_content=True` 参数
  - 预期结果: 返回包含文章内容的结果
  - 验证方法: 检查结果中的 `content` 字段
  - ✅ 已验证通过（集成测试通过，即使部分网站有 captcha，snippet 仍可用）

- [x] **内容压缩功能正常**
  - 测量方法: 获取长文章内容，验证压缩逻辑
  - 预期结果: 内容被正确压缩（如果超过阈值）
  - 验证方法: 检查 `content_status` 字段和压缩后的内容长度
  - ✅ 已验证通过（超时时间已增加到 60 秒）

- [x] **错误处理正确**
  - 测量方法: 测试各种错误场景（无效凭证、网络错误等）
  - 预期结果: 错误被正确捕获和处理，不导致服务器崩溃
  - 验证方法: 检查错误日志和返回结果（应为空结果而非异常）
  - ✅ 已验证通过（单元测试覆盖所有错误场景）

- [x] **现有平台不受影响**
  - 测量方法: 运行现有测试套件
  - 预期结果: 所有现有测试通过
  - 验证方法: `pytest tests/integration/test_weixin_search.py -v`
  - ✅ 已验证通过（向后兼容性保持）

- [x] **代码质量达标**
  - 测量方法: 运行类型检查和 lint 检查
  - 预期结果: 无类型错误，无 lint 错误
  - 验证方法: `mypy platforms/google_searcher.py --strict` 和 `flake8 platforms/google_searcher.py`
  - ✅ 已验证通过（无 lint 错误）

- [x] **文档完整**
  - 测量方法: 检查 README 和设计文档
  - 预期结果: 包含 Google Custom Search 的配置和使用说明
  - 验证方法: 检查文档中的相关章节
  - ✅ 已验证通过（README 和 README_cn 已更新）

- [x] **测试覆盖完整**
  - 测量方法: 运行 Google 相关测试
  - 预期结果: 单元测试和集成测试全部通过
  - 验证方法: `pytest tests/unit/test_google_searcher.py tests/integration/test_google_search.py -v`
  - ✅ 已验证通过（25 个测试全部通过）

**依赖**: Iteration 10

**完成时间**: 2026-01-07

**额外完成**:
- [x] 所有代码包含完整的类型注解和文档字符串
- [x] 代码质量符合项目规范（无 lint 错误，类型检查通过）
- [x] 实现了优雅的错误处理（不导致服务器崩溃）
- [x] 提供了详细的使用文档和配置说明
- [x] 实现了速率限制和重试机制
- [x] 创建了完整的测试套件（单元测试和集成测试）
- [x] 更新了压缩超时时间（从 30 秒增加到 60 秒）
- [x] 创建了独立的测试脚本（test_weixin.py, test_zhihu.py, test_google.py）

**技术参考**:
- 设计文档: `docs/GOOGLE_CUSTOM_SEARCH_DESIGN.md`
- 重构计划: `docs/GOOGLE_CUSTOM_SEARCH_REFACTORING.md`
- 快速摘要: `docs/GOOGLE_CUSTOM_SEARCH_SUMMARY.md`
- Google Custom Search API: https://developers.google.com/custom-search/v1/overview
- httpx 文档: https://www.python-httpx.org/

---

