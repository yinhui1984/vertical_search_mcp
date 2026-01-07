### Iteration 12: Multi-Platform Search Support (1.5 天)

**目标**: 支持多平台搜索功能，允许用户在一次请求中搜索多个平台，并提供统一的进度报告和结果聚合

**背景**: 
- **需求**: 用户希望能够同时搜索多个平台（weixin, google），而不需要多次调用
- **用户体验**: 当前需要为每个平台单独调用，使用不便
- **技术挑战**: 
  - 需要设计灵活的 platform 参数格式
  - 多平台搜索的进度报告需要清晰展示
  - 单个 task_id 需要管理多个平台的搜索进度
  - 结果需要聚合和去重
- **设计决策**: 
  - Platform 参数使用字符串格式：`"all"`（默认）、`"weixin"`、`"weixin,google"` 等
  - 单个 task_id 对应整个多平台搜索任务
  - 两层进度报告：平台级别 + 平台内部阶段
  - 结果按平台标记，去重后合并

#### 执行阶段（按顺序）

**阶段1: 设计文档和方案确认 (1小时)**
- [x] 创建多平台搜索设计文档 `docs/MULTI_PLATFORM_SEARCH_DESIGN.md`
- [x] 确认 platform 参数格式：`"all"`、`"weixin"`、`"weixin,google"`
- [x] 确认 task_id 管理方案：单个 task_id 管理整个多平台搜索
- [x] 确认进度报告方案：平台级别 + 阶段级别
- [x] 确认结果聚合方案：标记平台、去重、限制总数

**阶段2: 实现平台解析函数 (30分钟)**
- [ ] 在 `mcp_server.py` 中添加 `_parse_platforms()` 方法
  - [ ] 解析 `"all"` -> 所有注册的平台
  - [ ] 解析单个平台 `"weixin"` -> `["weixin"]`
  - [ ] 解析多个平台 `"weixin,google"` -> `["weixin", "google"]`
  - [ ] 处理空格：`"weixin, google"` -> `["weixin", "google"]`
  - [ ] 验证平台是否存在，不存在时抛出 ValueError
  - [ ] 返回可用平台列表作为错误信息的一部分

**阶段3: 修改 inputSchema (30分钟)**
- [ ] 修改 `handle_list_tools()` 中的 `start_vertical_search` schema
  - [ ] 将 `platform` 从 `enum` 改为 `string` 类型
  - [ ] 更新 description，说明支持的格式
  - [ ] 添加 `default: "all"`
  - [ ] 从 `required` 数组中移除 `"platform"`（因为有默认值）
  - [ ] 更新工具描述，说明多平台搜索功能

**阶段4: 修改任务创建和处理 (1小时)**
- [ ] 修改 `_handle_start_vertical_search()` 方法
  - [ ] 获取 platform 参数（默认 "all"）
  - [ ] 调用 `_parse_platforms()` 解析平台列表
  - [ ] 验证平台列表（处理 ValueError）
  - [ ] 创建 task 时，platform 字段存储为逗号分隔的字符串
  - [ ] 修改 `_execute_search_task()` 调用，传入 `platforms` 列表
- [ ] 修改 `_execute_search_task()` 方法签名
  - [ ] 将 `platform: str` 改为 `platforms: List[str]`
  - [ ] 添加多平台搜索逻辑
  - [ ] 计算每个平台的结果数量分配
  - [ ] 实现平台级别的进度报告

**阶段5: 实现多平台搜索执行逻辑 (2小时)**
- [ ] 在 `_execute_search_task()` 中实现多平台循环
  - [ ] 遍历平台列表
  - [ ] 为每个平台创建进度回调包装器
  - [ ] 计算当前平台的结果数量（平均分配 + 余数给最后一个）
  - [ ] 调用 `manager.search()` 搜索每个平台
  - [ ] 标记每个结果的来源平台（`result['platform'] = platform_name`）
  - [ ] 收集所有平台的结果
  - [ ] 处理平台搜索失败（继续其他平台）
- [ ] 实现结果聚合
  - [ ] 按 URL 去重（保留第一个出现的）
  - [ ] 限制最终结果数量为 `max_results`
  - [ ] 记录每个平台的搜索状态（成功/失败）

**阶段6: 实现进度报告包装器 (1.5小时)**
- [ ] 创建 `create_platform_progress_callback()` 函数
  - [ ] 接收平台名称和平台索引
  - [ ] 返回包装后的进度回调函数
  - [ ] 计算总体进度：`(已完成平台数 × 100 + 当前平台进度) / 总平台数`
  - [ ] 构建带平台前缀的消息：`"Platform X/Y (platform_name): message"`
  - [ ] 设置 stage 为 `"{platform}_{stage}"`（多平台）或 `"{stage}"`（单平台）
  - [ ] 调用 `task_manager.update_task_progress()` 更新进度
- [ ] 在平台搜索开始和完成时添加进度更新
  - [ ] 平台开始：`"Platform X/Y (platform_name): Starting search..."`
  - [ ] 平台完成：`"Platform X/Y (platform_name): Completed (N results)"`
  - [ ] 多平台搜索完成：`"Multi-platform search completed: X/Y platforms, N total results"`

**阶段7: 错误处理和容错 (1小时)**
- [ ] 实现平台级别的错误隔离
  - [ ] 单个平台失败不影响其他平台
  - [ ] 记录失败平台和错误信息
  - [ ] 在最终进度消息中报告失败的平台
- [ ] 处理所有平台都失败的情况
  - [ ] 设置任务状态为 FAILED
  - [ ] 返回聚合的错误信息
- [ ] 处理无效平台名称
  - [ ] 在 `_parse_platforms()` 中验证
  - [ ] 返回清晰的错误消息，包含可用平台列表

**阶段8: 更新任务管理器（如需要）(30分钟)**
- [ ] 检查 `TaskManager.create_task()` 是否需要修改
  - [ ] platform 字段可以存储逗号分隔的字符串（如 `"weixin,google"`）
  - [ ] 确保向后兼容（单平台仍然工作）
- [ ] 检查 `SearchTask` 数据结构是否需要扩展
  - [ ] 当前结构应该足够（platform 字段存储字符串即可）

**阶段9: 代码质量检查 (30分钟)**
- [ ] 代码风格检查
  - [ ] 遵循 PEP 8 规范
  - [ ] 使用类型提示（Type Hints）
  - [ ] 添加详细的 docstrings
- [ ] 类型检查
  - [ ] 运行 `mypy mcp_server.py`
  - [ ] 修复所有类型错误
- [ ] Lint 检查
  - [ ] 运行 `flake8 mcp_server.py`
  - [ ] 修复所有 lint 错误

**阶段10: 单元测试 (1.5小时)**
- [ ] 测试 `_parse_platforms()` 方法
  - [ ] 测试 `"all"` -> 所有平台
  - [ ] 测试单个平台 `"weixin"`
  - [ ] 测试多个平台 `"weixin,google"`
  - [ ] 测试带空格 `"weixin, google"`
  - [ ] 测试无效平台名称
  - [ ] 测试空字符串（应该使用默认 "all"）
- [ ] 测试进度计算
  - [ ] 测试单平台进度（应该与之前相同）
  - [ ] 测试多平台进度计算
  - [ ] 测试进度消息格式

**阶段11: 集成测试 (2小时)**
- [ ] 测试单平台搜索（向后兼容性）
  - [ ] `platform="weixin"` 应该与之前行为相同
  - [ ] 进度消息不应该有平台前缀
  - [ ] 结果格式相同
- [ ] 测试多平台搜索
  - [ ] `platform="weixin,google"` 搜索两个平台
  - [ ] 验证进度报告包含平台信息
  - [ ] 验证结果包含 `platform` 字段
  - [ ] 验证结果去重
  - [ ] 验证结果总数限制
- [ ] 测试默认行为
  - [ ] 不提供 platform 参数，应该搜索所有平台
  - [ ] `platform="all"` 应该搜索所有平台
- [ ] 测试错误场景
  - [ ] 一个平台失败，其他平台继续
  - [ ] 所有平台失败
  - [ ] 无效平台名称

**阶段12: 手动测试验证 (1小时)**
- [ ] 测试单平台搜索
  - [ ] `platform="weixin"` 正常工作
  - [ ] 进度报告正常
  - [ ] 结果格式正确
- [ ] 测试多平台搜索
  - [ ] `platform="weixin,google"` 搜索两个平台
  - [ ] 观察进度报告（平台级别 + 阶段级别）
  - [ ] 验证结果包含两个平台的内容
  - [ ] 验证结果去重
- [ ] 测试默认行为
  - [ ] 不提供 platform，搜索所有平台
  - [ ] `platform="all"` 搜索所有平台
- [ ] 测试错误处理
  - [ ] 无效平台名称返回错误
  - [ ] 一个平台失败不影响其他平台

**阶段13: 文档更新 (30分钟)**
- [ ] 更新 README.md
  - [ ] 添加多平台搜索使用示例
  - [ ] 说明 platform 参数格式
  - [ ] 说明进度报告格式
- [ ] 更新 API 文档（如果有）
  - [ ] 更新工具描述
  - [ ] 添加多平台搜索示例

## 测试用例

### 单元测试用例

```python
def test_parse_platforms_all():
    """Test parsing 'all' returns all registered platforms."""
    # Should return ['weixin', 'google'] if both are registered

def test_parse_platforms_single():
    """Test parsing single platform."""
    assert parse_platforms("weixin") == ["weixin"]

def test_parse_platforms_multiple():
    """Test parsing multiple platforms."""
    assert parse_platforms("weixin,google") == ["weixin", "google"]

def test_parse_platforms_with_spaces():
    """Test parsing with spaces around commas."""
    assert parse_platforms("weixin, google") == ["weixin", "google"]

def test_parse_platforms_invalid():
    """Test parsing invalid platform raises ValueError."""
    with pytest.raises(ValueError, match="Invalid platform"):
        parse_platforms("invalid_platform")
```

### 集成测试用例

```python
async def test_single_platform_backward_compatibility():
    """Test single platform search works as before."""
    # Should behave exactly like before iteration 12

async def test_multi_platform_search():
    """Test multi-platform search returns results from all platforms."""
    # Search weixin and google, verify results from both

async def test_multi_platform_progress():
    """Test multi-platform progress reporting."""
    # Verify progress messages include platform information

async def test_multi_platform_deduplication():
    """Test results are deduplicated by URL."""
    # If same URL appears in multiple platforms, keep only one

async def test_platform_failure_isolation():
    """Test one platform failure doesn't affect others."""
    # Mock one platform to fail, verify others continue
```

## 验收标准

1. ✅ Platform 参数支持 `"all"`（默认）、单个平台、多个平台（逗号分隔）
2. ✅ 单个 task_id 管理整个多平台搜索任务
3. ✅ 进度报告清晰显示平台级别和阶段级别信息
4. ✅ 结果正确聚合、去重、限制总数
5. ✅ 单平台搜索保持向后兼容
6. ✅ 错误处理正确（平台失败隔离）
7. ✅ 所有测试通过
8. ✅ 代码质量检查通过

## 预计时间

- 设计文档：1 小时
- 平台解析：30 分钟
- Schema 修改：30 分钟
- 任务管理修改：1 小时
- 多平台搜索逻辑：2 小时
- 进度报告：1.5 小时
- 错误处理：1 小时
- 任务管理器更新：30 分钟
- 代码质量检查：30 分钟
- 单元测试：1.5 小时
- 集成测试：2 小时
- 手动测试：1 小时
- 文档更新：30 分钟

**总计**: 约 13.5 小时（1.5 天）

## 风险与缓解

### 风险1: 进度报告复杂
- **风险**: 多平台进度计算可能不准确
- **缓解**: 使用简单的公式，充分测试

### 风险2: 结果去重可能丢失重要信息
- **风险**: 不同平台的相同 URL 可能有不同内容
- **缓解**: 保留第一个出现的，记录来源平台

### 风险3: 性能问题（多平台顺序搜索）
- **风险**: 顺序搜索可能较慢
- **缓解**: 先实现顺序搜索，后续可优化为并行

### 风险4: 向后兼容性问题
- **风险**: 单平台搜索行为可能改变
- **缓解**: 充分测试单平台场景，确保行为一致

## 后续优化

1. **并行平台搜索**: 同时搜索多个平台，提高速度
2. **智能去重**: 使用内容相似度，不仅仅是 URL
3. **平台优先级**: 重要平台先搜索
4. **平台特定限制**: 每个平台不同的 max_results
5. **结果排序**: 跨平台结果合并和排序

