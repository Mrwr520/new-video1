"""WebSocket 管理器单元测试

测试 WebSocketManager 的连接管理、断开连接、进度推送和错误处理。
需求 5.2, 10.4
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.script_optimization import IterationProgress
from app.services.websocket_manager import WebSocketManager


def _make_progress(session_id: str = "s1", **kwargs) -> IterationProgress:
    defaults = dict(
        session_id=session_id,
        current_iteration=1,
        total_iterations=5,
        stage="generating",
        current_score=None,
        message="生成中",
    )
    defaults.update(kwargs)
    return IterationProgress(**defaults)


def _make_websocket(accept_ok=True, send_ok=True, close_ok=True):
    """Create a mock WebSocket with configurable behavior."""
    ws = AsyncMock()
    if not accept_ok:
        ws.accept.side_effect = RuntimeError("accept failed")
    if not send_ok:
        ws.send_json.side_effect = RuntimeError("send failed")
    if not close_ok:
        ws.close.side_effect = RuntimeError("close failed")
    return ws


class TestConnect:
    @pytest.mark.asyncio
    async def test_accepts_and_registers_connection(self):
        manager = WebSocketManager()
        ws = _make_websocket()

        await manager.connect("s1", ws)

        ws.accept.assert_called_once()
        assert "s1" in manager.active_connections
        assert manager.active_connections["s1"] is ws

    @pytest.mark.asyncio
    async def test_replaces_existing_connection(self):
        manager = WebSocketManager()
        ws_old = _make_websocket()
        ws_new = _make_websocket()

        await manager.connect("s1", ws_old)
        await manager.connect("s1", ws_new)

        ws_old.close.assert_called_once()
        assert manager.active_connections["s1"] is ws_new

    @pytest.mark.asyncio
    async def test_multiple_sessions(self):
        manager = WebSocketManager()
        ws1 = _make_websocket()
        ws2 = _make_websocket()

        await manager.connect("s1", ws1)
        await manager.connect("s2", ws2)

        assert len(manager.active_connections) == 2
        assert manager.active_connections["s1"] is ws1
        assert manager.active_connections["s2"] is ws2


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_removes_and_closes_connection(self):
        manager = WebSocketManager()
        ws = _make_websocket()
        await manager.connect("s1", ws)

        await manager.disconnect("s1")

        ws.close.assert_called_once()
        assert "s1" not in manager.active_connections

    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_session_is_noop(self):
        manager = WebSocketManager()
        # Should not raise
        await manager.disconnect("nonexistent")
        assert len(manager.active_connections) == 0

    @pytest.mark.asyncio
    async def test_disconnect_handles_close_error(self):
        manager = WebSocketManager()
        ws = _make_websocket(close_ok=False)
        await manager.connect("s1", ws)

        # Should not raise even if close fails
        await manager.disconnect("s1")

        assert "s1" not in manager.active_connections


class TestSendProgress:
    @pytest.mark.asyncio
    async def test_sends_json_to_connected_client(self):
        manager = WebSocketManager()
        ws = _make_websocket()
        await manager.connect("s1", ws)
        progress = _make_progress("s1")

        await manager.send_progress("s1", progress)

        ws.send_json.assert_called_once()
        sent_data = ws.send_json.call_args[0][0]
        assert sent_data["session_id"] == "s1"
        assert sent_data["stage"] == "generating"
        assert sent_data["current_iteration"] == 1

    @pytest.mark.asyncio
    async def test_skips_when_no_connection(self):
        manager = WebSocketManager()
        progress = _make_progress("s1")

        # Should not raise
        await manager.send_progress("s1", progress)

    @pytest.mark.asyncio
    async def test_removes_connection_on_send_error(self):
        manager = WebSocketManager()
        ws = _make_websocket(send_ok=False)
        await manager.connect("s1", ws)
        progress = _make_progress("s1")

        # Should not raise
        await manager.send_progress("s1", progress)

        # Broken connection should be removed
        assert "s1" not in manager.active_connections

    @pytest.mark.asyncio
    async def test_send_does_not_affect_other_sessions(self):
        manager = WebSocketManager()
        ws1 = _make_websocket(send_ok=False)
        ws2 = _make_websocket()
        await manager.connect("s1", ws1)
        await manager.connect("s2", ws2)

        # s1 fails, s2 should be unaffected
        await manager.send_progress("s1", _make_progress("s1"))
        await manager.send_progress("s2", _make_progress("s2"))

        assert "s1" not in manager.active_connections
        assert "s2" in manager.active_connections
        ws2.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_sends_all_progress_fields(self):
        manager = WebSocketManager()
        ws = _make_websocket()
        await manager.connect("s1", ws)
        progress = _make_progress(
            "s1",
            current_iteration=3,
            total_iterations=10,
            stage="evaluating",
            current_score=7.5,
            message="评审中",
            data={"scores": [5.0, 6.0, 7.5]},
        )

        await manager.send_progress("s1", progress)

        sent_data = ws.send_json.call_args[0][0]
        assert sent_data["current_iteration"] == 3
        assert sent_data["total_iterations"] == 10
        assert sent_data["stage"] == "evaluating"
        assert sent_data["current_score"] == 7.5
        assert sent_data["message"] == "评审中"
        assert sent_data["data"] == {"scores": [5.0, 6.0, 7.5]}


class TestActiveConnections:
    @pytest.mark.asyncio
    async def test_starts_empty(self):
        manager = WebSocketManager()
        assert manager.active_connections == {}

    @pytest.mark.asyncio
    async def test_tracks_connection_count(self):
        manager = WebSocketManager()
        for i in range(3):
            ws = _make_websocket()
            await manager.connect(f"s{i}", ws)

        assert len(manager.active_connections) == 3

        await manager.disconnect("s1")
        assert len(manager.active_connections) == 2
