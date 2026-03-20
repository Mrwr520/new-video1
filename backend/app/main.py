"""FastAPI 应用入口"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.api.projects import router as projects_router
from app.api.templates import router as templates_router
from app.api.characters import router as characters_router
from app.api.scenes import router as scenes_router
from app.api.tts import router as tts_router, projects_tts_router
from app.api.export import router as export_router
from app.api.events import router as events_router
from app.api.config import router as config_router
from app.api.models import router as models_router
from app.api.environment import router as environment_router
from app.api.script_optimization import router as script_optimization_router
from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时初始化数据库"""
    await init_db()
    yield


app = FastAPI(
    title="AI 视频生成器后端",
    version="0.1.0",
    lifespan=lifespan,
)

# 配置 CORS，允许 Electron 前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(projects_router)
app.include_router(templates_router)
app.include_router(characters_router)
app.include_router(scenes_router)
app.include_router(tts_router)
app.include_router(projects_tts_router)
app.include_router(export_router)
app.include_router(events_router)
app.include_router(config_router)
app.include_router(models_router)
app.include_router(environment_router)
app.include_router(script_optimization_router)

# 挂载静态文件目录，提供项目资源访问（图片、音频、视频等）
projects_dir = Path(__file__).parent.parent / "data" / "projects"
projects_dir.mkdir(parents=True, exist_ok=True)
app.mount("/projects", StaticFiles(directory=str(projects_dir)), name="projects")
