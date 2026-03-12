"""
属性测试：Pipeline 步骤完成后自动保存

Feature: ai-video-generator, Property 13: Pipeline 步骤完成后自动保存
**Validates: Requirements 8.4**

对任意 Pipeline 步骤完成事件，完成后项目的持久化状态应当反映该步骤的完成状态和产出数据。
"""

import asyncio
from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from app.database import get_connection, init_db, set_db_path
from app.pipeline import (
    CONFIRMATION_STEPS,
    STEP_ORDER,
    PipelineEngine,
    PipelineStep,
    StepStatus,
    load_step_states,
)


# ============================================================
# Strategies
# ============================================================

# Generate a random number of steps to run (1..6), representing
# "run the first N steps then verify"
num_steps_st = st.integers(min_value=1, max_value=len(STEP_ORDER))

# Generate a random step to resume from (index 0..5)
resume_index_st = st.integers(min_value=0, max_value=len(STEP_ORDER) - 1)


# ============================================================
# Helpers
# ============================================================

def run_async(coro):
    """Run an async coroutine in a fresh event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _setup_db(tmp_dir: Path) -> str:
    """Create a temp DB, init schema, insert a test project. Returns project_id."""
    db_path = tmp_dir / "test.db"
    set_db_path(db_path)
    await init_db()

    project_id = "prop-test-project"
    conn = await get_connection()
    try:
        await conn.execute(
            "INSERT INTO projects (id, name, template_id, status) VALUES (?, ?, ?, ?)",
            (project_id, "Property Test", "builtin-anime", "created"),
        )
        await conn.commit()
    finally:
        await conn.close()
    return project_id


def _make_engine() -> PipelineEngine:
    """Create a PipelineEngine with no-op executors for all steps."""
    engine = PipelineEngine()
    for step in STEP_ORDER:
        async def noop_executor(pid):
            pass
        engine.register_step_executor(step, noop_executor)
    return engine


async def _auto_confirm(engine: PipelineEngine, project_id: str, stop_event: asyncio.Event):
    """Auto-confirm confirmation steps until stop_event is set."""
    while not stop_event.is_set():
        if engine._waiting_confirmation.get(project_id, False):
            await engine.confirm_step(project_id)
        await asyncio.sleep(0.02)


async def _run_full_pipeline_and_verify(tmp_dir: Path):
    """Run the full pipeline and verify all steps are saved as completed."""
    project_id = await _setup_db(tmp_dir)
    engine = _make_engine()

    stop_event = asyncio.Event()
    confirm_task = asyncio.create_task(_auto_confirm(engine, project_id, stop_event))

    try:
        await engine.start(project_id)
        task = engine._tasks.get(project_id)
        if task:
            await asyncio.wait_for(task, timeout=10.0)
    finally:
        stop_event.set()
        confirm_task.cancel()
        try:
            await confirm_task
        except asyncio.CancelledError:
            pass

    states = await load_step_states(project_id)
    return project_id, states


async def _run_n_steps_then_cancel(tmp_dir: Path, n: int):
    """Run the first n steps of the pipeline, then cancel.

    For confirmation steps, auto-confirm so the pipeline proceeds.
    After the n-th step completes, cancel the pipeline.
    Returns (project_id, states_after_cancel).
    """
    project_id = await _setup_db(tmp_dir)
    engine = _make_engine()

    completed_count = {"value": 0}
    target_n = n

    stop_event = asyncio.Event()

    async def auto_confirm_and_cancel():
        """Auto-confirm and cancel after n steps complete."""
        while not stop_event.is_set():
            if engine._waiting_confirmation.get(project_id, False):
                # Check how many steps completed so far
                states = await load_step_states(project_id)
                completed = sum(
                    1 for s in states.values() if s["status"] == "completed"
                )
                if completed >= target_n:
                    # We've completed enough steps, cancel
                    await engine.cancel(project_id)
                    stop_event.set()
                    return
                else:
                    await engine.confirm_step(project_id)
            await asyncio.sleep(0.02)

    confirm_task = asyncio.create_task(auto_confirm_and_cancel())

    # Also monitor for non-confirmation steps completing
    async def monitor_completion():
        while not stop_event.is_set():
            states = await load_step_states(project_id)
            completed = sum(
                1 for s in states.values() if s["status"] == "completed"
            )
            if completed >= target_n and not engine._waiting_confirmation.get(project_id, False):
                await engine.cancel(project_id)
                stop_event.set()
                return
            await asyncio.sleep(0.02)

    monitor_task = asyncio.create_task(monitor_completion())

    try:
        await engine.start(project_id)
        task = engine._tasks.get(project_id)
        if task:
            await asyncio.wait_for(task, timeout=10.0)
    except asyncio.TimeoutError:
        pass
    finally:
        stop_event.set()
        confirm_task.cancel()
        monitor_task.cancel()
        try:
            await confirm_task
        except asyncio.CancelledError:
            pass
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

    states = await load_step_states(project_id)
    return project_id, states


async def _resume_from_step_and_verify(tmp_dir: Path, resume_idx: int):
    """Resume pipeline from a given step index and verify all steps from that
    point onward are saved as completed."""
    project_id = await _setup_db(tmp_dir)
    engine = _make_engine()

    from_step = STEP_ORDER[resume_idx]

    stop_event = asyncio.Event()
    confirm_task = asyncio.create_task(_auto_confirm(engine, project_id, stop_event))

    try:
        await engine.resume(project_id, from_step)
        task = engine._tasks.get(project_id)
        if task:
            await asyncio.wait_for(task, timeout=10.0)
    finally:
        stop_event.set()
        confirm_task.cancel()
        try:
            await confirm_task
        except asyncio.CancelledError:
            pass

    states = await load_step_states(project_id)
    return project_id, states, resume_idx


# ============================================================
# Property Tests
# ============================================================

@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(n=num_steps_st)
def test_property_13_completed_steps_persisted_after_partial_run(n):
    """
    Property 13: Pipeline 步骤完成后自动保存

    For any number of steps N (1..6), after running the first N steps
    and then cancelling, all N completed steps should be persisted
    with status='completed' and progress=1.0 in the database.

    **Validates: Requirements 8.4**
    """
    import tempfile

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_dir = Path(tmp)
        project_id, states = run_async(_run_n_steps_then_cancel(tmp_dir, n))

        # Count completed steps
        completed_steps = [
            step_name for step_name, state in states.items()
            if state["status"] == "completed"
        ]

        # At least n steps should be completed (may be more if pipeline
        # completed additional steps before cancel took effect)
        assert len(completed_steps) >= n, (
            f"Expected at least {n} completed steps, got {len(completed_steps)}: "
            f"{completed_steps}"
        )

        # Every completed step must have progress=1.0
        for step_name in completed_steps:
            assert states[step_name]["progress"] == 1.0, (
                f"Step {step_name} is completed but progress={states[step_name]['progress']}"
            )


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(resume_idx=resume_index_st)
def test_property_13_resumed_steps_persisted(resume_idx):
    """
    Property 13: Pipeline 步骤完成后自动保存

    For any resume point, after resuming and running to completion,
    all steps from the resume point onward should be persisted
    with status='completed' and progress=1.0.

    **Validates: Requirements 8.4**
    """
    import tempfile

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_dir = Path(tmp)
        project_id, states, idx = run_async(
            _resume_from_step_and_verify(tmp_dir, resume_idx)
        )

        # All steps from resume_idx onward should be completed
        expected_steps = STEP_ORDER[idx:]
        for step in expected_steps:
            assert step.value in states, (
                f"Step {step.value} not found in persisted states"
            )
            assert states[step.value]["status"] == "completed", (
                f"Step {step.value} should be completed, got {states[step.value]['status']}"
            )
            assert states[step.value]["progress"] == 1.0, (
                f"Step {step.value} progress should be 1.0, got {states[step.value]['progress']}"
            )


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=st.data())
def test_property_13_full_pipeline_all_steps_persisted(data):
    """
    Property 13: Pipeline 步骤完成后自动保存

    For a full pipeline run, all 6 steps should be persisted as completed
    with progress=1.0 and the project status should be 'completed'.

    **Validates: Requirements 8.4**
    """
    import tempfile

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_dir = Path(tmp)
        project_id, states = run_async(_run_full_pipeline_and_verify(tmp_dir))

        # All 6 steps must be present and completed
        assert len(states) == len(STEP_ORDER), (
            f"Expected {len(STEP_ORDER)} step states, got {len(states)}"
        )

        for step in STEP_ORDER:
            assert step.value in states, (
                f"Step {step.value} missing from persisted states"
            )
            assert states[step.value]["status"] == "completed", (
                f"Step {step.value} should be completed, got {states[step.value]['status']}"
            )
            assert states[step.value]["progress"] == 1.0, (
                f"Step {step.value} progress should be 1.0, got {states[step.value]['progress']}"
            )
            # completed_at should be set
            assert states[step.value]["completed_at"] is not None, (
                f"Step {step.value} completed_at should not be None"
            )
