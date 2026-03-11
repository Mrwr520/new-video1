# 需求文档

## 简介

AI 视频生成器是一款 Electron 桌面端应用，能够将小说文本（或其他文本内容如科普、数学讲解）自动转化为可发布的高质量视频。系统通过 LLM 提取角色信息并生成分镜脚本，利用 AI 图像生成模型创建关键帧，再通过 FramePack 将静态图片转化为动态视频片段，最终结合 TTS 配音和 FFmpeg 合成为完整的可发布视频。

## 术语表

- **Pipeline**：视频生成的完整处理流水线，从文本输入到最终视频输出的全部自动化步骤
- **分镜脚本（Storyboard_Script）**：将文本拆解后生成的结构化数据，包含场景描述、台词/旁白、镜头指示
- **关键帧（Keyframe）**：由 AI 图像生成模型为每个分镜生成的静态图片
- **FramePack_Engine**：基于 HunyuanVideo 架构的图片转动态视频引擎，仅需 6GB 显存
- **TTS_Engine**：文本转语音引擎，用于生成旁白和角色对话的语音
- **FFmpeg_Compositor**：基于 FFmpeg 的视频合成模块，负责将视频片段、音频、字幕合成为最终视频
- **LLM_Service**：大语言模型服务，用于角色提取和分镜脚本生成
- **Image_Generator**：AI 图像生成服务，用于生成分镜关键帧图片
- **Python_Backend**：Python 后端服务，承载 FramePack 和 AI 模型的运行
- **Electron_App**：基于 Electron 框架的桌面客户端应用
- **内容模板（Content_Template）**：针对不同内容类型（动漫、科普、数学等）的 prompt 策略和生成参数配置

## 需求

### 需求 1：文本输入与管理

**用户故事：** 作为用户，我希望能够输入或导入小说/文本内容，以便系统能够处理并生成视频。

#### 验收标准

1. WHEN 用户粘贴文本到输入区域, THE Electron_App SHALL 接受并存储该文本内容
2. WHEN 用户选择导入文件, THE Electron_App SHALL 支持导入 TXT 和 Markdown 格式的文件
3. WHEN 文本内容超过系统处理上限, THE Electron_App SHALL 显示明确的字数限制提示并阻止提交
4. WHEN 用户选择内容类型（动漫、科普、数学等）, THE Electron_App SHALL 加载对应的 Content_Template 配置
5. WHEN 用户提交文本, THE Electron_App SHALL 对文本进行基础校验（非空、最小长度）并给出校验结果反馈

### 需求 2：角色信息提取

**用户故事：** 作为用户，我希望系统能自动从文本中提取角色信息，以便后续生成一致的角色形象。

#### 验收标准

1. WHEN 文本提交后, THE LLM_Service SHALL 自动分析文本并提取所有角色的外貌描述、性格特征和背景信息
2. WHEN 角色提取完成, THE Electron_App SHALL 以列表形式展示所有提取到的角色及其属性
3. WHEN 用户编辑角色信息, THE Electron_App SHALL 允许用户修改角色的外貌、性格和背景描述
4. WHEN 用户确认角色信息, THE Electron_App SHALL 将角色数据持久化存储以供后续 Pipeline 步骤使用
5. IF LLM_Service 提取角色失败, THEN THE Electron_App SHALL 显示错误信息并允许用户手动添加角色

### 需求 3：分镜脚本生成

**用户故事：** 作为用户，我希望系统能自动将文本拆解为分镜脚本，以便逐个场景生成视频。

#### 验收标准

1. WHEN 角色信息确认后, THE LLM_Service SHALL 将文本拆解为有序的分镜脚本列表
2. THE 分镜脚本 SHALL 包含场景描述、台词或旁白文本、镜头指示（如远景、近景、特写）三个必要字段
3. WHEN 分镜脚本生成完成, THE Electron_App SHALL 以时间线视图展示所有分镜
4. WHEN 用户编辑某个分镜, THE Electron_App SHALL 允许修改场景描述、台词和镜头指示
5. WHEN 用户调整分镜顺序, THE Electron_App SHALL 支持拖拽排序并更新时间线
6. WHILE 使用不同的 Content_Template, THE LLM_Service SHALL 根据模板类型调整分镜生成策略（如科普类侧重知识点拆分，动漫类侧重情节推进）

### 需求 4：关键帧图片生成

**用户故事：** 作为用户，我希望系统能为每个分镜生成高质量的关键帧图片，以便作为视频生成的基础素材。

#### 验收标准

1. WHEN 分镜脚本确认后, THE Image_Generator SHALL 根据场景描述和角色信息为每个分镜生成关键帧图片
2. THE Image_Generator SHALL 在同一项目中保持角色外貌的视觉一致性
3. WHEN 关键帧生成完成, THE Electron_App SHALL 在对应分镜位置展示生成的图片
4. WHEN 用户对某张关键帧不满意, THE Electron_App SHALL 提供重新生成该帧的功能
5. IF Image_Generator 生成图片失败, THEN THE Electron_App SHALL 显示错误信息并提供重试选项
6. THE Image_Generator SHALL 生成分辨率不低于 1024x576（16:9）的关键帧图片


### 需求 5：FramePack 动态视频生成

**用户故事：** 作为用户，我希望系统能将静态关键帧图片转化为真正能动的视频片段，而非简单的图片轮播。

#### 验收标准

1. WHEN 关键帧图片准备就绪, THE FramePack_Engine SHALL 将每张关键帧转化为动态视频片段
2. THE FramePack_Engine SHALL 生成流畅的动态效果，包含合理的运动和过渡
3. WHEN 视频片段生成完成, THE Electron_App SHALL 提供每个片段的预览播放功能
4. THE FramePack_Engine SHALL 在 6GB 显存的 GPU 上正常运行
5. IF FramePack_Engine 生成视频失败, THEN THE Electron_App SHALL 显示错误详情并提供重试选项
6. WHEN 用户指定视频风格参数, THE FramePack_Engine SHALL 根据参数调整生成效果（如运动幅度、帧率）

### 需求 6：TTS 语音配音

**用户故事：** 作为用户，我希望系统能自动为旁白和角色对话生成语音配音，以便视频有完整的音频。

#### 验收标准

1. WHEN 分镜脚本中包含台词或旁白, THE TTS_Engine SHALL 为每段文本生成对应的语音音频
2. WHEN 存在多个角色对话, THE TTS_Engine SHALL 为不同角色分配不同的语音风格
3. WHEN 语音生成完成, THE Electron_App SHALL 提供音频预览和播放功能
4. WHEN 用户选择语音引擎（Edge-TTS 或 ChatTTS）, THE TTS_Engine SHALL 使用指定的引擎生成语音
5. IF TTS_Engine 生成语音失败, THEN THE Electron_App SHALL 显示错误信息并提供重试选项
6. THE TTS_Engine SHALL 生成采样率不低于 16kHz 的音频文件

### 需求 7：视频合成与导出

**用户故事：** 作为用户，我希望系统能将所有视频片段、音频和字幕合成为一个完整的可发布视频。

#### 验收标准

1. WHEN 所有视频片段和音频准备就绪, THE FFmpeg_Compositor SHALL 将视频片段按分镜顺序拼接
2. THE FFmpeg_Compositor SHALL 将对应的语音音频与视频片段精确同步
3. THE FFmpeg_Compositor SHALL 根据台词和旁白文本自动生成并嵌入字幕
4. WHEN 合成完成, THE Electron_App SHALL 提供完整视频的预览播放功能
5. WHEN 用户选择导出, THE FFmpeg_Compositor SHALL 输出 MP4 格式的视频文件，分辨率不低于 1080p
6. THE FFmpeg_Compositor SHALL 在视频片段之间添加平滑的转场效果
7. IF FFmpeg_Compositor 合成失败, THEN THE Electron_App SHALL 显示错误详情并提供重试选项

### 需求 8：项目管理与工作流

**用户故事：** 作为用户，我希望能够管理多个视频生成项目，并能随时查看和继续之前的工作。

#### 验收标准

1. THE Electron_App SHALL 提供项目列表页面，展示所有已创建的项目及其状态
2. WHEN 用户创建新项目, THE Electron_App SHALL 初始化项目目录结构并保存项目元数据
3. WHEN 用户打开已有项目, THE Electron_App SHALL 恢复到该项目上次的工作状态
4. THE Electron_App SHALL 在 Pipeline 的每个步骤完成后自动保存项目进度
5. WHEN Pipeline 执行中, THE Electron_App SHALL 显示当前步骤的进度条和预计剩余时间
6. WHEN 用户取消正在执行的 Pipeline, THE Electron_App SHALL 安全终止所有子进程并保存已完成的中间结果

### 需求 9：Python 后端服务管理

**用户故事：** 作为用户，我希望应用能自动管理 Python 后端服务的生命周期，无需手动启动或配置。

#### 验收标准

1. WHEN Electron_App 启动时, THE Electron_App SHALL 自动启动 Python_Backend 服务
2. WHEN Electron_App 关闭时, THE Electron_App SHALL 安全终止 Python_Backend 服务及其所有子进程
3. IF Python_Backend 启动失败, THEN THE Electron_App SHALL 显示诊断信息（如 Python 版本、依赖缺失）并提供修复建议
4. THE Electron_App SHALL 通过 HTTP API 与 Python_Backend 进行通信
5. WHEN Python_Backend 服务异常崩溃, THE Electron_App SHALL 检测到服务中断并提供自动重启选项
6. THE Electron_App SHALL 在设置页面提供 Python 环境路径和 GPU 配置选项

### 需求 10：多内容类型模板系统

**用户故事：** 作为用户，我希望系统支持多种内容类型的视频生成，不仅限于动漫小说。

#### 验收标准

1. THE Electron_App SHALL 提供内置的内容模板，至少包含动漫、科普和数学讲解三种类型
2. WHEN 用户选择动漫模板, THE Content_Template SHALL 配置适合动漫风格的图像生成参数和分镜策略
3. WHEN 用户选择科普模板, THE Content_Template SHALL 配置适合科普内容的图表生成和知识点拆分策略
4. WHEN 用户选择数学模板, THE Content_Template SHALL 配置适合数学公式展示和推导过程的可视化策略
5. THE Electron_App SHALL 允许用户自定义模板参数（如图像风格、语音风格、字幕样式）
