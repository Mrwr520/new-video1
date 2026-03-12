"""配置管理 API - GET/PUT /api/config"""

import json
from pathlib import Path
from typing import Optional

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
    image_gen_mode: str = Field(
        default="local", description="图像生成模式: local (本地SDXL) 或 api (远程API)"
    )
    image_gen_api_key: str = Field(default="", description="图像生成 API 密钥")
    image_gen_api_url: str = Field(default="", description="图像生成 API 地址")
    tts_engine: str = Field(
        default="edge-tts", description="TTS 引擎选择"
    )
    # 收费 TTS 引擎 API Key 配置
    fish_audio_api_key: str = Field(default="", description="Fish Audio API Key")
    cosyvoice_api_key: str = Field(default="", description="CosyVoice (阿里 DashScope) API Key")
    minimax_api_key: str = Field(default="", description="MiniMax API Key")
    minimax_group_id: str = Field(default="", description="MiniMax Group ID")
    volcengine_access_token: str = Field(default="", description="火山引擎 Access Token")
    volcengine_app_id: str = Field(default="", description="火山引擎 App ID")


class AppConfigUpdate(BaseModel):
    """配置更新模型（所有字段可选，支持部分更新）"""
    python_path: Optional[str] = None
    gpu_device: Optional[int] = None
    backend_port: Optional[int] = None
    llm_api_key: Optional[str] = None
    llm_api_url: Optional[str] = None
    image_gen_mode: Optional[str] = None
    image_gen_api_key: Optional[str] = None
    image_gen_api_url: Optional[str] = None
    tts_engine: Optional[str] = None
    fish_audio_api_key: Optional[str] = None
    cosyvoice_api_key: Optional[str] = None
    minimax_api_key: Optional[str] = None
    minimax_group_id: Optional[str] = None
    volcengine_access_token: Optional[str] = None
    volcengine_app_id: Optional[str] = None


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

    # 如果 TTS 相关配置变更，重置 TTS 服务单例
    tts_fields = {
        "tts_engine", "fish_audio_api_key", "cosyvoice_api_key",
        "minimax_api_key", "minimax_group_id",
        "volcengine_access_token", "volcengine_app_id",
    }
    if tts_fields & set(update_data.keys()):
        try:
            from app.api.tts import reset_tts_service
            reset_tts_service()
        except ImportError:
            pass

    return updated
