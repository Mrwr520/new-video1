"""版本管理器 - 管理剧本版本历史

实现剧本版本的保存、查询和标记最终版本功能。
使用 aiosqlite 直接操作 SQLite 数据库。

需求：6.1, 6.2, 6.3, 6.4
"""

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

import aiosqlite

from app.schemas.script_optimization import (
    DimensionScores,
    EvaluationResult,
    Hotspot,
    ScriptVersion,
    Technique,
)

logger = logging.getLogger(__name__)


class VersionManager:
    """剧本版本管理器，负责版本的持久化和查询。"""

    def __init__(self, db: aiosqlite.Connection):
        """初始化版本管理器。

        Args:
            db: aiosqlite 数据库连接
        """
        self.db = db

    async def save_version(
        self,
        session_id: str,
        iteration: int,
        script: str,
        evaluation: EvaluationResult,
        hotspots: List[Hotspot],
        techniques: List[Technique],
    ) -> ScriptVersion:
        """保存剧本版本到数据库。

        Args:
            session_id: 会话 ID
            iteration: 迭代次数
            script: 剧本内容
            evaluation: 评审结果
            hotspots: 热点列表
            techniques: 技巧列表

        Returns:
            ScriptVersion: 保存的版本对象
        """
        now = datetime.now(timezone.utc)
        dimension_scores_json = json.dumps(
            evaluation.dimension_scores.model_dump()
        )
        suggestions_json = json.dumps(evaluation.suggestions)
        hotspots_json = json.dumps(
            [h.model_dump(mode="json") for h in hotspots]
        )
        techniques_json = json.dumps(
            [t.model_dump(mode="json") for t in techniques]
        )

        await self.db.execute(
            """
            INSERT INTO script_versions
                (session_id, iteration, script, total_score,
                 dimension_scores, suggestions, hotspots, techniques,
                 is_final, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                iteration,
                script,
                evaluation.total_score,
                dimension_scores_json,
                suggestions_json,
                hotspots_json,
                techniques_json,
                False,
                now.isoformat(),
            ),
        )
        await self.db.commit()

        version = ScriptVersion(
            session_id=session_id,
            iteration=iteration,
            script=script,
            evaluation=evaluation,
            hotspots=hotspots,
            techniques=techniques,
            timestamp=now,
            is_final=False,
        )
        logger.info(
            "Saved version %d for session %s (score: %.2f)",
            iteration,
            session_id,
            evaluation.total_score,
        )
        return version

    async def get_versions(self, session_id: str) -> List[ScriptVersion]:
        """查询会话的所有版本，按迭代次数排序。

        Args:
            session_id: 会话 ID

        Returns:
            List[ScriptVersion]: 版本列表
        """
        cursor = await self.db.execute(
            """
            SELECT session_id, iteration, script, total_score,
                   dimension_scores, suggestions, hotspots, techniques,
                   is_final, created_at
            FROM script_versions
            WHERE session_id = ?
            ORDER BY iteration ASC
            """,
            (session_id,),
        )
        rows = await cursor.fetchall()
        versions = [self._row_to_version(row) for row in rows]
        logger.info(
            "Retrieved %d versions for session %s",
            len(versions),
            session_id,
        )
        return versions

    async def get_version(
        self, session_id: str, iteration: int
    ) -> Optional[ScriptVersion]:
        """查询特定版本。

        Args:
            session_id: 会话 ID
            iteration: 迭代次数

        Returns:
            Optional[ScriptVersion]: 版本对象，不存在时返回 None
        """
        cursor = await self.db.execute(
            """
            SELECT session_id, iteration, script, total_score,
                   dimension_scores, suggestions, hotspots, techniques,
                   is_final, created_at
            FROM script_versions
            WHERE session_id = ? AND iteration = ?
            """,
            (session_id, iteration),
        )
        row = await cursor.fetchone()
        if row is None:
            logger.debug(
                "Version not found: session=%s, iteration=%d",
                session_id,
                iteration,
            )
            return None
        logger.debug(
            "Retrieved version: session=%s, iteration=%d",
            session_id,
            iteration,
        )
        return self._row_to_version(row)

    async def mark_final_version(
        self, session_id: str, iteration: int
    ) -> None:
        """标记最终版本。先将该会话所有版本的 is_final 设为 False，
        再将指定版本设为 True。

        Args:
            session_id: 会话 ID
            iteration: 要标记为最终版本的迭代次数
        """
        # 先清除该会话所有 is_final 标记
        await self.db.execute(
            "UPDATE script_versions SET is_final = FALSE WHERE session_id = ?",
            (session_id,),
        )
        # 标记指定版本
        await self.db.execute(
            """
            UPDATE script_versions
            SET is_final = TRUE
            WHERE session_id = ? AND iteration = ?
            """,
            (session_id, iteration),
        )
        await self.db.commit()
        logger.info(
            "Marked iteration %d as final for session %s",
            iteration,
            session_id,
        )

    @staticmethod
    def _row_to_version(row: aiosqlite.Row) -> ScriptVersion:
        """将数据库行转换为 ScriptVersion 对象。"""
        dimension_scores = DimensionScores(**json.loads(row["dimension_scores"]))
        suggestions = json.loads(row["suggestions"])
        hotspots_data = json.loads(row["hotspots"]) if row["hotspots"] else []
        techniques_data = json.loads(row["techniques"]) if row["techniques"] else []

        evaluation = EvaluationResult(
            total_score=row["total_score"],
            dimension_scores=dimension_scores,
            suggestions=suggestions,
        )

        return ScriptVersion(
            session_id=row["session_id"],
            iteration=row["iteration"],
            script=row["script"],
            evaluation=evaluation,
            hotspots=[Hotspot(**h) for h in hotspots_data],
            techniques=[Technique(**t) for t in techniques_data],
            timestamp=datetime.fromisoformat(row["created_at"]),
            is_final=bool(row["is_final"]),
        )
