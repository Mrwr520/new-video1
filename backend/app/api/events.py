"""SSE 事件流和 Pipeline 控制 API

实现 GET /api/projects/{id}/events SSE 端点，
以及 Pipeline 启动、取消、状态查询等控制端点。

Requirements:
    8.5: Pipeline 执行中显示当前步骤的进度条和预计剩余时间
"""

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.database import get_connection
from app.database import get_connection
from app.pipeline import (
    PipelineEngine,
    PipelineAlreadyRunningError,
    PipelineStep,
    STEP_ORDER,
    load_step_states,
)
from app.pipeline.executors import (
    execute_character_extraction,
    execute_storyboard_generation,
    execute_keyframe_generation,
    execute_video_generation,
    execute_tts_generation,
    execute_composition,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["pipeline"])

# Global PipelineEngine instance
_engine: PipelineEngine | None = None


def _register_executors(engine: PipelineEngine) -> None:
    """Register all step executors with the pipeline engine."""
    engine.register_step_executor(PipelineStep.CHARACTER_EXTRACTION, execute_character_extraction)
    engine.register_step_executor(PipelineStep.STORYBOARD_GENERATION, execute_storyboard_generation)
    engine.register_step_executor(PipelineStep.KEYFRAME_GENERATION, execute_keyframe_generation)
    engine.register_step_executor(PipelineStep.VIDEO_GENERATION, execute_video_generation)
    engine.register_step_executor(PipelineStep.TTS_GENERATION, execute_tts_generation)
    engine.register_step_executor(PipelineStep.COMPOSITION, execute_composition)


def get_engine() -> PipelineEngine:
    """Get or create the global PipelineEngine instance."""
    global _engine
    if _engine is None:
        _engine = PipelineEngine()
        _register_executors(_engine)
    return _engine


def set_engine(engine: PipelineEngine) -> None:
    """Set the global PipelineEngine instance (for testing)."""
    global _engine
    _engine = engine


async def _check_project_exists(project_id: str) -> None:
    """Check that a project exists, raise 404 if not."""
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="项目不存在")
    finally:
        await conn.close()


def _format_sse(event_type: str, data: dict) -> str:
    """Format a dict as an SSE message string."""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _event_stream(project_id: str) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE events for a project's pipeline.

    Registers a callback with the PipelineEngine to receive events,
    sends them as SSE, and sends periodic heartbeats.
    """
    engine = get_engine()
    queue: asyncio.Queue[dict] = asyncio.Queue()

    async def on_event(event: dict) -> None:
        await queue.put(event)

    engine.register_event_callback(project_id, on_event)

    try:
        # Send initial connection event
        yield _format_sse("connected", {"project_id": project_id})

        # Send current pipeline status
        status = engine.get_status(project_id)
        yield _format_sse("status", {
            "project_id": project_id,
            "current_step": status.current_step.value if status.current_step else None,
            "progress": status.progress,
            "step_detail": status.step_detail,
            "estimated_remaining": status.estimated_remaining,
            "is_running": status.is_running,
            "is_waiting_confirmation": status.is_waiting_confirmation,
        })

        while True:
            try:
                # Wait for events with a timeout for heartbeat
                event = await asyncio.wait_for(queue.get(), timeout=15.0)
                event_type = event.get("type", "unknown")
                yield _format_sse(event_type, event)

                # If pipeline completed or cancelled, send final event and stop
                if event_type in ("pipeline_completed", "pipeline_cancelled"):
                    break

            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                yield _format_sse("heartbeat", {"project_id": project_id})

    except asyncio.CancelledError:
        logger.info("SSE stream cancelled for project %s", project_id)
    finally:
        engine.unregister_event_callback(project_id, on_event)


@router.get("/{project_id}/events")
async def pipeline_events(project_id: str):
    """SSE 事件流端点 - 推送 Pipeline 进度更新。

    Returns a streaming response with text/event-stream content type.
    Events include: step_started, step_completed, step_failed,
    waiting_confirmation, pipeline_completed, pipeline_cancelled, heartbeat.
    """
    await _check_project_exists(project_id)

    return StreamingResponse(
        _event_stream(project_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{project_id}/start")
async def start_pipeline(project_id: str):
    """启动 Pipeline，从第一个步骤开始执行。"""
    await _check_project_exists(project_id)
    engine = get_engine()

    try:
        await engine.start(project_id)
    except PipelineAlreadyRunningError:
        raise HTTPException(status_code=409, detail="Pipeline 已在运行中")

    return {"message": "Pipeline 已启动", "project_id": project_id}


@router.post("/{project_id}/cancel")
async def cancel_pipeline(project_id: str):
    """取消正在运行的 Pipeline。"""
    await _check_project_exists(project_id)
    engine = get_engine()

    await engine.cancel(project_id)
    return {"message": "Pipeline 已取消", "project_id": project_id}


@router.get("/{project_id}/pipeline-status")
async def get_pipeline_status(project_id: str):
    """获取当前 Pipeline 状态。

    如果 engine 内存中没有状态（重启后），从数据库恢复。
    """
    await _check_project_exists(project_id)
    engine = get_engine()

    status = engine.get_status(project_id)
    step_states = await load_step_states(project_id)

    # 如果 engine 内存中没有状态，从数据库恢复
    if status.current_step is None and step_states:
        # 旧版确认值到对应 PipelineStep 值的映射
        CONFIRMED_STEP_MAP = {
            "characters_confirmed": "character_extraction",
            "storyboard_confirmed": "storyboard_generation",
        }

        conn = await get_connection()
        try:
            cursor = await conn.execute(
                "SELECT status, current_step FROM projects WHERE id = ?", (project_id,)
            )
            row = await cursor.fetchone()
            if row and row[1]:
                db_status = row[0]
                db_step = row[1]

                # 兼容旧版 'characters_confirmed' / 'storyboard_confirmed' 值
                is_confirmed_legacy = db_step in CONFIRMED_STEP_MAP
                if is_confirmed_legacy:
                    db_step = CONFIRMED_STEP_MAP[db_step]

                # 计算进度
                step_keys = [s.value for s in STEP_ORDER]
                if db_step in step_keys:
                    step_idx = step_keys.index(db_step)
                    is_waiting = (
                        (db_status == "paused" or is_confirmed_legacy)
                        and db_step in ("character_extraction", "storyboard_generation")
                    )
                    # 等待确认说明该步骤执行已完成，进度应算到 (step_idx+1)
                    # 正常运行中的步骤进度算到 step_idx（即该步骤刚开始）
                    if is_waiting:
                        progress = (step_idx + 1) / len(STEP_ORDER)
                    else:
                        progress = step_idx / len(STEP_ORDER)
                    step_desc_map = {
                        "character_extraction": "角色提取",
                        "storyboard_generation": "分镜脚本生成",
                        "keyframe_generation": "关键帧图片生成",
                        "video_generation": "视频片段生成",
                        "tts_generation": "语音配音生成",
                        "composition": "视频合成",
                    }
                    step_desc = step_desc_map.get(db_step, db_step)
                    detail = f"{step_desc} - 等待用户确认" if is_waiting else step_desc

                    return {
                        "current_step": db_step,
                        "progress": progress,
                        "step_detail": detail,
                        "estimated_remaining": 0,
                        "is_running": False,
                        "is_waiting_confirmation": is_waiting,
                        "error_message": None,
                        "steps": step_states,
                    }
        finally:
            await conn.close()

    return {
        "current_step": status.current_step.value if status.current_step else None,
        "progress": status.progress,
        "step_detail": status.step_detail,
        "estimated_remaining": status.estimated_remaining,
        "is_running": status.is_running,
        "is_waiting_confirmation": status.is_waiting_confirmation,
        "error_message": status.error_message,
        "steps": step_states,
    }
