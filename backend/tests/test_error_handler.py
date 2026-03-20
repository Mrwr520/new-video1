"""错误处理器单元测试

测试 ErrorHandler 的搜索错误处理、生成错误处理、关键错误处理、
错误日志记录和降级策略。

需求 9.1, 9.2, 9.3
"""

import logging
from unittest.mock import patch

import pytest

from app.services.error_handler import (
    CriticalError,
    ErrorHandler,
    GenerationError,
)


@pytest.fixture(autouse=True)
def _clear_error_states():
    """每个测试前后清理全局错误状态"""
    ErrorHandler._error_states.clear()
    yield
    ErrorHandler._error_states.clear()


class TestHandleSearchError:
    @pytest.mark.asyncio
    async def test_returns_empty_list_for_hotspot(self):
        result = await ErrorHandler.handle_search_error(
            RuntimeError("API timeout"), "hotspot"
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_technique(self):
        result = await ErrorHandler.handle_search_error(
            ConnectionError("network down"), "technique"
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_unknown_type(self):
        result = await ErrorHandler.handle_search_error(
            ValueError("bad data"), "unknown_type"
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_logs_error(self, caplog):
        with caplog.at_level(logging.ERROR):
            await ErrorHandler.handle_search_error(
                RuntimeError("search failed"), "hotspot"
            )
        assert "search failed" in caplog.text
        assert "hotspot" in caplog.text

    @pytest.mark.asyncio
    async def test_does_not_raise(self):
        """搜索错误不应中断主流程"""
        # Should complete without raising
        result = await ErrorHandler.handle_search_error(
            Exception("any error"), "hotspot"
        )
        assert isinstance(result, list)


class TestHandleGenerationError:
    @pytest.mark.asyncio
    async def test_returns_none_when_retries_remaining(self):
        result = await ErrorHandler.handle_generation_error(
            RuntimeError("LLM timeout"), retry_count=0, max_retries=3
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_intermediate_retry(self):
        result = await ErrorHandler.handle_generation_error(
            RuntimeError("LLM error"), retry_count=1, max_retries=3
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_raises_generation_error_when_retries_exhausted(self):
        with pytest.raises(GenerationError, match="failed after 3 retries"):
            await ErrorHandler.handle_generation_error(
                RuntimeError("LLM down"), retry_count=3, max_retries=3
            )

    @pytest.mark.asyncio
    async def test_raises_immediately_when_max_retries_zero(self):
        with pytest.raises(GenerationError, match="failed after 0 retries"):
            await ErrorHandler.handle_generation_error(
                RuntimeError("fail"), retry_count=0, max_retries=0
            )

    @pytest.mark.asyncio
    async def test_generation_error_contains_retry_count(self):
        with pytest.raises(GenerationError) as exc_info:
            await ErrorHandler.handle_generation_error(
                RuntimeError("fail"), retry_count=2, max_retries=2
            )
        assert exc_info.value.retry_count == 2

    @pytest.mark.asyncio
    async def test_logs_error(self, caplog):
        with caplog.at_level(logging.ERROR):
            await ErrorHandler.handle_generation_error(
                RuntimeError("LLM timeout"), retry_count=0, max_retries=3
            )
        assert "LLM timeout" in caplog.text
        assert "retry=0/3" in caplog.text

    @pytest.mark.asyncio
    async def test_exponential_backoff_delay(self):
        """验证指数退避：retry_count=0 → sleep(1), retry_count=1 → sleep(2)"""
        with patch("app.services.error_handler.asyncio.sleep") as mock_sleep:
            mock_sleep.return_value = None
            await ErrorHandler.handle_generation_error(
                RuntimeError("err"), retry_count=0, max_retries=3
            )
            mock_sleep.assert_called_once_with(1)  # 2^0 = 1

        with patch("app.services.error_handler.asyncio.sleep") as mock_sleep:
            mock_sleep.return_value = None
            await ErrorHandler.handle_generation_error(
                RuntimeError("err"), retry_count=2, max_retries=3
            )
            mock_sleep.assert_called_once_with(4)  # 2^2 = 4


class TestHandleCriticalError:
    @pytest.mark.asyncio
    async def test_raises_critical_error(self):
        with pytest.raises(CriticalError) as exc_info:
            await ErrorHandler.handle_critical_error(
                RuntimeError("DB connection lost"), "session-123"
            )
        assert exc_info.value.session_id == "session-123"
        assert isinstance(exc_info.value.original_error, RuntimeError)

    @pytest.mark.asyncio
    async def test_logs_critical(self, caplog):
        with caplog.at_level(logging.CRITICAL):
            with pytest.raises(CriticalError):
                await ErrorHandler.handle_critical_error(
                    RuntimeError("DB down"), "session-abc"
                )
        assert "session-abc" in caplog.text
        assert "DB down" in caplog.text

    @pytest.mark.asyncio
    async def test_saves_error_state(self):
        with pytest.raises(CriticalError):
            await ErrorHandler.handle_critical_error(
                ValueError("config corrupted"), "session-xyz"
            )

        states = ErrorHandler.get_error_states("session-xyz")
        assert len(states) == 1
        assert states[0]["session_id"] == "session-xyz"
        assert states[0]["error_type"] == "ValueError"
        assert "config corrupted" in states[0]["error_message"]
        assert states[0]["timestamp"] is not None

    @pytest.mark.asyncio
    async def test_accumulates_multiple_errors(self):
        for i in range(3):
            with pytest.raises(CriticalError):
                await ErrorHandler.handle_critical_error(
                    RuntimeError(f"error {i}"), "session-multi"
                )

        states = ErrorHandler.get_error_states("session-multi")
        assert len(states) == 3

    @pytest.mark.asyncio
    async def test_error_state_includes_traceback(self):
        with pytest.raises(CriticalError):
            await ErrorHandler.handle_critical_error(
                RuntimeError("traceback test"), "session-tb"
            )

        states = ErrorHandler.get_error_states("session-tb")
        assert "traceback" in states[0]


class TestErrorStates:
    def test_get_error_states_empty_session(self):
        states = ErrorHandler.get_error_states("nonexistent")
        assert states == []

    @pytest.mark.asyncio
    async def test_clear_error_states(self):
        with pytest.raises(CriticalError):
            await ErrorHandler.handle_critical_error(
                RuntimeError("err"), "session-clear"
            )
        assert len(ErrorHandler.get_error_states("session-clear")) == 1

        ErrorHandler.clear_error_states("session-clear")
        assert ErrorHandler.get_error_states("session-clear") == []

    def test_clear_nonexistent_session_is_noop(self):
        # Should not raise
        ErrorHandler.clear_error_states("nonexistent")

    @pytest.mark.asyncio
    async def test_states_isolated_between_sessions(self):
        with pytest.raises(CriticalError):
            await ErrorHandler.handle_critical_error(
                RuntimeError("err1"), "session-a"
            )
        with pytest.raises(CriticalError):
            await ErrorHandler.handle_critical_error(
                RuntimeError("err2"), "session-b"
            )

        assert len(ErrorHandler.get_error_states("session-a")) == 1
        assert len(ErrorHandler.get_error_states("session-b")) == 1
        assert "err1" in ErrorHandler.get_error_states("session-a")[0]["error_message"]
        assert "err2" in ErrorHandler.get_error_states("session-b")[0]["error_message"]


class TestCustomExceptions:
    def test_generation_error_attributes(self):
        err = GenerationError("test message", retry_count=5)
        assert str(err) == "test message"
        assert err.retry_count == 5

    def test_generation_error_default_retry_count(self):
        err = GenerationError("test")
        assert err.retry_count == 0

    def test_critical_error_attributes(self):
        original = RuntimeError("original")
        err = CriticalError("critical msg", session_id="s1", original_error=original)
        assert str(err) == "critical msg"
        assert err.session_id == "s1"
        assert err.original_error is original
