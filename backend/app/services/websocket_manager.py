"""WebSocket 管理器

管理 WebSocket 连接，实时推送迭代进度更新。
需求 5.2: 实时更新迭代次数、当前分数和历史分数曲线
需求 10.4: 使用 WebSocket 实时推送进度更新
"""

import logging
from typing import Dict

from fastapi import WebSocket, WebSocketDisconnect

from app.schemas.script_optimization import IterationProgress

logger = logging.getLogger(__name__)


class WebSocketManager:
    """WebSocket 连接管理器

    维护活跃连接字典，支持按 session_id 管理连接。
    连接断开时不影响主流程。
    """

    def __init__(self) -> None:
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        """建立 WebSocket 连接

        接受连接并将其注册到活跃连接字典中。
        如果该 session_id 已有连接，先关闭旧连接。

        Args:
            session_id: 会话 ID
            websocket: FastAPI WebSocket 实例
        """
        # 如果已有连接，先断开旧连接
        if session_id in self.active_connections:
            await self.disconnect(session_id)

        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket connected: session_id={session_id}")

    async def disconnect(self, session_id: str) -> None:
        """断开 WebSocket 连接

        从活跃连接字典中移除连接并尝试关闭。
        关闭失败时仅记录日志，不抛出异常。

        Args:
            session_id: 会话 ID
        """
        websocket = self.active_connections.pop(session_id, None)
        if websocket is not None:
            try:
                await websocket.close()
            except Exception:
                logger.debug(
                    f"WebSocket already closed: session_id={session_id}"
                )
            logger.info(f"WebSocket disconnected: session_id={session_id}")

    async def send_progress(
        self, session_id: str, progress: IterationProgress
    ) -> None:
        """推送进度更新

        向指定 session_id 的 WebSocket 连接发送进度 JSON 数据。
        连接不存在或发送失败时不影响主流程。

        Args:
            session_id: 会话 ID
            progress: 迭代进度数据
        """
        websocket = self.active_connections.get(session_id)
        if websocket is None:
            logger.debug(
                f"No active WebSocket for session_id={session_id}, "
                "skipping progress push"
            )
            return

        try:
            await websocket.send_json(progress.model_dump(mode="json"))
        except WebSocketDisconnect:
            logger.warning(
                f"WebSocket disconnected during send: session_id={session_id}"
            )
            self.active_connections.pop(session_id, None)
        except Exception as e:
            logger.error(
                f"Failed to send progress via WebSocket: "
                f"session_id={session_id}, error={e}"
            )
            # Remove broken connection
            self.active_connections.pop(session_id, None)
