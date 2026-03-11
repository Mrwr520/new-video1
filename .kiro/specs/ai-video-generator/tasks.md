# 实现计划：AI 视频生成器

## 概述

基于 Electron + React (TypeScript) 前端和 Python FastAPI 后端的架构，按模块逐步实现完整的文本到视频生成 Pipeline。先搭建基础框架和通信层，再逐个实现服务模块，最后集成 Pipeline 编排和视频合成。

## 任务

- [x] 1. 搭建项目基础结构和开发环境
  - [x] 1.1 初始化 Electron + React + TypeScript 前端项目
    - 使用 electron-vite 脚手架创建项目
    - 配置 React、TypeScript、React Router
    - 创建基础页面路由结构（项目列表、项目工作台、设置页）
    - 配置 vitest 测试框架
    - _Requirements: 8.1_
  - [x] 1.2 初始化 Python FastAPI 后端项目
    - 创建 Python 项目结构（api/、services/、models/、pipeline/）
    - 配置 FastAPI 应用和 CORS
    - 配置 SQLite 数据库连接（使用 aiosqlite）
    - 创建数据库表结构（projects、characters、scenes、pipeline_states）
    - 配置 pytest + hypothesis 测试框架
    - _Requirements: 9.4_
  - [x] 1.3 实现 Electron 主进程的 Python 后端生命周期管理
    - 实现 PythonManager 类（start/stop/restart/healthCheck）
    - 通过子进程启动 Python 后端
    - 实现健康检查轮询机制
    - 实现应用关闭时的安全终止逻辑
    - _Requirements: 9.1, 9.2, 9.3, 9.5_

- [x] 2. 检查点 - 确保基础框架搭建完成
  - 确保 Electron 应用能启动并自动拉起 Python 后端
  - 确保前端能通过 HTTP 调用后端健康检查接口
  - 确保所有测试通过，如有问题请询问用户

- [x] 3. 实现项目管理和数据持久化
  - [x] 3.1 实现后端项目 CRUD API
    - 实现 POST /api/projects（创建项目，初始化目录结构）
    - 实现 GET /api/projects（项目列表）
    - 实现 GET /api/projects/{id}（项目详情，含状态恢复）
    - 实现 DELETE /api/projects/{id}（删除项目及文件）
    - _Requirements: 8.1, 8.2, 8.3_
  - [x] 3.2 编写项目持久化往返属性测试
    - **Property 12: 项目持久化往返一致性**
    - 使用 hypothesis 生成随机项目数据，验证创建后读取得到等价数据
    - **Validates: Requirements 8.2, 8.3**
  - [x] 3.3 实现前端项目列表页和创建项目流程
    - 实现项目列表页组件（展示项目名称、状态、创建时间）
    - 实现创建项目对话框（项目名称、内容类型选择）
    - 实现 ApiClient 的项目管理方法
    - _Requirements: 8.1, 8.2_

- [x] 4. 实现文本输入与校验模块
  - [x] 4.1 实现后端文本提交和校验 API
    - 实现 POST /api/projects/{id}/text 端点
    - 实现文本校验逻辑（非空、最小长度、最大长度）
    - 实现 TXT 和 Markdown 文件内容解析
    - _Requirements: 1.1, 1.2, 1.3, 1.5_
  - [x] 4.2 编写文本校验属性测试
    - **Property 1: 文本校验正确性**
    - 使用 hypothesis 生成随机字符串，验证校验函数对空/短/超长/有效文本的判断
    - **Validates: Requirements 1.3, 1.5**
  - [x] 4.3 编写文本存储往返属性测试
    - **Property 2: 文本存储往返一致性**
    - **Property 3: 文件导入往返一致性**
    - **Validates: Requirements 1.1, 1.2**
  - [x] 4.4 实现前端文本输入页面
    - 实现文本粘贴输入区域（支持大文本）
    - 实现文件导入功能（TXT、Markdown）
    - 实现内容类型选择器
    - 实现字数统计和校验反馈
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [ ] 5. 实现内容模板系统
  - [-] 5.1 实现模板服务和内置模板
    - 实现 TemplateService 类
    - 创建动漫模板（anime）：动漫风格图像参数、情节推进分镜策略
    - 创建科普模板（science）：图表风格、知识点拆分策略
    - 创建数学模板（math）：公式展示、推导过程可视化策略
    - 实现模板 CRUD API 端点
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  - [~] 5.2 编写模板相关属性测试
    - **Property 4: 模板加载正确性**
    - **Property 14: 模板自定义往返一致性**
    - **Validates: Requirements 1.4, 10.5**

- [~] 6. 检查点 - 确保项目管理和文本输入功能完整
  - 确保所有测试通过，如有问题请询问用户

- [ ] 7. 实现 LLM 服务（角色提取 + 分镜生成）
  - [~] 7.1 实现 LLM 服务核心
    - 实现 LLMService 类，支持 OpenAI 兼容 API
    - 实现角色提取功能（extract_characters），包含结构化 prompt 模板
    - 实现分镜脚本生成功能（generate_storyboard），包含结构化 prompt 模板
    - 实现 LLM 响应解析和错误处理
    - _Requirements: 2.1, 3.1, 3.6_
  - [~] 7.2 实现角色管理 API 和前端
    - 实现 POST /api/projects/{id}/confirm-characters
    - 实现 PUT /api/projects/{id}/characters/{cid}
    - 实现前端角色列表展示和编辑组件
    - 实现手动添加角色功能（LLM 失败时的降级方案）
    - _Requirements: 2.2, 2.3, 2.4, 2.5_
  - [~] 7.3 编写角色数据属性测试
    - **Property 5: 角色数据持久化往返一致性**
    - **Validates: Requirements 2.3, 2.4**
  - [~] 7.4 实现分镜管理 API 和前端
    - 实现 POST /api/projects/{id}/confirm-storyboard
    - 实现 PUT /api/projects/{id}/scenes/{sid}
    - 实现 PUT /api/projects/{id}/scenes/reorder
    - 实现前端分镜时间线视图（展示、编辑、拖拽排序）
    - _Requirements: 3.2, 3.3, 3.4, 3.5_
  - [~] 7.5 编写分镜相关属性测试
    - **Property 6: 分镜结构完整性不变量**
    - **Property 7: 分镜更新正确性**
    - **Property 8: 分镜重排序数据保持不变量**
    - **Validates: Requirements 3.2, 3.4, 3.5**

- [ ] 8. 实现图像生成服务
  - [~] 8.1 实现图像生成服务核心
    - 实现 ImageGeneratorService 类
    - 支持外部 API 调用（Stable Diffusion API、Flux 等 OpenAI 兼容图像接口）
    - 实现 prompt 构建逻辑（结合场景描述 + 角色外貌 + 模板风格）
    - 实现关键帧图片下载和存储
    - _Requirements: 4.1, 4.2, 4.6_
  - [~] 8.2 实现关键帧管理 API 和前端
    - 实现 POST /api/projects/{id}/scenes/{sid}/regenerate-keyframe
    - 实现前端关键帧展示（在分镜位置显示图片）
    - 实现重新生成按钮和加载状态
    - _Requirements: 4.3, 4.4, 4.5_

- [ ] 9. 实现 FramePack 视频生成引擎
  - [~] 9.1 实现 FramePack 服务封装
    - 实现 FramePackService 类
    - 集成 FramePack 模型加载/卸载逻辑
    - 实现图片转视频生成功能（支持 prompt、duration、fps 参数）
    - 实现 TeaCache 加速选项
    - 实现 GPU 信息查询
    - _Requirements: 5.1, 5.2, 5.4, 5.6_
  - [~] 9.2 实现视频片段管理 API 和前端
    - 实现 POST /api/projects/{id}/scenes/{sid}/regenerate-video
    - 实现前端视频片段预览播放器
    - 实现重新生成和参数调整界面
    - _Requirements: 5.3, 5.5_

- [~] 10. 检查点 - 确保图像和视频生成功能正常
  - 确保所有测试通过，如有问题请询问用户

- [ ] 11. 实现 TTS 语音配音服务
  - [~] 11.1 实现 TTS 可插拔适配器架构
    - 实现 TTSAdapter 抽象基类
    - 实现 EdgeTTSAdapter（Edge-TTS 免费引擎）
    - 实现 ChatTTSAdapter（ChatTTS 本地引擎）
    - 预留 FishSpeechAdapter、CosyVoiceAdapter、MiniMaxTTSAdapter、VolcEngineTTSAdapter 的适配器骨架
    - 实现 TTSService 管理器（引擎注册、选择、调用）
    - 实现角色语音分配逻辑（不同角色分配不同 voice_id）
    - _Requirements: 6.1, 6.2, 6.4_
  - [~] 11.2 编写语音分配属性测试
    - **Property 9: 角色语音分配唯一性**
    - **Validates: Requirements 6.2**
  - [~] 11.3 实现 TTS 相关 API 和前端
    - 实现语音引擎列表和语音列表 API
    - 实现前端音频预览播放组件
    - 实现语音引擎选择和配置界面
    - _Requirements: 6.3, 6.5, 6.6_


- [ ] 12. 实现 FFmpeg 视频合成服务
  - [~] 12.1 实现 FFmpeg 合成器核心
    - 实现 FFmpegCompositor 类
    - 实现视频片段按顺序拼接功能
    - 实现音视频同步合成功能
    - 实现字幕生成（SRT 格式）和嵌入功能
    - 实现转场效果（fade 等）
    - 实现 MP4 导出（1080p、h264 编码）
    - _Requirements: 7.1, 7.2, 7.3, 7.5, 7.6_
  - [~] 12.2 编写合成相关属性测试
    - **Property 10: 视频合成排序与音视频同步正确性**
    - **Property 11: 字幕生成完整性**
    - **Validates: Requirements 7.1, 7.2, 7.3**
  - [~] 12.3 实现导出 API 和前端
    - 实现 POST /api/projects/{id}/export
    - 实现前端完整视频预览播放器
    - 实现导出按钮和进度显示
    - _Requirements: 7.4, 7.5, 7.7_

- [ ] 13. 实现 Pipeline 编排引擎和 SSE 事件流
  - [~] 13.1 实现 Pipeline 状态机
    - 实现 PipelineEngine 类（start/cancel/resume）
    - 实现六个步骤的顺序执行逻辑
    - 实现步骤间的等待用户确认机制（角色确认、分镜确认）
    - 实现每步完成后的自动保存
    - 实现取消时的安全终止和中间结果保存
    - _Requirements: 8.4, 8.6_
  - [~] 13.2 编写 Pipeline 自动保存属性测试
    - **Property 13: Pipeline 步骤完成后自动保存**
    - **Validates: Requirements 8.4**
  - [~] 13.3 实现 SSE 事件流
    - 实现 GET /api/projects/{id}/events SSE 端点
    - 推送 Pipeline 各步骤的进度更新
    - 推送错误事件和完成事件
    - 实现前端 SSE 订阅和进度条展示
    - _Requirements: 8.5_

- [ ] 14. 实现设置页面和配置管理
  - [~] 14.1 实现后端配置 API
    - 实现 GET /api/config 和 PUT /api/config
    - 支持 Python 路径、GPU 设备、LLM API 配置、图像 API 配置、TTS 引擎选择
    - 实现配置持久化（JSON 文件）
    - _Requirements: 9.6_
  - [~] 14.2 实现前端设置页面
    - 实现 Python 环境配置表单
    - 实现 GPU 配置选项
    - 实现 LLM API 和图像生成 API 配置表单
    - 实现 TTS 引擎选择和收费引擎 API Key 配置
    - _Requirements: 9.6_

- [ ] 15. 全流程集成和端到端联调
  - [~] 15.1 集成所有服务模块到 Pipeline
    - 将 LLM、图像生成、FramePack、TTS、FFmpeg 服务串联到 Pipeline 引擎
    - 实现前端完整工作流界面（文本输入 → 角色确认 → 分镜确认 → 生成 → 预览 → 导出）
    - 实现资源文件服务（GET /api/projects/{id}/files/{path}）
    - _Requirements: 全部_
  - [~] 15.2 编写 API 集成测试
    - 测试完整的项目创建到导出流程（使用 mock 服务）
    - 测试错误处理和重试逻辑
    - 测试 Pipeline 取消和恢复
    - _Requirements: 全部_

- [~] 16. 最终检查点 - 确保所有测试通过
  - 确保所有单元测试和属性测试通过
  - 确保前后端联调正常
  - 如有问题请询问用户

## 说明

- 所有任务均为必需任务，包括属性测试和集成测试
- 每个任务引用了具体的需求编号以确保可追溯性
- 检查点任务用于阶段性验证，确保增量开发的稳定性
- 属性测试验证设计文档中定义的通用正确性属性
- 单元测试验证具体示例和边界情况
