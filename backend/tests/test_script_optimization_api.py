"""剧本迭代优化 API 路由测试

测试 POST /start, GET /status, GET /versions, GET /versions/{iteration}
以及请求验证和错误响应。
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio

from app.database import get_connection


# ---------------------------------------------------------------------------
# Helpers: seed a session + versions directly in the DB
# ---------------------------------------------------------------------------

async def _seed_session(db, session_id="test-session-1", status="completed"):
    """Insert a test optimization session."""
    await db.execute(
        """
        INSERT INTO optimization_sessions
            (id, initial_prompt, target_score, max_iterations, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (session_id, "测试提示词", 8.0, 20, status, "2024-01-01T00:00:00+00:00"),
    )
    await db.commit()


async def _seed_version(db, session_id="test-session-1", iteration=0, score=7.5, is_final=False):
    """Insert a test script version."""
    dimension_scores = json.dumps({
        "content_quality": 8.0,
        "structure": 7.0,
        "creativity": 7.5,
        "hotspot_relevance": 6.5,
        "technique_application": 7.0,
    })
    suggestions = json.dumps(["改进建议1", "改进建议2"])
    hotspots = json.dumps([])
    techniques = json.dumps([])
    await db.execute(
        """
        INSERT INTO script_versions
            (session_id, iteration, script, total_score,
             dimension_scores, suggestions, hotspots, techniques,
             is_final, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id, iteration, f"剧本内容 v{iteration}", score,
            dimension_scores, suggestions, hotspots, techniques,
            is_final, "2024-01-01T00:00:00+00:00",
        ),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# Tests: POST /api/script-optimization/start
# ---------------------------------------------------------------------------

class TestStartOptimization:
    """POST /api/script-optimization/start 端点测试"""

    @pytest.mark.asyncio
    async def test_start_returns_session_id(self, client, tmp_db):
        """启动优化应返回 session_id 和 running 状态"""
        with patch(
            "app.api.script_optimization._run_optimization",
            new_callable=AsyncMock,
        ):
            response = await client.post(
                "/api/script-optimization/start",
                json={"initial_prompt": "测试剧本提示词"},
            )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["status"] == "running"
        assert data["message"] == "优化流程已启动"

    @pytest.mark.asyncio
    async def test_start_creates_session_in_db(self, client, tmp_db):
        """启动优化应在数据库中创建会话记录"""
        with patch(
            "app.api.script_optimization._run_optimization",
            new_callable=AsyncMock,
        ):
            response = await client.post(
                "/api/script-optimization/start",
                json={
                    "initial_prompt": "测试提示词",
                    "target_score": 9.0,
                    "max_iterations": 10,
                },
            )
        session_id = response.json()["session_id"]

        db = await get_connection()
        try:
            cursor = await db.execute(
                "SELECT * FROM optimization_sessions WHERE id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row["initial_prompt"] == "测试提示词"
            assert row["target_score"] == 9.0
            assert row["max_iterations"] == 10
            assert row["status"] == "running"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_start_with_default_params(self, client, tmp_db):
        """使用默认参数启动优化"""
        with patch(
            "app.api.script_optimization._run_optimization",
            new_callable=AsyncMock,
        ):
            response = await client.post(
                "/api/script-optimization/start",
                json={"initial_prompt": "默认参数测试"},
            )
        assert response.status_code == 200

        session_id = response.json()["session_id"]
        db = await get_connection()
        try:
            cursor = await db.execute(
                "SELECT target_score, max_iterations FROM optimization_sessions WHERE id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
            assert row["target_score"] == 8.0
            assert row["max_iterations"] == 20
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_start_rejects_empty_prompt(self, client, tmp_db):
        """空提示词应返回 422"""
        response = await client.post(
            "/api/script-optimization/start",
            json={"initial_prompt": ""},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_start_rejects_blank_prompt(self, client, tmp_db):
        """空白提示词应返回 422"""
        response = await client.post(
            "/api/script-optimization/start",
            json={"initial_prompt": "   "},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_start_rejects_invalid_target_score(self, client, tmp_db):
        """无效目标分数应返回 422"""
        response = await client.post(
            "/api/script-optimization/start",
            json={"initial_prompt": "测试", "target_score": -1},
        )
        assert response.status_code == 422

        response = await client.post(
            "/api/script-optimization/start",
            json={"initial_prompt": "测试", "target_score": 11},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_start_rejects_invalid_max_iterations(self, client, tmp_db):
        """无效最大迭代次数应返回 422"""
        response = await client.post(
            "/api/script-optimization/start",
            json={"initial_prompt": "测试", "max_iterations": 0},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_start_rejects_missing_prompt(self, client, tmp_db):
        """缺少提示词应返回 422"""
        response = await client.post(
            "/api/script-optimization/start",
            json={},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Tests: GET /api/script-optimization/{session_id}/status
# ---------------------------------------------------------------------------

class TestGetSessionStatus:
    """GET /status 端点测试"""

    @pytest.mark.asyncio
    async def test_get_status_returns_session_info(self, client, tmp_db):
        """查询存在的会话应返回完整信息"""
        db = await get_connection()
        try:
            await _seed_session(db, "sess-1", "running")
        finally:
            await db.close()

        response = await client.get("/api/script-optimization/sess-1/status")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "sess-1"
        assert data["initial_prompt"] == "测试提示词"
        assert data["target_score"] == 8.0
        assert data["max_iterations"] == 20
        assert data["status"] == "running"

    @pytest.mark.asyncio
    async def test_get_status_not_found(self, client, tmp_db):
        """查询不存在的会话应返回 404"""
        response = await client.get("/api/script-optimization/nonexistent/status")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Tests: GET /api/script-optimization/{session_id}/versions
# ---------------------------------------------------------------------------

class TestGetVersions:
    """GET /versions 端点测试"""

    @pytest.mark.asyncio
    async def test_get_versions_returns_list(self, client, tmp_db):
        """获取版本列表应返回所有版本"""
        db = await get_connection()
        try:
            await _seed_session(db, "sess-v")
            await _seed_version(db, "sess-v", iteration=0, score=6.0)
            await _seed_version(db, "sess-v", iteration=1, score=7.5)
            await _seed_version(db, "sess-v", iteration=2, score=8.5, is_final=True)
        finally:
            await db.close()

        response = await client.get("/api/script-optimization/sess-v/versions")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "sess-v"
        assert data["total"] == 3
        assert len(data["versions"]) == 3
        # Verify ordering by iteration
        iterations = [v["iteration"] for v in data["versions"]]
        assert iterations == [0, 1, 2]

    @pytest.mark.asyncio
    async def test_get_versions_empty(self, client, tmp_db):
        """没有版本时应返回空列表"""
        db = await get_connection()
        try:
            await _seed_session(db, "sess-empty")
        finally:
            await db.close()

        response = await client.get("/api/script-optimization/sess-empty/versions")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["versions"] == []

    @pytest.mark.asyncio
    async def test_get_versions_session_not_found(self, client, tmp_db):
        """会话不存在时应返回 404"""
        response = await client.get("/api/script-optimization/nonexistent/versions")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Tests: GET /api/script-optimization/{session_id}/versions/{iteration}
# ---------------------------------------------------------------------------

class TestGetVersion:
    """GET /versions/{iteration} 端点测试"""

    @pytest.mark.asyncio
    async def test_get_specific_version(self, client, tmp_db):
        """获取特定版本应返回完整信息"""
        db = await get_connection()
        try:
            await _seed_session(db, "sess-sv")
            await _seed_version(db, "sess-sv", iteration=0, score=7.0)
            await _seed_version(db, "sess-sv", iteration=1, score=8.5, is_final=True)
        finally:
            await db.close()

        response = await client.get("/api/script-optimization/sess-sv/versions/1")
        assert response.status_code == 200
        data = response.json()
        assert data["iteration"] == 1
        assert data["session_id"] == "sess-sv"
        assert data["script"] == "剧本内容 v1"
        assert data["is_final"] is True

    @pytest.mark.asyncio
    async def test_get_version_not_found(self, client, tmp_db):
        """版本不存在时应返回 404"""
        db = await get_connection()
        try:
            await _seed_session(db, "sess-nv")
        finally:
            await db.close()

        response = await client.get("/api/script-optimization/sess-nv/versions/99")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_version_session_not_found(self, client, tmp_db):
        """会话不存在时应返回 404"""
        response = await client.get("/api/script-optimization/nonexistent/versions/0")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_version_negative_iteration(self, client, tmp_db):
        """负数迭代次数应返回 422"""
        db = await get_connection()
        try:
            await _seed_session(db, "sess-neg")
        finally:
            await db.close()

        response = await client.get("/api/script-optimization/sess-neg/versions/-1")
        assert response.status_code == 422
