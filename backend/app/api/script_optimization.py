"""剧本迭代优化 API 路由

提供剧本优化流程的 REST API 和 WebSocket 端点。

- POST /api/script-optimization/start — 启动优化流程
- GET  /api/script-optimization/{session_id}/status — 查询会话状态
- GET  /api/script-optimization/{session_id}/versions — 获取版本历史
- GET  /api/script-optimization/{session_id}/versions/{iteration} — 获取特定版本
- WS   /ws/script-optimization/{session_id} — 实时进度推送

需求：1.1, 6.2, 6.3
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, field_validator

from app.config.optimization_config import IterationConfig
from app.database import get_connection
from app.schemas.script_optimization import (
    DimensionWeights,
    IterationProgress,
    OptimizationSessionResponse,
    ScriptVersion,
)
from app.services.iteration_engine import IterationEngine, OptimizationResult
from app.services.script_evaluator_v2 import ScriptEvaluator
from app.services.script_generator import ScriptGenerator
from app.services.hotspot_searcher import HotspotSearcher
from app.services.technique_searcher import TechniqueSearcher
from app.services.search_api_client import SearchAPIClient, RetryConfig
from app.services.version_manager import VersionManager
from app.services.websocket_manager import WebSocketManager
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/script-optimization", tags=["script-optimization"])

# Shared WebSocket manager instance
ws_manager = WebSocketManager()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class StartOptimizationRequest(BaseModel):
    """启动优化请求"""
    initial_prompt: str = Field(..., min_length=1, description="初始剧本提示词")
    target_score: float = Field(default=8.0, ge=0, le=10, description="目标分数")
    max_iterations: int = Field(default=20, gt=0, le=100, description="最大迭代次数")

    @field_validator("initial_prompt")
    @classmethod
    def validate_prompt_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("初始提示词不能为空白")
        return v.strip()


class StartOptimizationResponse(BaseModel):
    """启动优化响应"""
    session_id: str
    status: str
    message: str


class SessionStatusResponse(BaseModel):
    """会话状态响应"""
    id: str
    initial_prompt: str
    target_score: float
    max_iterations: int
    status: str
    created_at: str
    completed_at: Optional[str] = None


class VersionListResponse(BaseModel):
    """版本列表响应"""
    session_id: str
    versions: List[ScriptVersion]
    total: int


# ---------------------------------------------------------------------------
# Helper: build services from a db connection
# ---------------------------------------------------------------------------

async def _build_services(db):
    """Construct the service graph needed by the iteration engine."""
    llm_service = LLMService()
    search_client = SearchAPIClient(
        api_key="",
        api_endpoint="https://api.example.com",
        retry_config=RetryConfig(max_retries=3),
    )
    hotspot_searcher = HotspotSearcher(search_api_client=search_client)
    technique_searcher = TechniqueSearcher(search_api_client=search_client)
    weights = DimensionWeights()
    script_evaluator = ScriptEvaluator(llm_service=llm_service, weights=weights)
    script_generator = ScriptGenerator(llm_service=llm_service)
    version_manager = VersionManager(db=db)
    return script_generator, script_evaluator, hotspot_searcher, technique_searcher, version_manager


# ---------------------------------------------------------------------------
# POST /api/script-optimization/start
# ---------------------------------------------------------------------------

@router.post("/start", response_model=StartOptimizationResponse)
async def start_optimization(req: StartOptimizationRequest):
    """启动剧本优化流程（需求 1.1）。

    创建优化会话并在后台启动迭代引擎。
    """
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    db = await get_connection()
    try:
        # Persist session record
        await db.execute(
            """
            INSERT INTO optimization_sessions
                (id, initial_prompt, target_score, max_iterations, status, created_at)
            VALUES (?, ?, ?, ?, 'running', ?)
            """,
            (session_id, req.initial_prompt, req.target_score, req.max_iterations, now),
        )
        await db.commit()
    except Exception as e:
        await db.close()
        logger.error("Failed to create optimization session: %s", e)
        raise HTTPException(status_code=500, detail="创建优化会话失败")

    # Launch the optimization in the background
    asyncio.create_task(
        _run_optimization(session_id, req.initial_prompt, req.target_score, req.max_iterations)
    )

    return StartOptimizationResponse(
        session_id=session_id,
        status="running",
        message="优化流程已启动",
    )


async def _run_optimization(
    session_id: str,
    initial_prompt: str,
    target_score: float,
    max_iterations: int,
):
    """Background task that runs the full optimization loop."""
    db = await get_connection()
    try:
        (
            script_generator,
            script_evaluator,
            hotspot_searcher,
            technique_searcher,
            version_manager,
        ) = await _build_services(db)

        config = IterationConfig(
            target_score=target_score,
            max_iterations=max_iterations,
        )
        engine = IterationEngine(
            script_generator=script_generator,
            script_evaluator=script_evaluator,
            hotspot_searcher=hotspot_searcher,
            technique_searcher=technique_searcher,
            version_manager=version_manager,
            config=config,
        )

        async def progress_callback(progress: IterationProgress):
            await ws_manager.send_progress(session_id, progress)

        await engine.optimize_script(
            initial_prompt=initial_prompt,
            session_id=session_id,
            progress_callback=progress_callback,
        )

        # Mark session completed
        completed_at = datetime.now(timezone.utc).isoformat()
        await db.execute(
            "UPDATE optimization_sessions SET status = 'completed', completed_at = ? WHERE id = ?",
            (completed_at, session_id),
        )
        await db.commit()
        logger.info("Optimization session %s completed", session_id)

    except Exception as e:
        logger.error("Optimization session %s failed: %s", session_id, e, exc_info=True)
        try:
            await db.execute(
                "UPDATE optimization_sessions SET status = 'failed' WHERE id = ?",
                (session_id,),
            )
            await db.commit()
        except Exception:
            logger.error("Failed to update session status to 'failed'")
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# GET /api/script-optimization/{session_id}/status
# ---------------------------------------------------------------------------

@router.get("/{session_id}/status", response_model=SessionStatusResponse)
async def get_session_status(session_id: str):
    """查询优化会话状态。"""
    db = await get_connection()
    try:
        cursor = await db.execute(
            "SELECT * FROM optimization_sessions WHERE id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="会话不存在")
        return SessionStatusResponse(
            id=row["id"],
            initial_prompt=row["initial_prompt"],
            target_score=row["target_score"],
            max_iterations=row["max_iterations"],
            status=row["status"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# GET /api/script-optimization/{session_id}/versions
# ---------------------------------------------------------------------------

@router.get("/{session_id}/versions", response_model=VersionListResponse)
async def get_versions(session_id: str):
    """获取会话的所有版本历史（需求 6.2）。"""
    db = await get_connection()
    try:
        # Verify session exists
        cursor = await db.execute(
            "SELECT id FROM optimization_sessions WHERE id = ?",
            (session_id,),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="会话不存在")

        version_manager = VersionManager(db=db)
        versions = await version_manager.get_versions(session_id)
        return VersionListResponse(
            session_id=session_id,
            versions=versions,
            total=len(versions),
        )
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# GET /api/script-optimization/{session_id}/versions/{iteration}
# ---------------------------------------------------------------------------

@router.get("/{session_id}/versions/{iteration}")
async def get_version(session_id: str, iteration: int):
    """获取特定迭代版本（需求 6.3）。"""
    if iteration < 0:
        raise HTTPException(status_code=422, detail="迭代次数不能为负数")

    db = await get_connection()
    try:
        # Verify session exists
        cursor = await db.execute(
            "SELECT id FROM optimization_sessions WHERE id = ?",
            (session_id,),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="会话不存在")

        version_manager = VersionManager(db=db)
        version = await version_manager.get_version(session_id, iteration)
        if version is None:
            raise HTTPException(status_code=404, detail="版本不存在")
        return version
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# WebSocket /ws/script-optimization/{session_id}
# ---------------------------------------------------------------------------

@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket 端点，实时推送优化进度（需求 10.4）。"""
    await ws_manager.connect(session_id, websocket)
    try:
        # Keep connection alive until client disconnects
        while True:
            # Wait for any client message (ping/pong or close)
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected: session_id=%s", session_id)
    except Exception as e:
        logger.error("WebSocket error for session %s: %s", session_id, e)
    finally:
        await ws_manager.disconnect(session_id)
