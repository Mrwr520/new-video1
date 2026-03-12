"""TTS 语音配音 API 路由

提供语音引擎列表、语音列表和语音生成端点。

Requirements:
    6.3: 语音生成完成后，提供音频预览和播放功能
    6.5: TTS_Engine 失败时，显示错误信息并提供重试选项
    6.6: TTS_Engine 生成采样率不低于 16kHz 的音频文件
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import get_connection
from app.services.tts_service import (
    TTSService,
    TTSError,
    TTSEngineNotFoundError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tts", tags=["tts"])

# 共享 TTSService 实例
_tts_service: Optional[TTSService] = None


def get_tts_service() -> TTSService:
    """获取或创建 TTSService 单例"""
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService()
    return _tts_service


# ============================================================
# 响应模型
# ============================================================

class EngineInfoResponse(BaseModel):
    name: str
    display_name: str
    is_paid: bool
    supported_languages: list[str]
    requires_api_key: bool
    description: str


class VoiceInfoResponse(BaseModel):
    id: str
    name: str
    language: str
    gender: str
    preview_url: Optional[str] = None


class GenerateSpeechRequest(BaseModel):
    engine: str = "edge-tts"
    voice_id: str = "zh-CN-XiaoxiaoNeural"


class GenerateSpeechResponse(BaseModel):
    audio_path: str
    scene_id: str
    engine: str
    voice_id: str


# ============================================================
# 引擎和语音列表端点
# ============================================================

@router.get("/engines", response_model=list[EngineInfoResponse])
async def list_engines():
    """列出所有可用的 TTS 引擎"""
    service = get_tts_service()
    engines = service.list_engines()
    return [
        EngineInfoResponse(
            name=e.name,
            display_name=e.display_name,
            is_paid=e.is_paid,
            supported_languages=e.supported_languages,
            requires_api_key=e.requires_api_key,
            description=e.description,
        )
        for e in engines
    ]


@router.get("/engines/{engine}/voices", response_model=list[VoiceInfoResponse])
async def list_voices(engine: str):
    """列出指定引擎的可用语音"""
    service = get_tts_service()
    try:
        voices = await service.list_voices(engine)
    except TTSEngineNotFoundError:
        raise HTTPException(status_code=404, detail=f"TTS 引擎 '{engine}' 不存在")
    return [
        VoiceInfoResponse(
            id=v.id,
            name=v.name,
            language=v.language,
            gender=v.gender,
            preview_url=v.preview_url,
        )
        for v in voices
    ]


# ============================================================
# 语音生成端点（挂载在 /api/projects 路径下）
# ============================================================

projects_tts_router = APIRouter(prefix="/api/projects", tags=["tts"])


@projects_tts_router.post("/{project_id}/scenes/{scene_id}/generate-speech")
async def generate_speech(
    project_id: str,
    scene_id: str,
    req: GenerateSpeechRequest = GenerateSpeechRequest(),
):
    """为指定分镜生成语音配音

    Requirements:
        6.3: 语音生成完成后，提供音频预览和播放
        6.5: 失败时显示错误信息并提供重试选项
        6.6: 采样率不低于 16kHz
    """
    conn = await get_connection()
    try:
        # 验证项目存在
        cursor = await conn.execute(
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="项目不存在")

        # 验证分镜存在并获取台词文本
        cursor = await conn.execute(
            "SELECT * FROM scenes WHERE id = ? AND project_id = ?",
            (scene_id, project_id),
        )
        scene_row = await cursor.fetchone()
        if not scene_row:
            raise HTTPException(status_code=404, detail="分镜不存在")

        dialogue = scene_row["dialogue"]
        if not dialogue or not dialogue.strip():
            raise HTTPException(status_code=400, detail="该分镜没有台词/旁白文本，无法生成语音")

        # 调用 TTS 服务生成语音
        service = get_tts_service()
        try:
            audio_path = await service.generate_speech(
                text=dialogue,
                voice_id=req.voice_id,
                engine=req.engine,
                project_id=project_id,
                scene_id=scene_id,
            )
        except TTSEngineNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"TTS 引擎 '{req.engine}' 不存在",
            )
        except TTSError as e:
            logger.error("语音生成失败: %s", e)
            raise HTTPException(
                status_code=502,
                detail={
                    "code": e.code,
                    "message": f"语音生成失败: {e}",
                    "retryable": e.retryable,
                },
            )

        # 更新数据库中的 audio_path
        now = datetime.now(timezone.utc).isoformat()
        await conn.execute(
            "UPDATE scenes SET audio_path = ? WHERE id = ? AND project_id = ?",
            (audio_path, scene_id, project_id),
        )
        await conn.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ?",
            (now, project_id),
        )
        await conn.commit()

        return GenerateSpeechResponse(
            audio_path=audio_path,
            scene_id=scene_id,
            engine=req.engine,
            voice_id=req.voice_id,
        )
    finally:
        await conn.close()
