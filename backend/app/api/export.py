"""导出和文件服务 API 路由

实现视频导出和项目资源文件服务端点。

Requirements:
    7.4: 合成完成后提供完整视频的预览播放功能
    7.5: 输出 MP4 格式的视频文件，分辨率不低于 1080p
    7.7: 合成失败时显示错误详情并提供重试选项
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.database import get_connection, get_db_path
from app.services.ffmpeg_service import (
    CompositionScene,
    FFmpegCompositor,
    FFmpegError,
    FFmpegNotFoundError,
    FFmpegCompositionError,
    OutputConfig,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["export"])


def _get_projects_root() -> Path:
    """获取项目文件存储根目录"""
    return get_db_path().parent / "projects"


class ExportRequest(BaseModel):
    """导出请求参数"""
    resolution_width: int = 1920
    resolution_height: int = 1080
    fps: int = 30
    codec: str = "h264"
    bitrate: str = "8M"


class ExportResponse(BaseModel):
    """导出响应"""
    video_path: str
    message: str


class ExportErrorResponse(BaseModel):
    """导出错误响应"""
    code: str
    message: str
    detail: Optional[str] = None
    retryable: bool


@router.post("/{project_id}/export", response_model=ExportResponse)
async def export_video(project_id: str, req: ExportRequest = ExportRequest()):
    """导出项目的最终合成视频。

    将项目中所有分镜的视频片段、音频和字幕合成为一个完整的 MP4 视频文件。

    Requirements:
        7.5: 输出 MP4 格式的视频文件，分辨率不低于 1080p
        7.7: 合成失败时返回错误详情
    """
    conn = await get_connection()
    try:
        # 验证项目存在
        cursor = await conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="项目不存在")

        # 获取所有分镜（按顺序）
        cursor = await conn.execute(
            "SELECT * FROM scenes WHERE project_id = ? ORDER BY scene_order",
            (project_id,),
        )
        rows = await cursor.fetchall()

        if not rows:
            raise HTTPException(status_code=400, detail="项目没有分镜，无法导出")

        # 检查是否有视频片段
        scenes_with_video = [r for r in rows if r["video_path"]]
        if not scenes_with_video:
            raise HTTPException(status_code=400, detail="没有已生成的视频片段，请先生成视频")

        # 构建 CompositionScene 列表
        composition_scenes: list[CompositionScene] = []
        cumulative_time = 0.0
        for row in scenes_with_video:
            duration = row["duration"] if row["duration"] else 5.0
            scene = CompositionScene(
                video_path=row["video_path"],
                audio_path=row["audio_path"],
                subtitle_text=row["dialogue"],
                start_time=cumulative_time,
                duration=duration,
            )
            composition_scenes.append(scene)
            cumulative_time += duration

        # 构建输出配置
        output_config = OutputConfig(
            resolution=(req.resolution_width, req.resolution_height),
            fps=req.fps,
            codec=req.codec,
            bitrate=req.bitrate,
        )

        # 调用 FFmpeg 合成
        projects_root = _get_projects_root()
        compositor = FFmpegCompositor(projects_dir=projects_root)

        try:
            video_path = await compositor.compose_final_video(
                project_id=project_id,
                scenes=composition_scenes,
                output_config=output_config,
            )
        except FFmpegNotFoundError as e:
            raise HTTPException(
                status_code=502,
                detail={
                    "code": e.code,
                    "message": str(e),
                    "retryable": False,
                },
            )
        except FFmpegCompositionError as e:
            raise HTTPException(
                status_code=502,
                detail={
                    "code": e.code,
                    "message": str(e),
                    "detail": e.detail,
                    "retryable": True,
                },
            )
        except FFmpegError as e:
            raise HTTPException(
                status_code=502,
                detail={
                    "code": e.code,
                    "message": str(e),
                    "retryable": e.retryable,
                },
            )

        # 更新项目状态
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        await conn.execute(
            "UPDATE projects SET status = 'completed', current_step = 'exported', updated_at = ? WHERE id = ?",
            (now, project_id),
        )
        await conn.commit()

        return ExportResponse(
            video_path=video_path,
            message="视频导出成功",
        )

    finally:
        await conn.close()


@router.get("/{project_id}/files/{file_path:path}")
async def get_project_file(project_id: str, file_path: str):
    """获取项目资源文件（视频、图片、音频等）。

    Requirements:
        7.4: 提供完整视频的预览播放功能
    """
    conn = await get_connection()
    try:
        cursor = await conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="项目不存在")
    finally:
        await conn.close()

    projects_root = _get_projects_root()
    full_path = projects_root / project_id / file_path

    # 安全检查：防止路径遍历
    try:
        full_path = full_path.resolve()
        allowed_root = (projects_root / project_id).resolve()
        if not str(full_path).startswith(str(allowed_root)):
            raise HTTPException(status_code=403, detail="禁止访问该路径")
    except (ValueError, OSError):
        raise HTTPException(status_code=400, detail="无效的文件路径")

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    # 根据扩展名确定 media type
    media_types = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".avi": "video/x-msvideo",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".srt": "text/plain",
    }
    suffix = full_path.suffix.lower()
    media_type = media_types.get(suffix, "application/octet-stream")

    return FileResponse(
        path=str(full_path),
        media_type=media_type,
        filename=full_path.name,
    )
