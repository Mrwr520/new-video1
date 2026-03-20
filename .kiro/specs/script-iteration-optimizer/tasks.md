# 实施计划：剧本迭代优化系统

## 概述

本实施计划将剧本迭代优化系统分解为可执行的编码任务。系统采用迭代引擎驱动的架构，通过多轮生成-评审-优化循环提升剧本质量。实施将按照后端核心功能 → 搜索集成 → 数据持久化 → API 端点 → 前端可视化的顺序进行。

## 任务列表

- [x] 1. 创建核心数据模型和配置
  - 创建 `backend/app/models/script_optimization.py` 定义数据库模型
  - 创建 `backend/app/schemas/script_optimization.py` 定义 Pydantic 模式
  - 创建 `backend/app/config/optimization_config.py` 定义配置类
  - 实现 `DimensionScores`、`DimensionWeights`、`EvaluationResult`、`ScriptVersion` 等数据类
  - 实现 `IterationConfig` 配置类，支持目标分数、最大迭代次数等参数
  - _需求：1.1, 2.1, 8.1, 8.2, 8.3_

- [x] 1.1 为核心数据模型编写属性测试

  - **属性 5：加权平均计算正确性**
  - **验证：需求 2.2**

- [ ]\* 1.2 为配置验证编写属性测试
  - **属性 15：配置验证拒绝无效值**
  - **验证：需求 8.5**

- [x] 2. 实现剧本评审器 (Script Evaluator)
  - [x] 2.1 创建 `backend/app/services/script_evaluator_v2.py`
    - 实现 `ScriptEvaluator` 类的初始化和配置
    - 实现 `evaluate_script()` 方法，调用 LLM 进行多维度评审
    - 实现 `_calculate_total_score()` 方法，计算加权平均分
    - 实现 `_generate_suggestions()` 方法，生成改进建议
    - 集成现有的 `LLMService` 进行 LLM 调用
    - _需求：2.1, 2.2, 2.3, 2.4_

  - [ ]\* 2.2 为评审器编写属性测试
    - **属性 2：迭代评审一致性**
    - **属性 6：改进建议生成**
    - **验证：需求 1.2, 2.1, 2.3, 2.4**

- [x] 3. 实现搜索 API 客户端
  - [x] 3.1 创建 `backend/app/services/search_api_client.py`
    - 实现 `SearchAPIClient` 类，封装第三方搜索 API
    - 实现 `search()` 方法，支持 web 和 news 搜索
    - 实现 `_execute_with_retry()` 方法，支持重试机制（最多 3 次）
    - 实现速率限制保护，避免超出 API 配额
    - 支持配置 API 密钥和端点
    - _需求：3.1, 4.1, 7.1, 7.2, 7.5, 8.4_

  - [ ]\* 3.2 为搜索客户端编写属性测试
    - **属性 12：API 重试机制**
    - **属性 13：速率限制保护**
    - **验证：需求 7.2, 7.5**

- [x] 4. 实现热点搜索器 (Hotspot Searcher)
  - [x] 4.1 创建 `backend/app/services/hotspot_searcher.py`
    - 实现 `HotspotSearcher` 类
    - 实现 `search_hotspots()` 方法，搜索实时热点
    - 实现 `_extract_keywords()` 方法，从剧本中提取关键词
    - 实现 `_parse_hotspot_results()` 方法，解析搜索结果为 `Hotspot` 对象
    - 实现错误处理，搜索失败时返回空列表
    - _需求：3.1, 3.2, 3.3, 3.4_

  - [ ]\* 4.2 为热点搜索器编写属性测试
    - **属性 7：搜索关键词提取**
    - **属性 8：搜索结果数量保证**
    - **验证：需求 3.2, 3.3**

- [x] 5. 实现技巧搜索器 (Technique Searcher)
  - [x] 5.1 创建 `backend/app/services/technique_searcher.py`
    - 实现 `TechniqueSearcher` 类
    - 实现 `search_techniques()` 方法，搜索剧本创作技巧
    - 实现 `_build_search_query()` 方法，根据剧本类型和缺陷构建查询
    - 实现 `_parse_technique_results()` 方法，解析搜索结果
    - 实现 `_get_fallback_techniques()` 方法，提供默认技巧库
    - 实现降级策略，搜索失败时使用默认技巧
    - _需求：4.1, 4.2, 4.3, 4.4_

  - [ ]\* 5.2 为技巧搜索器编写属性测试
    - **属性 7：搜索关键词提取**
    - **属性 8：搜索结果数量保证**
    - **验证：需求 4.2, 4.3**

- [x] 6. 实现剧本生成器 (Script Generator)
  - [x] 6.1 创建 `backend/app/services/script_generator.py`
    - 实现 `ScriptGenerator` 类
    - 实现 `generate_initial_script()` 方法，生成初始剧本
    - 实现 `regenerate_script()` 方法，根据评审结果和搜索数据重新生成
    - 实现 `_build_regeneration_prompt()` 方法，构建优化提示词
    - 集成现有的 `LLMService` 进行剧本生成
    - 实现错误处理和重试机制
    - _需求：1.1, 1.3, 7.4_

  - [ ]\* 6.2 为剧本生成器编写单元测试
    - 测试初始剧本生成
    - 测试基于反馈的重新生成
    - 测试提示词构建逻辑

- [x] 7. 实现版本管理器 (Version Manager)
  - [x] 7.1 创建 `backend/app/services/version_manager.py`
    - 实现 `VersionManager` 类
    - 实现 `save_version()` 方法，保存剧本版本到数据库
    - 实现 `get_versions()` 方法，查询会话的所有版本
    - 实现 `get_version()` 方法，查询特定版本
    - 实现 `mark_final_version()` 方法，标记最终版本
    - _需求：6.1, 6.2, 6.3, 6.4_

  - [ ]\* 7.2 为版本管理器编写属性测试
    - **属性 9：版本持久化完整性**
    - **属性 10：版本查询完整性**
    - **属性 11：最终版本标记**
    - **验证：需求 6.1, 6.2, 6.3, 6.4**

- [x] 8. 实现迭代引擎 (Iteration Engine)
  - [x] 8.1 创建 `backend/app/services/iteration_engine.py`
    - 实现 `IterationEngine` 类，协调整个优化流程
    - 实现 `optimize_script()` 方法，执行完整的优化流程
    - 实现 `_iteration_loop()` 方法，执行迭代循环
    - 实现并行搜索逻辑（使用 `asyncio.gather`）
    - 实现迭代终止条件判断（分数达标或达到最大次数）
    - 实现进度回调机制，推送实时进度
    - 集成所有子组件（生成器、评审器、搜索器、版本管理器）
    - _需求：1.1, 1.2, 1.3, 1.4, 1.5, 10.1_

  - [ ]\* 8.2 为迭代引擎编写属性测试
    - **属性 1：迭代启动完整性**
    - **属性 3：迭代继续条件**
    - **属性 4：迭代终止条件**
    - **属性 19：并行搜索执行**
    - **验证：需求 1.1, 1.3, 1.4, 10.1**

- [x] 9. 检查点 - 核心功能验证
  - 确保所有核心服务类已实现并通过测试
  - 验证迭代引擎能够完成完整的优化流程
  - 如有问题请向用户询问

- [x] 10. 实现 WebSocket 管理器
  - [x] 10.1 创建 `backend/app/services/websocket_manager.py`
    - 实现 `WebSocketManager` 类
    - 实现 `connect()` 方法，建立 WebSocket 连接
    - 实现 `disconnect()` 方法，断开连接
    - 实现 `send_progress()` 方法，推送进度更新
    - 维护活跃连接字典
    - 实现错误处理，连接断开时不影响主流程
    - _需求：5.2, 10.4_

  - [ ]\* 10.2 为 WebSocket 管理器编写属性测试
    - **属性 20：WebSocket 进度推送**
    - **验证：需求 5.2, 10.4**

- [x] 11. 实现错误处理器
  - [x] 11.1 创建 `backend/app/services/error_handler.py`
    - 实现 `ErrorHandler` 类
    - 实现 `handle_search_error()` 方法，处理搜索错误
    - 实现 `handle_generation_error()` 方法，处理生成错误
    - 实现 `handle_critical_error()` 方法，处理关键错误
    - 实现错误日志记录
    - 实现降级策略
    - _需求：9.1, 9.2, 9.3_

  - [ ]\* 11.2 为错误处理器编写属性测试
    - **属性 16：错误日志记录**
    - **属性 17：错误恢复能力**
    - **验证：需求 9.1, 9.2**

- [x] 12. 创建数据库迁移
  - [x] 12.1 创建数据库迁移脚本
    - 创建 `optimization_sessions` 表
    - 创建 `script_versions` 表
    - 创建 `search_cache` 表（可选）
    - 添加必要的索引
    - _需求：6.1_

- [x] 13. 实现 API 路由
  - [x] 13.1 创建 `backend/app/api/script_optimization.py`
    - 实现 `POST /api/script-optimization/start` 端点，启动优化流程
    - 实现 `GET /api/script-optimization/{session_id}/status` 端点，查询状态
    - 实现 `GET /api/script-optimization/{session_id}/versions` 端点，获取版本历史
    - 实现 `GET /api/script-optimization/{session_id}/versions/{iteration}` 端点，获取特定版本
    - 实现 `WebSocket /ws/script-optimization/{session_id}` 端点，实时进度推送
    - 实现请求验证和错误响应
    - _需求：1.1, 6.2, 6.3_

  - [ ]\* 13.2 为 API 路由编写集成测试
    - 测试完整的优化流程
    - 测试版本查询
    - 测试 WebSocket 连接和消息推送

- [x] 14. 检查点 - 后端功能完整性验证
  - 确保所有 API 端点正常工作
  - 验证 WebSocket 实时推送功能
  - 验证数据库持久化
  - 如有问题请向用户询问

- [x] 15. 实现前端状态管理
  - [x] 15.1 创建 `frontend/src/store/scriptOptimizationSlice.ts`
    - 使用 Redux Toolkit 创建状态切片
    - 定义 `OptimizationState` 接口
    - 实现状态更新 reducers
    - 实现异步 thunks（启动优化、查询版本等）
    - _需求：5.2_

- [x] 16. 实现 WebSocket 客户端
  - [x] 16.1 创建 `frontend/src/services/websocketService.ts`
    - 实现 WebSocket 连接管理
    - 实现消息接收和分发
    - 实现自动重连机制
    - 集成 Redux store，更新状态
    - _需求：5.2, 10.4_

- [x] 17. 实现前端核心组件
  - [x] 17.1 创建优化控制面板
    - 创建 `frontend/src/components/ScriptOptimization/ControlPanel.tsx`
    - 实现启动优化按钮和参数配置
    - 实现目标分数和最大迭代次数设置
    - _需求：1.1, 8.1, 8.2_

  - [x] 17.2 创建进度面板
    - 创建 `frontend/src/components/ScriptOptimization/ProgressPanel.tsx`
    - 显示当前迭代次数和阶段
    - 显示当前分数
    - 显示实时状态消息
    - _需求：5.2_

  - [x] 17.3 创建分数可视化组件
    - 创建 `frontend/src/components/ScriptOptimization/ScoreChart.tsx`
    - 使用 Chart.js 或 Recharts 绘制分数曲线
    - 实时更新分数历史
    - _需求：5.2_

  - [x] 17.4 创建维度雷达图
    - 创建 `frontend/src/components/ScriptOptimization/RadarChart.tsx`
    - 显示五个评审维度的雷达图
    - 支持动画效果
    - _需求：5.5_

  - [x] 17.5 创建搜索可视化组件
    - 创建 `frontend/src/components/ScriptOptimization/SearchVisualizer.tsx`
    - 显示搜索动画（雷达扫描效果）
    - 显示热点列表和技巧列表
    - 实现卡片飞入动画
    - _需求：5.3_

  - [x] 17.6 创建版本历史组件
    - 创建 `frontend/src/components/ScriptOptimization/VersionHistory.tsx`
    - 显示所有版本的时间线
    - 支持版本选择和查看
    - 支持版本对比
    - _需求：6.2, 6.3_

- [x] 18. 实现前端动画效果
  - [x] 18.1 创建动画工具库
    - 创建 `frontend/src/utils/animations.ts`
    - 实现打字机效果
    - 实现粒子效果
    - 实现数字滚动效果
    - 实现进度条填充动画
    - 使用 Framer Motion 或 React Spring
    - _需求：5.3, 5.4, 5.5, 5.6_

- [x] 19. 集成前端主视图
  - [x] 19.1 创建 `frontend/src/views/ScriptOptimizationView.tsx`
    - 组合所有子组件
    - 实现布局和样式
    - 实现响应式设计
    - 添加炫酷的视觉效果（渐变、阴影、动画）
    - _需求：5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]\* 19.2 为前端组件编写单元测试
    - 测试组件渲染
    - 测试用户交互
    - 测试状态更新

- [x] 20. 实现配置管理界面
  - [x] 20.1 创建配置页面
    - 创建 `frontend/src/components/ScriptOptimization/ConfigPanel.tsx`
    - 支持配置目标分数
    - 支持配置最大迭代次数
    - 支持配置评审维度权重
    - 支持配置搜索 API 密钥
    - 实现配置验证
    - _需求：8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 21. 实现日志和统计
  - [x] 21.1 增强日志记录
    - 在所有关键操作点添加日志
    - 记录迭代统计信息
    - 实现日志查看界面（可选）
    - _需求：9.1, 9.4_

  - [ ]\* 21.2 为日志功能编写属性测试
    - **属性 18：迭代统计完整性**
    - **验证：需求 9.4**

- [x] 22. 端到端测试
  - [ ]\* 22.1 编写端到端测试
    - 测试完整的优化流程（从启动到完成）
    - 测试 WebSocket 实时更新
    - 测试版本管理
    - 测试错误处理和降级
    - 测试配置管理

- [x] 23. 最终检查点 - 系统完整性验证
  - 确保所有功能正常工作
  - 验证前后端集成
  - 验证所有测试通过
  - 验证文档完整
  - 如有问题请向用户询问

## 注意事项

- 标记 `*` 的任务为可选任务，可以跳过以加快 MVP 开发
- 每个任务都引用了具体的需求编号以确保可追溯性
- 检查点任务确保增量验证
- 属性测试验证通用正确性属性
- 单元测试验证特定示例和边界情况
- 集成测试验证端到端流程
