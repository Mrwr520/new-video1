"""Pipeline 引擎单元测试

测试 PipelineEngine 的核心功能：
- start/cancel/resume 操作
- 六个步骤的顺序执行
- 步骤间的等待用户确认机制
- 每步完成后的自动保存
- 取消时的安全终止和中间结果保存
"""

import asyncio
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app.database import get_connection, init_db, set_db_path
from app.pipeline import (
    CONFIRMATION_STEPS,
    STEP_ORDER,
    PipelineAlreadyRunningError,
    PipelineCancelledError,
    PipelineEngine,
    PipelineError,
    PipelineStatus,
    PipelineStep,
    StepStatus,
    load_step_states,
    save_step_state,
    update_project_status,
)


# ============================================================
# Fixtures
# ============================================================

@pytest_asyncio.fixture
async def db(tmp_path):
    """为每个测试创建临时数据库"""
    db_path = tmp_path / "test_pipeline.db"
    set_db_path(db_path)
    await init_db()
    yield db_path


@pytest_asyncio.fixture
async def project_id(db):
    """创建一个测试项目并返回其 ID"""
    conn = await get_connection()
    try:
        pid = "test-project-001"
        await conn.execute(
            "INSERT INTO projects (id, name, template_id, status) VALUES (?, ?, ?, ?)",
            (pid, "Test Project", "builtin-anime", "created"),
        )
        await conn.commit()
        return pid
    finally:
        await conn.close()


@pytest.fixture
def engine():
    """创建 PipelineEngine 实例"""
    return PipelineEngine()


# ============================================================
# Helper: register no-op executors for all steps
# ============================================================

def register_noop_executors(engine: PipelineEngine) -> dict[PipelineStep, AsyncMock]:
    """Register async no-op executors for all steps, return the mocks."""
    mocks = {}
    for step in STEP_ORDER:
        mock = AsyncMock()
        engine.register_step_executor(step, mock)
        mocks[step] = mock
    return mocks


def register_fast_executors(engine: PipelineEngine) -> dict[PipelineStep, AsyncMock]:
    """Register fast executors that complete immediately."""
    mocks = {}
    for step in STEP_ORDER:
        mock = AsyncMock(return_value=None)
        engine.register_step_executor(step, mock)
        mocks[step] = mock
    return mocks


# ============================================================
# Tests: PipelineStep enum
# ============================================================

class TestPipelineStep:
    def test_step_values(self):
        assert PipelineStep.CHARACTER_EXTRACTION == "character_extraction"
        assert PipelineStep.STORYBOARD_GENERATION == "storyboard_generation"
        assert PipelineStep.KEYFRAME_GENERATION == "keyframe_generation"
        assert PipelineStep.VIDEO_GENERATION == "video_generation"
        assert PipelineStep.TTS_GENERATION == "tts_generation"
        assert PipelineStep.COMPOSITION == "composition"

    def test_step_order_has_six_steps(self):
        assert len(STEP_ORDER) == 6

    def test_step_order_sequence(self):
        assert STEP_ORDER[0] == PipelineStep.CHARACTER_EXTRACTION
        assert STEP_ORDER[1] == PipelineStep.STORYBOARD_GENERATION
        assert STEP_ORDER[2] == PipelineStep.KEYFRAME_GENERATION
        assert STEP_ORDER[3] == PipelineStep.VIDEO_GENERATION
        assert STEP_ORDER[4] == PipelineStep.TTS_GENERATION
        assert STEP_ORDER[5] == PipelineStep.COMPOSITION

    def test_confirmation_steps(self):
        assert PipelineStep.CHARACTER_EXTRACTION in CONFIRMATION_STEPS
        assert PipelineStep.STORYBOARD_GENERATION in CONFIRMATION_STEPS
        assert PipelineStep.KEYFRAME_GENERATION not in CONFIRMATION_STEPS


# ============================================================
# Tests: PipelineStatus
# ============================================================

class TestPipelineStatus:
    def test_default_status(self):
        status = PipelineStatus(
            current_step=None,
            progress=0.0,
            step_detail="未启动",
            estimated_remaining=0,
        )
        assert status.current_step is None
        assert status.progress == 0.0
        assert not status.is_running
        assert not status.is_waiting_confirmation

    def test_running_status(self):
        status = PipelineStatus(
            current_step=PipelineStep.KEYFRAME_GENERATION,
            progress=0.5,
            step_detail="正在生成关键帧",
            estimated_remaining=120,
            is_running=True,
        )
        assert status.current_step == PipelineStep.KEYFRAME_GENERATION
        assert status.is_running
        assert status.estimated_remaining == 120


# ============================================================
# Tests: State persistence
# ============================================================

class TestStatePersistence:
    @pytest.mark.asyncio
    async def test_save_and_load_step_state(self, project_id):
        await save_step_state(
            project_id, PipelineStep.CHARACTER_EXTRACTION,
            StepStatus.COMPLETED.value, progress=1.0,
        )
        states = await load_step_states(project_id)
        assert "character_extraction" in states
        assert states["character_extraction"]["status"] == "completed"
        assert states["character_extraction"]["progress"] == 1.0

    @pytest.mark.asyncio
    async def test_save_step_state_updates_existing(self, project_id):
        step = PipelineStep.KEYFRAME_GENERATION
        await save_step_state(project_id, step, StepStatus.PENDING.value)
        await save_step_state(project_id, step, StepStatus.RUNNING.value, progress=0.5)
        await save_step_state(project_id, step, StepStatus.COMPLETED.value, progress=1.0)

        states = await load_step_states(project_id)
        assert states["keyframe_generation"]["status"] == "completed"
        assert states["keyframe_generation"]["progress"] == 1.0

    @pytest.mark.asyncio
    async def test_save_step_state_with_error(self, project_id):
        await save_step_state(
            project_id, PipelineStep.VIDEO_GENERATION,
            StepStatus.FAILED.value, error_message="GPU OOM",
        )
        states = await load_step_states(project_id)
        assert states["video_generation"]["status"] == "failed"
        assert states["video_generation"]["error_message"] == "GPU OOM"

    @pytest.mark.asyncio
    async def test_load_empty_states(self, project_id):
        states = await load_step_states(project_id)
        assert states == {}

    @pytest.mark.asyncio
    async def test_update_project_status(self, project_id):
        await update_project_status(project_id, "processing", "character_extraction")
        conn = await get_connection()
        try:
            cursor = await conn.execute(
                "SELECT status, current_step FROM projects WHERE id=?",
                (project_id,),
            )
            row = await cursor.fetchone()
            assert row[0] == "processing"
            assert row[1] == "character_extraction"
        finally:
            await conn.close()


# ============================================================
# Tests: PipelineEngine.get_status
# ============================================================

class TestGetStatus:
    def test_status_before_start(self, engine):
        status = engine.get_status("nonexistent")
        assert status.current_step is None
        assert status.progress == 0.0
        assert not status.is_running

    @pytest.mark.asyncio
    async def test_status_during_run(self, engine, project_id):
        """Manually set engine state to simulate running."""
        engine._running[project_id] = True
        engine._current_steps[project_id] = PipelineStep.KEYFRAME_GENERATION
        engine._progress[project_id] = 0.33

        status = engine.get_status(project_id)
        assert status.current_step == PipelineStep.KEYFRAME_GENERATION
        assert status.is_running
        assert "关键帧" in status.step_detail

    @pytest.mark.asyncio
    async def test_status_waiting_confirmation(self, engine, project_id):
        engine._running[project_id] = True
        engine._waiting_confirmation[project_id] = True
        engine._current_steps[project_id] = PipelineStep.CHARACTER_EXTRACTION
        engine._progress[project_id] = 0.0

        status = engine.get_status(project_id)
        assert status.is_waiting_confirmation
        assert "确认" in status.step_detail


# ============================================================
# Tests: PipelineEngine.start
# ============================================================

class TestStart:
    @pytest.mark.asyncio
    async def test_start_initializes_states(self, engine, project_id):
        """Start should initialize all step states as pending."""
        mocks = register_fast_executors(engine)

        # Auto-confirm confirmation steps
        async def auto_confirm():
            while True:
                await asyncio.sleep(0.05)
                if engine._waiting_confirmation.get(project_id, False):
                    await engine.confirm_step(project_id)

        confirm_task = asyncio.create_task(auto_confirm())
        try:
            await engine.start(project_id)
            # Wait for pipeline to complete
            task = engine._tasks.get(project_id)
            if task:
                await asyncio.wait_for(task, timeout=5.0)
        finally:
            confirm_task.cancel()
            try:
                await confirm_task
            except asyncio.CancelledError:
                pass

        # All steps should be completed
        states = await load_step_states(project_id)
        for step in STEP_ORDER:
            assert step.value in states
            assert states[step.value]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_start_raises_if_already_running(self, engine, project_id):
        engine._running[project_id] = True
        with pytest.raises(PipelineAlreadyRunningError):
            await engine.start(project_id)

    @pytest.mark.asyncio
    async def test_start_calls_executors_in_order(self, engine, project_id):
        """Verify all step executors are called in the correct order."""
        call_order = []

        for step in STEP_ORDER:
            async def make_executor(pid, s=step):
                call_order.append(s)
            engine.register_step_executor(step, make_executor)

        async def auto_confirm():
            while True:
                await asyncio.sleep(0.05)
                if engine._waiting_confirmation.get(project_id, False):
                    await engine.confirm_step(project_id)

        confirm_task = asyncio.create_task(auto_confirm())
        try:
            await engine.start(project_id)
            task = engine._tasks.get(project_id)
            if task:
                await asyncio.wait_for(task, timeout=5.0)
        finally:
            confirm_task.cancel()
            try:
                await confirm_task
            except asyncio.CancelledError:
                pass

        assert call_order == list(STEP_ORDER)


# ============================================================
# Tests: Auto-save after each step (Req 8.4)
# ============================================================

class TestAutoSave:
    @pytest.mark.asyncio
    async def test_each_step_saved_after_completion(self, engine, project_id):
        """Each step should be saved as completed after execution."""
        saved_steps = []

        for step in STEP_ORDER:
            async def make_executor(s=step):
                pass  # no-op
            engine.register_step_executor(step, make_executor)

        async def auto_confirm():
            while True:
                await asyncio.sleep(0.05)
                if engine._waiting_confirmation.get(project_id, False):
                    # Check that the completed step was saved before confirmation
                    states = await load_step_states(project_id)
                    for s in STEP_ORDER:
                        if states.get(s.value, {}).get("status") == "completed":
                            if s.value not in saved_steps:
                                saved_steps.append(s.value)
                    await engine.confirm_step(project_id)

        confirm_task = asyncio.create_task(auto_confirm())
        try:
            await engine.start(project_id)
            task = engine._tasks.get(project_id)
            if task:
                await asyncio.wait_for(task, timeout=5.0)
        finally:
            confirm_task.cancel()
            try:
                await confirm_task
            except asyncio.CancelledError:
                pass

        # Verify all steps are saved as completed
        states = await load_step_states(project_id)
        for step in STEP_ORDER:
            assert states[step.value]["status"] == "completed"
            assert states[step.value]["progress"] == 1.0


# ============================================================
# Tests: Confirmation mechanism
# ============================================================

class TestConfirmation:
    @pytest.mark.asyncio
    async def test_pipeline_waits_after_character_extraction(self, engine, project_id):
        """Pipeline should pause after character extraction for confirmation."""
        register_fast_executors(engine)

        await engine.start(project_id)

        # Wait a bit for the pipeline to reach the confirmation point
        for _ in range(50):
            await asyncio.sleep(0.05)
            if engine._waiting_confirmation.get(project_id, False):
                break

        assert engine._waiting_confirmation.get(project_id, False)
        status = engine.get_status(project_id)
        assert status.is_waiting_confirmation

        # Confirm and let it continue to next confirmation step
        await engine.confirm_step(project_id)

        # Wait for storyboard confirmation
        for _ in range(50):
            await asyncio.sleep(0.05)
            if engine._waiting_confirmation.get(project_id, False):
                break

        assert engine._waiting_confirmation.get(project_id, False)

        # Confirm storyboard
        await engine.confirm_step(project_id)

        # Wait for completion
        task = engine._tasks.get(project_id)
        if task:
            await asyncio.wait_for(task, timeout=5.0)

        status = engine.get_status(project_id)
        assert not status.is_running

    @pytest.mark.asyncio
    async def test_confirm_step_releases_wait(self, engine, project_id):
        """confirm_step should release the waiting state."""
        engine._waiting_confirmation[project_id] = True
        await engine.confirm_step(project_id)
        assert not engine._waiting_confirmation.get(project_id, False)


# ============================================================
# Tests: Cancel (Req 8.6)
# ============================================================

class TestCancel:
    @pytest.mark.asyncio
    async def test_cancel_stops_pipeline(self, engine, project_id):
        """Cancel should stop the pipeline and not execute further steps."""
        executed_steps = []

        async def tracking_executor(pid, s=None):
            executed_steps.append(s)
            # Simulate some work
            await asyncio.sleep(0.05)

        for step in STEP_ORDER:
            async def make_exec(pid, s=step):
                executed_steps.append(s)
                await asyncio.sleep(0.05)
            engine.register_step_executor(step, make_exec)

        await engine.start(project_id)

        # Wait for first step to complete and reach confirmation
        for _ in range(50):
            await asyncio.sleep(0.05)
            if engine._waiting_confirmation.get(project_id, False):
                break

        # Cancel while waiting for confirmation
        await engine.cancel(project_id)

        task = engine._tasks.get(project_id)
        if task:
            await asyncio.wait_for(task, timeout=5.0)

        assert not engine._running.get(project_id, False)
        # Only the first step should have been executed
        assert len(executed_steps) == 1

    @pytest.mark.asyncio
    async def test_cancel_saves_intermediate_results(self, engine, project_id):
        """Cancel should preserve completed step results."""
        step_counter = {"count": 0}

        async def counting_executor(pid):
            step_counter["count"] += 1

        for step in STEP_ORDER:
            engine.register_step_executor(step, counting_executor)

        # Start and auto-confirm first step, then cancel during wait for second
        await engine.start(project_id)

        # Wait for first confirmation
        for _ in range(50):
            await asyncio.sleep(0.05)
            if engine._waiting_confirmation.get(project_id, False):
                break

        # First step should be completed
        states = await load_step_states(project_id)
        assert states.get("character_extraction", {}).get("status") == "completed"

        # Cancel while waiting for confirmation
        await engine.cancel(project_id)

        task = engine._tasks.get(project_id)
        if task:
            await asyncio.wait_for(task, timeout=5.0)

        # Verify first step result is preserved
        states = await load_step_states(project_id)
        assert states["character_extraction"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_cancel_during_confirmation_wait(self, engine, project_id):
        """Cancel during confirmation wait should work."""
        register_fast_executors(engine)

        await engine.start(project_id)

        # Wait for confirmation
        for _ in range(50):
            await asyncio.sleep(0.05)
            if engine._waiting_confirmation.get(project_id, False):
                break

        assert engine._waiting_confirmation.get(project_id, False)

        # Cancel
        await engine.cancel(project_id)

        task = engine._tasks.get(project_id)
        if task:
            await asyncio.wait_for(task, timeout=5.0)

        assert not engine._running.get(project_id, False)

    @pytest.mark.asyncio
    async def test_cancel_emits_event(self, engine, project_id):
        """Cancel should emit a pipeline_cancelled event."""
        events = []

        async def capture_event(event):
            events.append(event)

        engine.register_event_callback(project_id, capture_event)
        register_fast_executors(engine)

        await engine.start(project_id)
        await asyncio.sleep(0.1)
        await engine.cancel(project_id)

        task = engine._tasks.get(project_id)
        if task:
            await asyncio.wait_for(task, timeout=5.0)

        cancel_events = [e for e in events if e["type"] == "pipeline_cancelled"]
        assert len(cancel_events) >= 1


# ============================================================
# Tests: Resume
# ============================================================

class TestResume:
    @pytest.mark.asyncio
    async def test_resume_from_specific_step(self, engine, project_id):
        """Resume should start from the specified step."""
        call_order = []

        for step in STEP_ORDER:
            async def make_executor(pid, s=step):
                call_order.append(s)
            engine.register_step_executor(step, make_executor)

        # Resume from keyframe generation (skip first two steps)
        await engine.resume(project_id, PipelineStep.KEYFRAME_GENERATION)

        task = engine._tasks.get(project_id)
        if task:
            await asyncio.wait_for(task, timeout=5.0)

        # Should only execute steps from keyframe_generation onwards
        expected = STEP_ORDER[2:]  # keyframe, video, tts, composition
        assert call_order == expected

    @pytest.mark.asyncio
    async def test_resume_raises_if_already_running(self, engine, project_id):
        engine._running[project_id] = True
        with pytest.raises(PipelineAlreadyRunningError):
            await engine.resume(project_id, PipelineStep.KEYFRAME_GENERATION)

    @pytest.mark.asyncio
    async def test_resume_raises_for_invalid_step(self, engine, project_id):
        with pytest.raises(ValueError):
            await engine.resume(project_id, "invalid_step")

    @pytest.mark.asyncio
    async def test_resume_resets_step_states(self, engine, project_id):
        """Resume should reset states for steps from the resume point."""
        # Pre-set some states
        await save_step_state(project_id, PipelineStep.KEYFRAME_GENERATION, StepStatus.FAILED.value)
        await save_step_state(project_id, PipelineStep.VIDEO_GENERATION, StepStatus.PENDING.value)

        register_fast_executors(engine)

        await engine.resume(project_id, PipelineStep.KEYFRAME_GENERATION)

        task = engine._tasks.get(project_id)
        if task:
            await asyncio.wait_for(task, timeout=5.0)

        states = await load_step_states(project_id)
        # All resumed steps should be completed
        for step in STEP_ORDER[2:]:
            assert states[step.value]["status"] == "completed"


# ============================================================
# Tests: Error handling
# ============================================================

class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_step_failure_saves_error_state(self, engine, project_id):
        """When a step fails, error state should be saved."""
        async def failing_executor(pid):
            raise RuntimeError("GPU out of memory")

        engine.register_step_executor(PipelineStep.CHARACTER_EXTRACTION, failing_executor)

        await engine.start(project_id)

        task = engine._tasks.get(project_id)
        if task:
            await asyncio.wait_for(task, timeout=5.0)

        states = await load_step_states(project_id)
        assert states["character_extraction"]["status"] == "failed"
        assert "GPU out of memory" in states["character_extraction"]["error_message"]

    @pytest.mark.asyncio
    async def test_step_failure_stops_pipeline(self, engine, project_id):
        """Pipeline should stop after a step failure."""
        call_order = []

        async def fail_on_storyboard(pid):
            raise RuntimeError("LLM timeout")

        async def track_executor(pid, s=None):
            call_order.append(s)

        engine.register_step_executor(
            PipelineStep.CHARACTER_EXTRACTION,
            lambda pid: track_executor(pid, s=PipelineStep.CHARACTER_EXTRACTION),
        )
        engine.register_step_executor(
            PipelineStep.STORYBOARD_GENERATION, fail_on_storyboard,
        )

        # Auto-confirm
        async def auto_confirm():
            while True:
                await asyncio.sleep(0.05)
                if engine._waiting_confirmation.get(project_id, False):
                    await engine.confirm_step(project_id)

        confirm_task = asyncio.create_task(auto_confirm())
        try:
            await engine.start(project_id)
            task = engine._tasks.get(project_id)
            if task:
                await asyncio.wait_for(task, timeout=5.0)
        finally:
            confirm_task.cancel()
            try:
                await confirm_task
            except asyncio.CancelledError:
                pass

        # Only character_extraction should have been called
        assert PipelineStep.CHARACTER_EXTRACTION in call_order
        # Storyboard was called but failed
        states = await load_step_states(project_id)
        assert states["storyboard_generation"]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_step_failure_emits_error_event(self, engine, project_id):
        """Step failure should emit a step_failed event."""
        events = []

        async def capture_event(event):
            events.append(event)

        engine.register_event_callback(project_id, capture_event)

        async def failing_executor(pid):
            raise RuntimeError("test error")

        engine.register_step_executor(PipelineStep.CHARACTER_EXTRACTION, failing_executor)

        await engine.start(project_id)
        task = engine._tasks.get(project_id)
        if task:
            await asyncio.wait_for(task, timeout=5.0)

        error_events = [e for e in events if e["type"] == "step_failed"]
        assert len(error_events) == 1
        assert "test error" in error_events[0]["error"]


# ============================================================
# Tests: Event callbacks
# ============================================================

class TestEventCallbacks:
    @pytest.mark.asyncio
    async def test_step_events_emitted(self, engine, project_id):
        """Pipeline should emit step_started and step_completed events."""
        events = []

        async def capture_event(event):
            events.append(event)

        engine.register_event_callback(project_id, capture_event)
        register_fast_executors(engine)

        async def auto_confirm():
            while True:
                await asyncio.sleep(0.05)
                if engine._waiting_confirmation.get(project_id, False):
                    await engine.confirm_step(project_id)

        confirm_task = asyncio.create_task(auto_confirm())
        try:
            await engine.start(project_id)
            task = engine._tasks.get(project_id)
            if task:
                await asyncio.wait_for(task, timeout=5.0)
        finally:
            confirm_task.cancel()
            try:
                await confirm_task
            except asyncio.CancelledError:
                pass

        started_events = [e for e in events if e["type"] == "step_started"]
        completed_events = [e for e in events if e["type"] == "step_completed"]
        pipeline_completed = [e for e in events if e["type"] == "pipeline_completed"]

        assert len(started_events) == 6
        assert len(completed_events) == 6
        assert len(pipeline_completed) == 1

    @pytest.mark.asyncio
    async def test_unregister_callback(self, engine, project_id):
        events = []

        async def capture_event(event):
            events.append(event)

        engine.register_event_callback(project_id, capture_event)
        engine.unregister_event_callback(project_id, capture_event)

        await engine._emit_event(project_id, {"type": "test"})
        assert len(events) == 0


# ============================================================
# Tests: Full pipeline flow
# ============================================================

class TestFullPipelineFlow:
    @pytest.mark.asyncio
    async def test_complete_pipeline_run(self, engine, project_id):
        """Test a complete pipeline run from start to finish."""
        register_fast_executors(engine)

        async def auto_confirm():
            while True:
                await asyncio.sleep(0.05)
                if engine._waiting_confirmation.get(project_id, False):
                    await engine.confirm_step(project_id)

        confirm_task = asyncio.create_task(auto_confirm())
        try:
            await engine.start(project_id)
            task = engine._tasks.get(project_id)
            if task:
                await asyncio.wait_for(task, timeout=5.0)
        finally:
            confirm_task.cancel()
            try:
                await confirm_task
            except asyncio.CancelledError:
                pass

        # Verify final state
        assert not engine._running.get(project_id, False)
        assert engine._progress.get(project_id) == 1.0

        # Verify project status
        conn = await get_connection()
        try:
            cursor = await conn.execute(
                "SELECT status FROM projects WHERE id=?", (project_id,),
            )
            row = await cursor.fetchone()
            assert row[0] == "completed"
        finally:
            await conn.close()

        # Verify all steps completed
        states = await load_step_states(project_id)
        for step in STEP_ORDER:
            assert states[step.value]["status"] == "completed"
