"""配置管理 API - GET/PUT /api/config"""

import json
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.database import get_db_path

router = APIRouter(prefix="/api")


class AppConfig(BaseModel):
    """应用配置模型"""
    python_path: str = Field(default="python", description="Python 解释器路径")
    gpu_device: int = Field(default=0, description="GPU 设备编号")
    backend_port: int = Field(default=8000, description="后端服务端口")
    llm_api_key: str = Field(default="", description="LLM API 密钥")
    llm_api_url: str = Field(default="", description="LLM API 地址")
    image_gen_api_key: str = Field(default="", description="图像生成 API 密钥")
    image_gen_api_url: str = Field(default="", description="图像生成 API 地址")
    tts_engine: Literal["edge-tts", "chattts"] = Field(
        default="edge-tts", description="TTS 引擎选择"
    )


class AppConfigUpdate(BaseModel):
    """配置更新模型（所有字段可选，支持部分更新）"""
    python_path: Optional[str] = None
    gpu_device: Optional[int] = None
    backend_port: Optional[int] = None
    llm_api_key: Optional[str] = None
    llm_api_url: Optional[str] = None
    image_gen_api_key: Optional[str] = None
    image_gen_api_url: Optional[str] = None
    tts_engine: Optional[Literal["edge-tts", "chattts"]] = None


def _get_config_path() -> Path:
    """获取配置文件路径（与数据库同目录）"""
    return get_db_path().parent / "config.json"


def _load_config() -> AppConfig:
    """从 JSON 文件加载配置，文件不存在则返回默认配置"""
    config_path = _get_config_path()
    if config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        return AppConfig(**data)
    return AppConfig()


def _save_config(config: AppConfig) -> None:
    """将配置保存到 JSON 文件"""
    config_path = _get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(config.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


@router.get("/config")
async def get_config() -> AppConfig:
    """获取当前配置"""
    return _load_config()


@router.put("/config")
async def update_config(update: AppConfigUpdate) -> AppConfig:
    """更新配置（支持部分更新）"""
    current = _load_config()
    update_data = update.model_dump(exclude_none=True)
    updated = current.model_copy(update=update_data)
    _save_config(updated)
    return updated
