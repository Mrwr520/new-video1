# AI 视频生成器

将小说文本（或科普、数学讲解等内容）自动转化为可发布的高质量视频。

系统通过 LLM 提取角色信息并生成分镜脚本，利用 AI 图像生成模型创建关键帧，再通过 FramePack 将静态图片转化为动态视频片段，最终结合 TTS 配音和 FFmpeg 合成为完整视频。

## 特性亮点

- **开箱即用** — 本地模型自动下载管理，无需手动配置环境
- **图像生成双模式** — 本地 SDXL 模型（免费，需 GPU）或远程 API（DALL-E / Flux 等）
- **视频生成本地化** — FramePack (HunyuanVideo) 本地推理，6GB 显存即可运行
- **智能显存协调** — 图像模型和视频模型交替使用 GPU，自动加载/卸载
- **模型管理界面** — 设置页集成 GPU 检测、模型下载进度、一键管理
- **多 TTS 引擎** — Edge-TTS / ChatTTS（免费）+ Fish Audio / CosyVoice / MiniMax / 火山引擎（收费）
- **三种内容模板** — 动漫、科普、数学讲解，支持自定义扩展

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 桌面客户端 | Electron + React + TypeScript |
| 后端服务 | Python FastAPI + SQLite (aiosqlite) |
| 图像生成 | Stable Diffusion XL（本地）/ OpenAI 兼容 API（远程） |
| 视频生成 | FramePack (HunyuanVideo 架构，6GB 显存) |
| 模型管理 | huggingface_hub（自动下载 + 断点续传） |
| 语音合成 | Edge-TTS / ChatTTS / Fish Audio / CosyVoice / MiniMax / 火山引擎 |
| 视频合成 | FFmpeg |
| 测试 | vitest + fast-check (前端)，pytest + hypothesis (后端) |

## 项目结构

```text
├── frontend/                  # Electron + React 前端
│   ├── src/
│   │   ├── main/              # Electron 主进程（含 PythonManager）
│   │   ├── preload/           # 预加载脚本
│   │   └── renderer/          # React 渲染进程
│   │       ├── pages/         # 页面组件（含模型管理页）
│   │       ├── components/    # 通用组件
│   │       └── services/      # API 客户端
│   └── package.json
│
├── backend/                   # Python FastAPI 后端
│   ├── app/
│   │   ├── api/               # REST API 路由（含模型管理 API）
│   │   ├── models/            # Pydantic 数据模型
│   │   ├── services/          # 业务服务模块
│   │   │   ├── model_manager.py       # 模型下载/缓存/GPU 管理
│   │   │   ├── local_image_service.py # 本地 SDXL 图像生成
│   │   │   ├── image_service.py       # 远程 API 图像生成
│   │   │   ├── framepack_service.py   # FramePack 视频生成
│   │   │   ├── llm_service.py         # LLM 角色提取 & 分镜生成
│   │   │   ├── tts_service.py         # TTS 语音合成
│   │   │   └── ffmpeg_service.py      # FFmpeg 视频合成
│   │   ├── pipeline/          # Pipeline 编排引擎
│   │   ├── database.py        # SQLite 数据库管理
│   │   └── main.py            # FastAPI 应用入口
│   ├── tests/                 # 单元测试 + 属性测试
│   └── pyproject.toml
│
└── .kiro/specs/               # 功能规格文档
```

## 快速开始

### 环境要求

- Node.js >= 18
- Python >= 3.10
- FFmpeg（用于视频合成）
- NVIDIA GPU（6GB+ 显存，用于本地图像/视频生成）
  - 没有 GPU 时，图像生成可切换为远程 API 模式

### 安装后端

```bash
cd backend
pip install -e ".[dev]"
```

### 安装前端

```bash
cd frontend
npm install
```

### 开发模式运行

```bash
# 终端 1：启动后端
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 终端 2：启动前端
cd frontend
npm run dev
```

> 正式使用时，Electron 主进程会自动管理 Python 后端的生命周期，无需手动启动。

### 首次使用

1. 启动应用后进入「设置」页面
2. 查看 GPU 环境检测结果
3. 点击「下载模型」下载 SDXL（关键帧）和 HunyuanVideo（视频）模型
4. 模型下载完成后即可开始创作，后续使用无需联网
5. 如果没有 GPU，可将图像生成切换为「远程 API」模式并配置 API Key

### 运行测试

```bash
# 后端测试
cd backend
python -m pytest -v

# 前端测试
cd frontend
npm test
```

## 核心流程

```text
文本输入 → 角色提取 (LLM) → 分镜生成 (LLM) → 关键帧生成 (本地SDXL/远程API)
    → FramePack 视频生成 → TTS 语音配音 → FFmpeg 合成导出
```

每个阶段由独立的服务模块驱动，Pipeline 引擎负责编排执行。用户可在角色提取和分镜生成后进行人工确认和编辑。

图像模型和视频模型共享同一块 GPU，按阶段串行使用：先加载 SDXL 生成所有关键帧 → 卸载 SDXL → 加载 HunyuanVideo 生成视频片段 → 卸载。

## 内容模板

内置三种内容模板，支持自定义扩展：

- **动漫** — 动漫风格图像参数，情节推进分镜策略
- **科普** — 信息图表风格，知识点拆分策略
- **数学讲解** — 黑板风格，推导过程可视化策略

## API 概览

| 端点 | 说明 |
| --- | --- |
| `GET /api/health` | 健康检查 |
| `POST /api/projects` | 创建项目 |
| `GET /api/projects` | 项目列表 |
| `GET /api/projects/{id}` | 项目详情 |
| `DELETE /api/projects/{id}` | 删除项目 |
| `POST /api/projects/{id}/text` | 提交文本 |
| `POST /api/projects/{id}/confirm-characters` | 确认角色 |
| `POST /api/projects/{id}/confirm-storyboard` | 确认分镜 |
| `POST /api/projects/{id}/export` | 导出视频 |
| `GET /api/projects/{id}/events` | SSE 事件流 |
| `GET /api/templates` | 模板列表 |
| `GET /api/config` | 获取配置 |
| `PUT /api/config` | 更新配置 |
| `GET /api/models` | 模型列表及状态 |
| `POST /api/models/{id}/download` | 触发模型下载 |
| `DELETE /api/models/{id}` | 删除本地模型缓存 |
| `GET /api/gpu` | GPU 环境信息 |

## 许可证

MIT
