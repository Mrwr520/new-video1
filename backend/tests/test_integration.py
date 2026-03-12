"""API 集成测试

测试完整的项目创建到导出流程（使用 mock 服务），
测试错误处理和重试逻辑，
测试 Pipeline 取消和恢复。

Requirements: 全部
"""

import asyncio
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import get_connection, init_db, set_db_path
from app.main import app
from app.api.events import get_engine, set_engine
from app.pipeline import (
    PipelineEngine,
    PipelineStep,
    STEP_ORDER,
    load_step_states,
)


# ============================================================
# Fixtures
# ============================================================

@pytest_asyncio.fixture
async def tmp_db(tmp_path):
    """Create a temporary database for each test."""
    db_path = tmp_path / "test.db"
    set_db_path(db_path)
    await init_db()
    yield db_path


@pytest_asyncio.fixture
async def client(tmp_db):
    """Create test HTTP client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def project_id(client):
    """Create a test project and return its ID."""
    resp = await client.post("/api/projects", json={
        "name": "Integration Test Project",
        "template_id": "anime",
    })
    assert resp.status_code == 201
    return resp.json()["id"]


def _make_engine_with_mock_executors() -> tuple[PipelineEngine, dict[PipelineStep, AsyncMock]]:
    """Create a PipelineEngine with mock executors that complete instantly."""
    engine = PipelineEngine()
    mocks = {}
    for step in STEP_ORDER:
        mock = AsyncMock(return_value=None)
        engine.register_step_executor(step, mock)
        mocks[step] = mock
    return engine, mocks


async def _auto_confirm_loop(engine: PipelineEngine, project_id: str):
    """Background task that auto-confirms pipeline confirmation steps."""
    while True:
        await asyncio.sleep(0.05)
        if engine._waiting_confirmation.get(project_id, False):
            await engine.confirm_step(project_id)


async def _run_pipeline_to_completion(engine: PipelineEngine, project_id: str, timeout: float = 10.0):
    """Start pipeline and auto-confirm until completion."""
    confirm_task = asyncio.create_task(_auto_confirm_loop(engine, project_id))
    try:
        await engine.start(project_id)
        task = engine._tasks.get(project_id)
        if task:
            await asyncio.wait_for(task, timeout=timeout)
    finally:
        confirm_task.cancel()
        try:
            await confirm_task
        except asyncio.CancelledError:
            pass


# ============================================================
# Test 1: Full workflow integration (create → text → pipeline → export)
# ============================================================

class TestFullWorkflowIntegration:
    """Test the complete project lifecycle through the API with mock services."""

    @pytest.mark.asyncio
    async def test_full_project_lifecycle(self, client, tmp_db):
        """Create project → submit text → start pipeline → confirm steps → complete → export."""
        # Step 1: Create project
        resp = await client.post("/api/projects", json={
            "name": "Full Workflow Test",
            "template_id": "anime",
        })
        assert resp.status_code == 201
        project = resp.json()
        pid = project["id"]
        assert project["status"] == "created"

        # Step 2: Submit text
        resp = await client.post(f"/api/projects/{pid}/text", json={
            "text": "这是一个测试故事。主角小明在森林中冒险，遇到了神秘的精灵。他们一起踏上了寻找宝藏的旅程。"
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "valid"

        # Step 3: Verify project has text
        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["source_text"] is not None

        # Step 4: Set up mock pipeline engine and start pipeline
        engine, mocks = _make_engine_with_mock_executors()

        # Mock character extraction to insert characters into DB
        async def mock_char_extraction(project_id):
            conn = await get_connection()
            try:
                await conn.execute(
                    "INSERT INTO characters (id, project_id, name, appearance, personality, background, image_prompt, confirmed) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (f"char-{uuid.uuid4().hex[:8]}", project_id, "小明", "少年", "勇敢", "冒险者", "a brave boy", False),
                )
                await conn.commit()
            finally:
                await conn.close()

        # Mock storyboard generation to insert scenes into DB
        async def mock_storyboard_gen(project_id):
            conn = await get_connection()
            try:
                for i in range(2):
                    await conn.execute(
                        "INSERT INTO scenes (id, project_id, scene_order, scene_description, dialogue, "
                        "camera_direction, image_prompt, motion_prompt, confirmed) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (f"scene-{uuid.uuid4().hex[:8]}", project_id, i + 1,
                         f"场景{i+1}描述", f"台词{i+1}", "中景", f"prompt{i+1}", f"motion{i+1}", False),
                    )
                await conn.commit()
            finally:
                await conn.close()

        # Mock keyframe generation to set keyframe_path
        async def mock_keyframe_gen(project_id):
            conn = await get_connection()
            try:
                cursor = await conn.execute(
                    "SELECT id FROM scenes WHERE project_id = ?", (project_id,)
                )
                rows = await cursor.fetchall()
                for row in rows:
                    await conn.execute(
                        "UPDATE scenes SET keyframe_path = ? WHERE id = ?",
                        (f"keyframes/scene_{row['id']}.png", row["id"]),
                    )
                await conn.commit()
            finally:
                await conn.close()

        # Mock video generation to set video_path and duration
        async def mock_video_gen(project_id):
            conn = await get_connection()
            try:
                cursor = await conn.execute(
                    "SELECT id FROM scenes WHERE project_id = ?", (project_id,)
                )
                rows = await cursor.fetchall()
                for row in rows:
                    await conn.execute(
                        "UPDATE scenes SET video_path = ?, duration = ? WHERE id = ?",
                        (f"videos/scene_{row['id']}.mp4", 5.0, row["id"]),
                    )
                await conn.commit()
            finally:
                await conn.close()

        # Mock TTS to set audio_path
        async def mock_tts_gen(project_id):
            conn = await get_connection()
            try:
                cursor = await conn.execute(
                    "SELECT id FROM scenes WHERE project_id = ?", (project_id,)
                )
                rows = await cursor.fetchall()
                for row in rows:
                    await conn.execute(
                        "UPDATE scenes SET audio_path = ? WHERE id = ?",
                        (f"audio/scene_{row['id']}.wav", row["id"]),
                    )
                await conn.commit()
            finally:
                await conn.close()

        # Mock composition (no-op, just marks project as completed)
        async def mock_composition(project_id):
            pass

        engine.register_step_executor(PipelineStep.CHARACTER_EXTRACTION, mock_char_extraction)
        engine.register_step_executor(PipelineStep.STORYBOARD_GENERATION, mock_storyboard_gen)
        engine.register_step_executor(PipelineStep.KEYFRAME_GENERATION, mock_keyframe_gen)
        engine.register_step_executor(PipelineStep.VIDEO_GENERATION, mock_video_gen)
        engine.register_step_executor(PipelineStep.TTS_GENERATION, mock_tts_gen)
        engine.register_step_executor(PipelineStep.COMPOSITION, mock_composition)
        set_engine(engine)

        # Start pipeline via API
        resp = await client.post(f"/api/projects/{pid}/start")
        assert resp.status_code == 200

        # Auto-confirm and wait for completion
        confirm_task = asyncio.create_task(_auto_confirm_loop(engine, pid))
        try:
            task = engine._tasks.get(pid)
            if task:
                await asyncio.wait_for(task, timeout=10.0)
        finally:
            confirm_task.cancel()
            try:
                await confirm_task
            except asyncio.CancelledError:
                pass

        # Step 5: Verify pipeline completed
        resp = await client.get(f"/api/projects/{pid}/pipeline-status")
        assert resp.status_code == 200
        status = resp.json()
        assert status["is_running"] is False

        # All steps should be completed
        states = await load_step_states(pid)
        for step in STEP_ORDER:
            assert states[step.value]["status"] == "completed"

        # Step 6: Verify project status is completed
        resp = await client.get(f"/api/projects/{pid}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

        # Step 7: Verify characters were created
        resp = await client.get(f"/api/projects/{pid}/characters")
        assert resp.status_code == 200
        chars = resp.json()
        assert len(chars) >= 1

        # Step 8: Verify scenes were created
        resp = await client.get(f"/api/projects/{pid}/scenes")
        assert resp.status_code == 200
        scenes = resp.json()
        assert len(scenes) == 2

    @pytest.mark.asyncio
    async def test_project_status_transitions(self, client, tmp_db):
        """Verify project status transitions: created → text_submitted → processing → completed."""
        # Create
        resp = await client.post("/api/projects", json={
            "name": "Status Transition Test",
            "template_id": "anime",
        })
        pid = resp.json()["id"]
        assert resp.json()["status"] == "created"

        # Submit text → text_submitted
        resp = await client.post(f"/api/projects/{pid}/text", json={
            "text": "一段足够长的测试文本内容，用于验证状态转换流程。"
        })
        assert resp.json()["status"] == "valid"

        resp = await client.get(f"/api/projects/{pid}")
        assert resp.json()["status"] == "text_submitted"

        # Start pipeline → processing
        engine, _ = _make_engine_with_mock_executors()
        set_engine(engine)

        resp = await client.post(f"/api/projects/{pid}/start")
        assert resp.status_code == 200

        # Wait briefly for pipeline to start
        await asyncio.sleep(0.1)

        resp = await client.get(f"/api/projects/{pid}/pipeline-status")
        assert resp.json()["is_running"] is True

        # Complete pipeline → completed
        confirm_task = asyncio.create_task(_auto_confirm_loop(engine, pid))
        try:
            task = engine._tasks.get(pid)
            if task:
                await asyncio.wait_for(task, timeout=10.0)
        finally:
            confirm_task.cancel()
            try:
                await confirm_task
            except asyncio.CancelledError:
                pass

        resp = await client.get(f"/api/projects/{pid}")
        assert resp.json()["status"] == "completed"


# ============================================================
# Test 2: Error handling and retry logic
# ============================================================

class TestErrorHandlingIntegration:
    """Test error handling through the API layer."""

    @pytest.mark.asyncio
    async def test_pipeline_step_failure_saves_error_and_can_resume(self, client, project_id):
        """Start pipeline → step fails → verify error state → resume from failed step."""
        engine = PipelineEngine()

        # Character extraction succeeds
        engine.register_step_executor(
            PipelineStep.CHARACTER_EXTRACTION, AsyncMock(return_value=None)
        )
        # Storyboard generation fails
        async def failing_storyboard(pid):
            raise RuntimeError("LLM API timeout")

        engine.register_step_executor(
            PipelineStep.STORYBOARD_GENERATION, failing_storyboard
        )
        # Register remaining steps as no-ops
        for step in STEP_ORDER[2:]:
            engine.register_step_executor(step, AsyncMock(return_value=None))

        set_engine(engine)

        # Start pipeline
        resp = await client.post(f"/api/projects/{project_id}/start")
        assert resp.status_code == 200

        # Auto-confirm character extraction
        confirm_task = asyncio.create_task(_auto_confirm_loop(engine, project_id))
        try:
            task = engine._tasks.get(project_id)
            if task:
                await asyncio.wait_for(task, timeout=10.0)
        finally:
            confirm_task.cancel()
            try:
                await confirm_task
            except asyncio.CancelledError:
                pass

        # Verify error state via API
        resp = await client.get(f"/api/projects/{project_id}/pipeline-status")
        assert resp.status_code == 200
        status = resp.json()
        assert status["is_running"] is False

        # Verify step states
        states = await load_step_states(project_id)
        assert states["character_extraction"]["status"] == "completed"
        assert states["storyboard_generation"]["status"] == "failed"
        assert "LLM API timeout" in states["storyboard_generation"]["error_message"]

        # Verify project is in error state
        resp = await client.get(f"/api/projects/{project_id}")
        assert resp.json()["status"] == "error"

        # Now fix the executor and resume
        engine._running[project_id] = False  # Reset running state
        engine.register_step_executor(
            PipelineStep.STORYBOARD_GENERATION, AsyncMock(return_value=None)
        )

        # Resume from the failed step
        await engine.resume(project_id, PipelineStep.STORYBOARD_GENERATION)

        # Auto-confirm storyboard step
        confirm_task = asyncio.create_task(_auto_confirm_loop(engine, project_id))
        try:
            task = engine._tasks.get(project_id)
            if task:
                await asyncio.wait_for(task, timeout=10.0)
        finally:
            confirm_task.cancel()
            try:
                await confirm_task
            except asyncio.CancelledError:
                pass

        # Verify all steps completed after resume
        states = await load_step_states(project_id)
        for step in STEP_ORDER[1:]:  # From storyboard onwards
            assert states[step.value]["status"] == "completed"

        # Project should be completed
        resp = await client.get(f"/api/projects/{project_id}")
        assert resp.json()["status"] == "completed"

    @pytest.mark.asyncio
    async def test_start_pipeline_nonexistent_project(self, client):
        """Starting pipeline for a non-existent project returns 404."""
        engine, _ = _make_engine_with_mock_executors()
        set_engine(engine)

        resp = await client.post("/api/projects/nonexistent-id/start")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_start_pipeline_already_running(self, client, project_id):
        """Starting pipeline when already running returns 409."""
        engine, _ = _make_engine_with_mock_executors()
        set_engine(engine)

        resp = await client.post(f"/api/projects/{project_id}/start")
        assert resp.status_code == 200

        resp = await client.post(f"/api/projects/{project_id}/start")
        assert resp.status_code == 409

        # Cleanup
        await engine.cancel(project_id)


# ============================================================
# Test 3: Pipeline cancel
# ============================================================

class TestPipelineCancelIntegration:
    """Test pipeline cancellation through the API."""

    @pytest.mark.asyncio
    async def test_cancel_during_execution_saves_intermediate_results(self, client, project_id):
        """Start pipeline → cancel during execution → verify intermediate results saved."""
        engine = PipelineEngine()

        # Character extraction completes normally
        engine.register_step_executor(
            PipelineStep.CHARACTER_EXTRACTION, AsyncMock(return_value=None)
        )
        # Register remaining steps
        for step in STEP_ORDER[1:]:
            engine.register_step_executor(step, AsyncMock(return_value=None))

        set_engine(engine)

        # Start pipeline via API
        resp = await client.post(f"/api/projects/{project_id}/start")
        assert resp.status_code == 200

        # Wait for pipeline to reach confirmation point (after character extraction)
        for _ in range(100):
            await asyncio.sleep(0.05)
            if engine._waiting_confirmation.get(project_id, False):
                break

        assert engine._waiting_confirmation.get(project_id, False), \
            "Pipeline should be waiting for confirmation"

        # Cancel via API
        resp = await client.post(f"/api/projects/{project_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Pipeline 已取消"

        # Wait for task to finish
        task = engine._tasks.get(project_id)
        if task:
            await asyncio.wait_for(task, timeout=5.0)

        # Verify intermediate results: character extraction should be completed
        states = await load_step_states(project_id)
        assert states["character_extraction"]["status"] == "completed"

        # Pipeline should not be running
        resp = await client.get(f"/api/projects/{project_id}/pipeline-status")
        assert resp.status_code == 200
        assert resp.json()["is_running"] is False

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_project(self, client):
        """Cancelling pipeline for non-existent project returns 404."""
        engine, _ = _make_engine_with_mock_executors()
        set_engine(engine)

        resp = await client.post("/api/projects/nonexistent-id/cancel")
        assert resp.status_code == 404


# ============================================================
# Test 4: Pipeline resume
# ============================================================

class TestPipelineResumeIntegration:
    """Test pipeline resume after cancel."""

    @pytest.mark.asyncio
    async def test_cancel_then_resume_completes_pipeline(self, client, project_id):
        """Start → cancel → resume from specific step → verify completion."""
        engine = PipelineEngine()

        executed_steps = []

        for step in STEP_ORDER:
            async def make_executor(pid, s=step):
                executed_steps.append(s)
            engine.register_step_executor(step, make_executor)

        set_engine(engine)

        # Start pipeline
        resp = await client.post(f"/api/projects/{project_id}/start")
        assert resp.status_code == 200

        # Wait for first confirmation (after character extraction)
        for _ in range(100):
            await asyncio.sleep(0.05)
            if engine._waiting_confirmation.get(project_id, False):
                break

        # Cancel
        resp = await client.post(f"/api/projects/{project_id}/cancel")
        assert resp.status_code == 200

        task = engine._tasks.get(project_id)
        if task:
            await asyncio.wait_for(task, timeout=5.0)

        # Verify only first step was executed
        assert PipelineStep.CHARACTER_EXTRACTION in executed_steps
        assert PipelineStep.STORYBOARD_GENERATION not in executed_steps

        # Clear executed steps for resume tracking
        executed_steps.clear()

        # Resume from storyboard generation
        await engine.resume(project_id, PipelineStep.STORYBOARD_GENERATION)

        # Auto-confirm storyboard step
        confirm_task = asyncio.create_task(_auto_confirm_loop(engine, project_id))
        try:
            task = engine._tasks.get(project_id)
            if task:
                await asyncio.wait_for(task, timeout=10.0)
        finally:
            confirm_task.cancel()
            try:
                await confirm_task
            except asyncio.CancelledError:
                pass

        # Verify all remaining steps were executed
        expected_resumed = STEP_ORDER[1:]  # storyboard onwards
        assert executed_steps == expected_resumed

        # Verify all steps completed
        states = await load_step_states(project_id)
        for step in STEP_ORDER[1:]:
            assert states[step.value]["status"] == "completed"

        # Project should be completed
        resp = await client.get(f"/api/projects/{project_id}")
        assert resp.json()["status"] == "completed"

    @pytest.mark.asyncio
    async def test_resume_from_middle_step(self, client, project_id):
        """Resume from keyframe_generation skips first two steps."""
        engine = PipelineEngine()

        executed_steps = []

        for step in STEP_ORDER:
            async def make_executor(pid, s=step):
                executed_steps.append(s)
            engine.register_step_executor(step, make_executor)

        set_engine(engine)

        # Resume directly from keyframe generation (no confirmation steps after this)
        await engine.resume(project_id, PipelineStep.KEYFRAME_GENERATION)

        task = engine._tasks.get(project_id)
        if task:
            await asyncio.wait_for(task, timeout=10.0)

        # Should only execute steps from keyframe_generation onwards
        expected = STEP_ORDER[2:]  # keyframe, video, tts, composition
        assert executed_steps == expected

        # First two steps should still be pending (not touched)
        states = await load_step_states(project_id)
        for step in STEP_ORDER[2:]:
            assert states[step.value]["status"] == "completed"
