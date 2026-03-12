"""Pipeline 编排引擎

管理视频生成的完整流程，采用状态机模式编排六个步骤的顺序执行。
支持启动、取消、恢复操作，以及步骤间的用户确认等待机制。

Requirements:
    8.4: Pipeline 的每个步骤完成后自动保存项目进度
    8.6: 用户取消正在执行的 Pipeline 时安全终止并保存中间结果
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

from app.database import get_connection

logger = logging.getLogger(__name__)


# ============================================================
# 枚举和数据类
# ============================================================

class PipelineStep(str, Enum):
    """Pipeline 六个步骤"""
    CHARACTER_EXTRACTION = "character_extraction"
    STORYBOARD_GENERATION = "storyboard_generation"
    KEYFRAME_GENERATION = "keyframe_generation"
    VIDEO_GENERATION = "video_generation"
    TTS_GENERATION = "tts_generation"
    COMPOSITION = "composition"


# 步骤顺序列表
STEP_ORDER: list[PipelineStep] = [
    PipelineStep.CHARACTER_EXTRACTION,
    PipelineStep.STORYBOARD_GENERATION,
    PipelineStep.KEYFRAME_GENERATION,
    PipelineStep.VIDEO_GENERATION,
    PipelineStep.TTS_GENERATION,
    PipelineStep.COMPOSITION,
]

# 需要用户确认才能继续的步骤（完成后暂停等待确认）
CONFIRMATION_STEPS: set[PipelineStep] = {
    PipelineStep.CHARACTER_EXTRACTION,
    PipelineStep.STORYBOARD_GENERATION,
}

# 步骤描述
STEP_DESCRIPTIONS: dict[PipelineStep, str] = {
    PipelineStep.CHARACTER_EXTRACTION: "角色提取",
    PipelineStep.STORYBOARD_GENERATION: "分镜脚本生成",
    PipelineStep.KEYFRAME_GENERATION: "关键帧图片生成",
    PipelineStep.VIDEO_GENERATION: "视频片段生成",
    PipelineStep.TTS_GENERATION: "语音配音生成",
    PipelineStep.COMPOSITION: "视频合成",
}

# 步骤预估时间（秒）
STEP_ESTIMATED_SECONDS: dict[PipelineStep, int] = {
    PipelineStep.CHARACTER_EXTRACTION: 30,
    PipelineStep.STORYBOARD_GENERATION: 60,
    PipelineStep.KEYFRAME_GENERATION: 120,
    PipelineStep.VIDEO_GENERATION: 300,
    PipelineStep.TTS_GENERATION: 60,
    PipelineStep.COMPOSITION: 30,
}


class StepStatus(str, Enum):
    """步骤状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_CONFIRMATION = "waiting_confirmation"


@dataclass
class PipelineStatus:
    """Pipeline 当前状态"""
    current_step: Optional[PipelineStep]
    progress: float  # 0.0 - 1.0
    step_detail: str  # 当前步骤的详细描述
    estimated_remaining: int  # 预计剩余秒数
    is_running: bool = False
    is_waiting_confirmation: bool = False
    error_message: Optional[str] = None


# ============================================================
# 异常类
# ============================================================

class PipelineError(Exception):
    """Pipeline 基础异常"""
    def __init__(self, message: str, code: str = "PIPELINE_ERROR"):
        super().__init__(message)
        self.code = code


class PipelineAlreadyRunningError(PipelineError):
    """Pipeline 已在运行"""
    def __init__(self, project_id: str):
        super().__init__(
            f"项目 {project_id} 的 Pipeline 已在运行中",
            code="PIPELINE_ALREADY_RUNNING",
        )


class PipelineCancelledError(PipelineError):
    """Pipeline 被取消"""
    def __init__(self):
        super().__init__("Pipeline 已被取消", code="PIPELINE_CANCELLED")


# Step executor type: async function taking project_id, returning None
StepExecutor = Callable[[str], Coroutine[Any, Any, None]]


# ============================================================
# Pipeline 状态持久化
# ============================================================

async def save_step_state(
    project_id: str,
    step: PipelineStep,
    status: str,
    progress: float = 0.0,
    error_message: Optional[str] = None,
) -> None:
    """保存步骤状态到数据库。

    如果该 project_id + step 的记录已存在则更新，否则插入新记录。
    """
    conn = await get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()

        # Check if record exists
        cursor = await conn.execute(
            "SELECT id FROM pipeline_states WHERE project_id = ? AND step = ?",
            (project_id, step.value),
        )
        row = await cursor.fetchone()

        if row:
            # Update existing
            update_fields = {
                "status": status,
                "progress": progress,
                "error_message": error_message,
            }
            if status == StepStatus.RUNNING.value:
                await conn.execute(
                    "UPDATE pipeline_states SET status=?, progress=?, error_message=?, started_at=? "
                    "WHERE project_id=? AND step=?",
                    (status, progress, error_message, now, project_id, step.value),
                )
            elif status in (StepStatus.COMPLETED.value, StepStatus.FAILED.value, StepStatus.CANCELLED.value):
                await conn.execute(
                    "UPDATE pipeline_states SET status=?, progress=?, error_message=?, completed_at=? "
                    "WHERE project_id=? AND step=?",
                    (status, progress, error_message, now, project_id, step.value),
                )
            else:
                await conn.execute(
                    "UPDATE pipeline_states SET status=?, progress=?, error_message=? "
                    "WHERE project_id=? AND step=?",
                    (status, progress, error_message, project_id, step.value),
                )
        else:
            # Insert new
            state_id = f"ps-{uuid.uuid4().hex[:8]}"
            started_at = now if status == StepStatus.RUNNING.value else None
            completed_at = now if status in (StepStatus.COMPLETED.value, StepStatus.FAILED.value, StepStatus.CANCELLED.value) else None
            await conn.execute(
                "INSERT INTO pipeline_states (id, project_id, step, status, progress, error_message, started_at, completed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (state_id, project_id, step.value, status, progress, error_message, started_at, completed_at),
            )

        await conn.commit()
    finally:
        await conn.close()


async def load_step_states(project_id: str) -> dict[str, dict]:
    """加载项目所有步骤的状态。

    Returns:
        dict mapping step name -> {status, progress, error_message, started_at, completed_at}
    """
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT step, status, progress, error_message, started_at, completed_at "
            "FROM pipeline_states WHERE project_id = ? ORDER BY started_at",
            (project_id,),
        )
        rows = await cursor.fetchall()
        result = {}
        for row in rows:
            result[row[0]] = {
                "status": row[1],
                "progress": row[2],
                "error_message": row[3],
                "started_at": row[4],
                "completed_at": row[5],
            }
        return result
    finally:
        await conn.close()


async def update_project_status(project_id: str, status: str, current_step: Optional[str] = None) -> None:
    """更新项目表的 status 和 current_step 字段。"""
    conn = await get_connection()
    try:
        now = datetime.now(timezone.utc).isoformat()
        await conn.execute(
            "UPDATE projects SET status=?, current_step=?, updated_at=? WHERE id=?",
            (status, current_step, now, project_id),
        )
        await conn.commit()
    finally:
        await conn.close()


# ============================================================
# PipelineEngine
# ============================================================

class PipelineEngine:
    """Pipeline 状态机，管理视频生成的完整流程。

    支持：
    - start: 从头开始执行 Pipeline
    - cancel: 取消正在运行的 Pipeline，安全终止并保存中间结果
    - resume: 从指定步骤恢复执行
    - get_status: 获取当前 Pipeline 状态
    """

    def __init__(self) -> None:
        # 每个项目的运行状态
        self._running: dict[str, bool] = {}
        # 取消标志
        self._cancel_flags: dict[str, bool] = {}
        # 等待确认标志
        self._waiting_confirmation: dict[str, bool] = {}
        # 当前步骤
        self._current_steps: dict[str, Optional[PipelineStep]] = {}
        # 当前进度
        self._progress: dict[str, float] = {}
        # 运行中的 asyncio Task
        self._tasks: dict[str, asyncio.Task] = {}
        # 步骤执行器（可注入，便于测试）
        self._step_executors: dict[PipelineStep, StepExecutor] = {}
        # 事件回调（用于 SSE 推送等）
        self._event_callbacks: dict[str, list[Callable]] = {}

    def register_step_executor(self, step: PipelineStep, executor: StepExecutor) -> None:
        """注册步骤执行器。"""
        self._step_executors[step] = executor

    def register_event_callback(self, project_id: str, callback: Callable) -> None:
        """注册事件回调（用于 SSE 推送）。"""
        if project_id not in self._event_callbacks:
            self._event_callbacks[project_id] = []
        self._event_callbacks[project_id].append(callback)

    def unregister_event_callback(self, project_id: str, callback: Callable) -> None:
        """注销事件回调。"""
        if project_id in self._event_callbacks:
            self._event_callbacks[project_id] = [
                cb for cb in self._event_callbacks[project_id] if cb is not callback
            ]

    async def _emit_event(self, project_id: str, event: dict) -> None:
        """发送事件到所有注册的回调。"""
        callbacks = self._event_callbacks.get(project_id, [])
        for cb in callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(event)
                else:
                    cb(event)
            except Exception as e:
                logger.warning("事件回调执行失败: %s", e)

    def _is_cancelled(self, project_id: str) -> bool:
        """检查是否已被取消。"""
        return self._cancel_flags.get(project_id, False)

    async def start(self, project_id: str) -> None:
        """启动 Pipeline，从第一个步骤开始。

        Pipeline 在后台异步执行。此方法启动执行任务后立即返回。

        Args:
            project_id: 项目 ID

        Raises:
            PipelineAlreadyRunningError: Pipeline 已在运行
        """
        if self._running.get(project_id, False):
            raise PipelineAlreadyRunningError(project_id)

        self._running[project_id] = True
        self._cancel_flags[project_id] = False
        self._waiting_confirmation[project_id] = False
        self._current_steps[project_id] = STEP_ORDER[0]
        self._progress[project_id] = 0.0

        await update_project_status(project_id, "processing", STEP_ORDER[0].value)

        # Initialize all step states as pending
        for step in STEP_ORDER:
            await save_step_state(project_id, step, StepStatus.PENDING.value)

        # Start execution in background
        task = asyncio.create_task(self._run_pipeline(project_id, STEP_ORDER[0]))
        self._tasks[project_id] = task

    async def cancel(self, project_id: str) -> None:
        """取消正在运行的 Pipeline。

        设置取消标志，Pipeline 会在当前步骤完成或下一个检查点安全终止。
        已完成的步骤结果会被保存。

        Args:
            project_id: 项目 ID
        """
        self._cancel_flags[project_id] = True

        # If waiting for confirmation, also release the wait
        self._waiting_confirmation[project_id] = False

        # Cancel the running task if exists
        task = self._tasks.get(project_id)
        if task and not task.done():
            # Don't force cancel - let the pipeline check the flag and exit gracefully
            pass

        # Determine which steps to mark as cancelled
        current_step = self._current_steps.get(project_id)
        if current_step:
            step_idx = STEP_ORDER.index(current_step)

            # Check if current step is already completed (e.g., waiting for confirmation)
            states = await load_step_states(project_id)
            current_state = states.get(current_step.value, {}).get("status")

            if current_state != StepStatus.COMPLETED.value:
                # Current step was still running — mark it cancelled
                await save_step_state(
                    project_id, current_step, StepStatus.CANCELLED.value
                )
                remaining_start = step_idx + 1
            else:
                # Current step already completed — don't overwrite it
                remaining_start = step_idx + 1

            # Mark remaining steps as cancelled
            for step in STEP_ORDER[remaining_start:]:
                step_state = states.get(step.value, {}).get("status")
                if step_state != StepStatus.COMPLETED.value:
                    await save_step_state(project_id, step, StepStatus.CANCELLED.value)

        await update_project_status(project_id, "paused", current_step.value if current_step else None)

        self._running[project_id] = False

        await self._emit_event(project_id, {
            "type": "pipeline_cancelled",
            "project_id": project_id,
            "step": current_step.value if current_step else None,
        })

        logger.info("Pipeline 已取消: project_id=%s", project_id)

    async def resume(self, project_id: str, from_step: PipelineStep) -> None:
        """从指定步骤恢复 Pipeline 执行。

        Args:
            project_id: 项目 ID
            from_step: 从哪个步骤开始恢复

        Raises:
            PipelineAlreadyRunningError: Pipeline 已在运行
            ValueError: 无效的步骤
        """
        if self._running.get(project_id, False):
            raise PipelineAlreadyRunningError(project_id)

        if from_step not in STEP_ORDER:
            raise ValueError(f"无效的 Pipeline 步骤: {from_step}")

        self._running[project_id] = True
        self._cancel_flags[project_id] = False
        self._waiting_confirmation[project_id] = False
        self._current_steps[project_id] = from_step
        self._progress[project_id] = STEP_ORDER.index(from_step) / len(STEP_ORDER)

        await update_project_status(project_id, "processing", from_step.value)

        # Reset states for steps from from_step onwards
        step_idx = STEP_ORDER.index(from_step)
        for step in STEP_ORDER[step_idx:]:
            await save_step_state(project_id, step, StepStatus.PENDING.value)

        task = asyncio.create_task(self._run_pipeline(project_id, from_step))
        self._tasks[project_id] = task

    def get_status(self, project_id: str) -> PipelineStatus:
        """获取当前 Pipeline 状态。

        Args:
            project_id: 项目 ID

        Returns:
            PipelineStatus 对象
        """
        current_step = self._current_steps.get(project_id)
        is_running = self._running.get(project_id, False)
        is_waiting = self._waiting_confirmation.get(project_id, False)
        progress = self._progress.get(project_id, 0.0)

        if current_step is None:
            return PipelineStatus(
                current_step=None,
                progress=0.0,
                step_detail="Pipeline 未启动",
                estimated_remaining=0,
                is_running=False,
            )

        step_desc = STEP_DESCRIPTIONS.get(current_step, current_step.value)

        if is_waiting:
            detail = f"{step_desc} - 等待用户确认"
        elif is_running:
            detail = f"正在执行: {step_desc}"
        else:
            detail = f"{step_desc}"

        # Calculate estimated remaining time
        step_idx = STEP_ORDER.index(current_step)
        remaining = sum(
            STEP_ESTIMATED_SECONDS.get(s, 30)
            for s in STEP_ORDER[step_idx:]
        )

        return PipelineStatus(
            current_step=current_step,
            progress=progress,
            step_detail=detail,
            estimated_remaining=remaining,
            is_running=is_running,
            is_waiting_confirmation=is_waiting,
        )

    async def confirm_step(self, project_id: str) -> None:
        """用户确认当前步骤，继续执行下一步。

        当 Pipeline 在等待用户确认时调用此方法。
        """
        self._waiting_confirmation[project_id] = False

    async def _run_pipeline(self, project_id: str, from_step: PipelineStep) -> None:
        """执行 Pipeline 的核心循环。

        从 from_step 开始，顺序执行每个步骤。
        每步完成后自动保存状态（Req 8.4）。
        取消时安全终止并保存中间结果（Req 8.6）。
        """
        start_idx = STEP_ORDER.index(from_step)

        try:
            for i, step in enumerate(STEP_ORDER[start_idx:], start=start_idx):
                # Check cancellation before each step
                if self._is_cancelled(project_id):
                    logger.info("Pipeline 在步骤 %s 前被取消", step.value)
                    raise PipelineCancelledError()

                self._current_steps[project_id] = step
                self._progress[project_id] = i / len(STEP_ORDER)

                # Mark step as running
                await save_step_state(project_id, step, StepStatus.RUNNING.value)
                await update_project_status(project_id, "processing", step.value)

                await self._emit_event(project_id, {
                    "type": "step_started",
                    "project_id": project_id,
                    "step": step.value,
                    "step_description": STEP_DESCRIPTIONS.get(step, step.value),
                    "progress": self._progress[project_id],
                })

                # Execute the step
                try:
                    await self._execute_step(project_id, step)
                except PipelineCancelledError:
                    raise
                except Exception as e:
                    # Step failed - save error state and stop
                    error_msg = str(e)
                    logger.error("Pipeline 步骤 %s 执行失败: %s", step.value, error_msg)
                    await save_step_state(
                        project_id, step, StepStatus.FAILED.value,
                        error_message=error_msg,
                    )
                    await update_project_status(project_id, "error", step.value)
                    await self._emit_event(project_id, {
                        "type": "step_failed",
                        "project_id": project_id,
                        "step": step.value,
                        "error": error_msg,
                    })
                    self._running[project_id] = False
                    return

                # Check cancellation after step execution
                if self._is_cancelled(project_id):
                    # Step completed but pipeline cancelled - save the completed step
                    await save_step_state(
                        project_id, step, StepStatus.COMPLETED.value, progress=1.0,
                    )
                    logger.info("Pipeline 在步骤 %s 完成后被取消", step.value)
                    raise PipelineCancelledError()

                # Step completed - auto-save (Req 8.4)
                await save_step_state(
                    project_id, step, StepStatus.COMPLETED.value, progress=1.0,
                )

                await self._emit_event(project_id, {
                    "type": "step_completed",
                    "project_id": project_id,
                    "step": step.value,
                    "progress": (i + 1) / len(STEP_ORDER),
                })

                logger.info("Pipeline 步骤完成: %s (project=%s)", step.value, project_id)

                # Wait for user confirmation if needed
                if step in CONFIRMATION_STEPS:
                    self._waiting_confirmation[project_id] = True
                    await update_project_status(project_id, "paused", step.value)

                    await self._emit_event(project_id, {
                        "type": "waiting_confirmation",
                        "project_id": project_id,
                        "step": step.value,
                    })

                    # Wait until confirmation or cancellation
                    while self._waiting_confirmation.get(project_id, False):
                        if self._is_cancelled(project_id):
                            raise PipelineCancelledError()
                        await asyncio.sleep(0.1)

                    await update_project_status(project_id, "processing", step.value)

            # All steps completed
            self._progress[project_id] = 1.0
            await update_project_status(project_id, "completed", None)
            self._running[project_id] = False

            await self._emit_event(project_id, {
                "type": "pipeline_completed",
                "project_id": project_id,
                "progress": 1.0,
            })

            logger.info("Pipeline 全部完成: project_id=%s", project_id)

        except PipelineCancelledError:
            # Already handled in cancel() - just clean up
            self._running[project_id] = False
            logger.info("Pipeline 执行被取消: project_id=%s", project_id)

        except Exception as e:
            logger.error("Pipeline 执行异常: %s", e)
            self._running[project_id] = False
            await update_project_status(project_id, "error", None)

    async def _execute_step(self, project_id: str, step: PipelineStep) -> None:
        """执行单个步骤。

        如果有注册的执行器则调用，否则使用默认的空操作（便于测试）。
        """
        executor = self._step_executors.get(step)
        if executor:
            await executor(project_id)
        else:
            # Default no-op for steps without registered executors
            logger.info("步骤 %s 没有注册执行器，跳过实际执行", step.value)
