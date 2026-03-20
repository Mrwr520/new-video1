"""错误处理器 (Error Handler)

集中处理系统中的各类错误：搜索错误、生成错误和关键错误。
实现错误日志记录和降级策略。

需求 9.1: 任何组件发生错误时记录详细的错误日志
需求 9.2: 迭代过程中发生错误时尝试恢复或优雅降级
需求 9.3: 关键错误发生时通知用户并提供错误信息
"""

import asyncio
import logging
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class GenerationError(Exception):
    """剧本生成失败异常（重试耗尽后抛出）"""

    def __init__(self, message: str, retry_count: int = 0):
        self.retry_count = retry_count
        super().__init__(message)


class CriticalError(Exception):
    """关键错误异常"""

    def __init__(self, message: str, session_id: str, original_error: Exception):
        self.session_id = session_id
        self.original_error = original_error
        super().__init__(message)


class ErrorHandler:
    """错误处理器

    提供静态方法处理三类错误：
    - 搜索错误：记录日志，返回空列表或默认数据，不中断主流程
    - 生成错误：使用指数退避重试，耗尽后抛出 GenerationError
    - 关键错误：记录详细信息，通知用户，抛出 CriticalError
    """

    # 存储错误状态，供外部查询（如通知用户）
    _error_states: Dict[str, List[Dict[str, Any]]] = {}

    @staticmethod
    async def handle_search_error(
        error: Exception,
        search_type: str,
    ) -> List:
        """处理搜索错误

        记录错误日志，根据搜索类型返回空列表或默认数据。
        不中断主流程（需求 9.2）。

        Args:
            error: 捕获的异常
            search_type: 搜索类型（如 "hotspot", "technique"）

        Returns:
            空列表（降级结果）
        """
        logger.error(
            "Search error [type=%s]: %s",
            search_type,
            error,
            exc_info=True,
        )
        # 降级策略：返回空列表，让调用方决定是否使用默认数据
        return []

    @staticmethod
    async def handle_generation_error(
        error: Exception,
        retry_count: int,
        max_retries: int,
    ) -> Optional[str]:
        """处理生成错误

        使用指数退避重试。未达到最大重试次数时返回 None（触发重试），
        达到最大重试次数后抛出 GenerationError。

        Args:
            error: 捕获的异常
            retry_count: 当前重试次数（从 0 开始）
            max_retries: 最大重试次数

        Returns:
            None 表示应该重试

        Raises:
            GenerationError: 重试次数耗尽
        """
        logger.error(
            "Generation error [retry=%d/%d]: %s",
            retry_count,
            max_retries,
            error,
            exc_info=True,
        )

        if retry_count < max_retries:
            delay = 2 ** retry_count
            logger.info(
                "Retrying generation in %.1f seconds (attempt %d/%d)",
                delay,
                retry_count + 1,
                max_retries,
            )
            await asyncio.sleep(delay)
            return None  # 触发重试

        raise GenerationError(
            f"Generation failed after {max_retries} retries: {error}",
            retry_count=retry_count,
        )

    @staticmethod
    async def handle_critical_error(
        error: Exception,
        session_id: str,
    ) -> None:
        """处理关键错误

        记录详细错误信息（含堆栈跟踪），保存错误状态，
        然后抛出 CriticalError 通知调用方终止流程。

        Args:
            error: 捕获的异常
            session_id: 会话 ID

        Raises:
            CriticalError: 始终抛出，通知调用方终止流程
        """
        error_detail = {
            "session_id": session_id,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.critical(
            "Critical error in session %s: [%s] %s",
            session_id,
            error_detail["error_type"],
            error_detail["error_message"],
            exc_info=True,
        )

        # 保存错误状态以便外部查询
        if session_id not in ErrorHandler._error_states:
            ErrorHandler._error_states[session_id] = []
        ErrorHandler._error_states[session_id].append(error_detail)

        raise CriticalError(
            f"Critical error in session {session_id}: {error}",
            session_id=session_id,
            original_error=error,
        )

    @staticmethod
    def get_error_states(session_id: str) -> List[Dict[str, Any]]:
        """获取指定会话的错误状态记录

        Args:
            session_id: 会话 ID

        Returns:
            错误状态列表
        """
        return list(ErrorHandler._error_states.get(session_id, []))

    @staticmethod
    def clear_error_states(session_id: str) -> None:
        """清除指定会话的错误状态记录

        Args:
            session_id: 会话 ID
        """
        ErrorHandler._error_states.pop(session_id, None)
