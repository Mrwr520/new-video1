# AI 视频生成器

将小说文本（或科普、数学讲解等内容）自动转化为可发布的高质量视频。

系统通过 LLM 提取角色信息并生成分镜脚本，利用 AI 图像生成模型创建关键帧，再通过 FramePack 将静态图片转化为动态视频片段，最终结合 TTS 配音和 FFmpeg 合成为完整视频。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 桌面客户端 | Electron + React + TypeScript |
| 后端服务 | Python FastAPI + SQLite (aiosqlite) |
| 视频生成 | FramePack (HunyuanVideo 架构，6GB 显存) |
| 语音合成 | Edge-TTS / ChatTTS（可插拔适配器） |
| 视频合成 | FFmpeg |
| 测试 | vitest + fast-check (前端)，pytest + hypothesis (后端) |

## 项目结构

```
├── frontend/                  # Electron + React 前端
│   ├── src/
│   │   ├── main/              # Electron 主进程（含 PythonManager）
│   │   ├── preload/           # 预加载脚本
│   │   └── renderer/          # React 渲染进程
│   │       ├── pages/         # 页面组件
│   │       ├── components/    # 通用组件
│   │       └── services/      # API 客户端
│   └── package.json
│
├── backend/                   # Python FastAPI 后端
│   ├── app/
│   │   ├── api/               # REST API 路由
│   │   ├── models/            # Pydantic 数据模型
│   │   ├── services/          # 业务服务模块
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
- NVIDIA GPU（6GB+ 显存，用于 FramePack 推理）

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

```
文本输入 → 角色提取 (LLM) → 分镜生成 (LLM) → 关键帧生成 (AI 图像)
    → FramePack 视频生成 → TTS 语音配音 → FFmpeg 合成导出
```

每个阶段由独立的服务模块驱动，Pipeline 引擎负责编排执行。用户可在角色提取和分镜生成后进行人工确认和编辑。

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

## 许可证

MIT
