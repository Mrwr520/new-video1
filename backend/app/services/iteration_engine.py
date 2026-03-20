"""迭代引擎 (Iteration Engine)

协调整个剧本优化流程：生成 → 并行搜索 → 评审 → 循环。
实现迭代终止条件判断和进度回调机制。

需求：1.1, 1.2, 1.3, 1.4, 1.5, 10.1
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, List

from app.config.optimization_config import IterationConfig
from app.schemas.script_optimization import (
    EvaluationResult,
    Hotspot,
    IterationProgress,
    ScriptVersion,
    Technique,
)
from app.services.hotspot_searcher import HotspotSearcher
from app.services.script_evaluator_v2 import ScriptEvaluator
from app.services.script_generator import ScriptGenerator
from app.services.technique_searcher import TechniqueSearcher
from app.services.version_manager import VersionManager

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """优化结果"""

    session_id: str
    final_script: str
    final_score: float
    total_iterations: int
    versions: List[ScriptVersion] = field(default_factory=list)


class IterationEngine:
    """迭代引擎，协调整个剧本优化流程。

    流程：
    1. 生成初始剧本
    2. 循环：评审 → 并行搜索（热点 + 技巧） → 重新生成
    3. 终止条件：分数 >= target_score 或 迭代次数 >= max_iterations
    4. 每个版本通过 VersionManager 保存
    5. 最佳版本标记为 final
    6. 通过 progress_callback 推送实时进度
    """

    def __init__(
        self,
        script_generator: ScriptGenerator,
        script_evaluator: ScriptEvaluator,
        hotspot_searcher: HotspotSearcher,
        technique_searcher: TechniqueSearcher,
        version_manager: VersionManager,
        config: IterationConfig,
    ):
        self._generator = script_generator
        self._evaluator = script_evaluator
        self._hotspot_searcher = hotspot_searcher
        self._technique_searcher = technique_searcher
        self._version_manager = version_manager
        self._config = config

    async def optimize_script(
        self,
        initial_prompt: str,
        session_id: str,
        progress_callback: Callable[[IterationProgress], None],
    ) -> OptimizationResult:
        """执行完整的剧本优化流程。

        Args:
            initial_prompt: 初始剧本提示词
            session_id: 会话 ID
            progress_callback: 进度回调函数

        Returns:
            OptimizationResult: 包含最终剧本、分数和所有版本
        """
        logger.info(
            "Starting optimization for session %s (target_score=%.2f, max_iterations=%d)",
            session_id,
            self._config.target_score,
            self._config.max_iterations,
        )
        start_time = time.monotonic()

        versions = await self._iteration_loop(
            initial_prompt, session_id, progress_callback
        )

        # Find the best version (highest score)
        best_version = max(versions, key=lambda v: v.evaluation.total_score)

        # Mark the best version as final
        await self._version_manager.mark_final_version(
            session_id, best_version.iteration
        )

        # Push completed progress
        progress_callback(
            IterationProgress(
                session_id=session_id,
                current_iteration=len(versions),
                total_iterations=self._config.max_iterations,
                stage="completed",
                current_score=best_version.evaluation.total_score,
                message=f"优化完成，最终分数: {best_version.evaluation.total_score}",
            )
        )

        elapsed = time.monotonic() - start_time
        target_reached = best_version.evaluation.total_score >= self._config.target_score

        # 迭代统计摘要日志（需求 9.4）
        logger.info(
            "Optimization summary for session %s: "
            "total_iterations=%d, final_score=%.2f, elapsed_time=%.2fs, "
            "target_score=%.2f, target_reached=%s",
            session_id,
            len(versions),
            best_version.evaluation.total_score,
            elapsed,
            self._config.target_score,
            target_reached,
        )

        return OptimizationResult(
            session_id=session_id,
            final_script=best_version.script,
            final_score=best_version.evaluation.total_score,
            total_iterations=len(versions),
            versions=versions,
        )

    async def _iteration_loop(
        self,
        prompt: str,
        session_id: str,
        progress_callback: Callable[[IterationProgress], None],
    ) -> List[ScriptVersion]:
        """执行迭代循环。

        Args:
            prompt: 初始提示词
            session_id: 会话 ID
            progress_callback: 进度回调函数

        Returns:
            所有迭代版本列表
        """
        versions: List[ScriptVersion] = []
        current_script: str = ""
        current_evaluation: EvaluationResult | None = None
        hotspots: List[Hotspot] = []
        techniques: List[Technique] = []

        for iteration in range(self._config.max_iterations):
            logger.info(
                "Session %s: starting iteration %d/%d",
                session_id,
                iteration + 1,
                self._config.max_iterations,
            )
            # --- Stage 1: Generate script ---
            progress_callback(
                IterationProgress(
                    session_id=session_id,
                    current_iteration=iteration + 1,
                    total_iterations=self._config.max_iterations,
                    stage="generating",
                    current_score=(
                        current_evaluation.total_score
                        if current_evaluation
                        else None
                    ),
                    message=f"正在生成第 {iteration + 1} 版剧本...",
                )
            )

            if iteration == 0:
                logger.info("Session %s: generating initial script", session_id)
                current_script = await self._generator.generate_initial_script(
                    prompt
                )
            else:
                assert current_evaluation is not None
                logger.info(
                    "Session %s: regenerating script based on previous score %.2f",
                    session_id,
                    current_evaluation.total_score,
                )
                current_script = await self._generator.regenerate_script(
                    current_script, current_evaluation, hotspots, techniques
                )
            logger.debug(
                "Session %s iteration %d: script generated (%d chars)",
                session_id,
                iteration + 1,
                len(current_script),
            )

            # --- Stage 2: Parallel search (hotspots + techniques) ---
            progress_callback(
                IterationProgress(
                    session_id=session_id,
                    current_iteration=iteration + 1,
                    total_iterations=self._config.max_iterations,
                    stage="searching",
                    current_score=(
                        current_evaluation.total_score
                        if current_evaluation
                        else None
                    ),
                    message="正在搜索热点和技巧...",
                )
            )

            hotspots, techniques = await self._parallel_search(
                current_script, prompt
            )
            logger.debug(
                "Session %s iteration %d: search completed (hotspots=%d, techniques=%d)",
                session_id,
                iteration + 1,
                len(hotspots),
                len(techniques),
            )

            # --- Stage 3: Evaluate script ---
            progress_callback(
                IterationProgress(
                    session_id=session_id,
                    current_iteration=iteration + 1,
                    total_iterations=self._config.max_iterations,
                    stage="evaluating",
                    current_score=(
                        current_evaluation.total_score
                        if current_evaluation
                        else None
                    ),
                    message=f"正在评审第 {iteration + 1} 版剧本...",
                )
            )

            current_evaluation = await self._evaluator.evaluate_script(
                current_script, hotspots, techniques
            )
            logger.debug(
                "Session %s iteration %d: evaluation completed "
                "(total=%.2f, content=%.2f, structure=%.2f, creativity=%.2f, "
                "hotspot=%.2f, technique=%.2f)",
                session_id,
                iteration + 1,
                current_evaluation.total_score,
                current_evaluation.dimension_scores.content_quality,
                current_evaluation.dimension_scores.structure,
                current_evaluation.dimension_scores.creativity,
                current_evaluation.dimension_scores.hotspot_relevance,
                current_evaluation.dimension_scores.technique_application,
            )

            # --- Save version ---
            version = await self._version_manager.save_version(
                session_id=session_id,
                iteration=iteration,
                script=current_script,
                evaluation=current_evaluation,
                hotspots=hotspots,
                techniques=techniques,
            )
            versions.append(version)

            logger.info(
                "Session %s iteration %d: score %.2f (target %.2f)",
                session_id,
                iteration + 1,
                current_evaluation.total_score,
                self._config.target_score,
            )

            # --- Check termination: score meets target (需求 1.4) ---
            if current_evaluation.total_score >= self._config.target_score:
                logger.info(
                    "Session %s: target score reached at iteration %d",
                    session_id,
                    iteration + 1,
                )
                break

        return versions

    async def _parallel_search(
        self,
        script: str,
        topic: str,
    ) -> tuple[List[Hotspot], List[Technique]]:
        """并行执行热点搜索和技巧搜索（需求 10.1）。

        根据配置决定是否启用各搜索以及是否并行执行。

        Args:
            script: 当前剧本内容
            topic: 剧本主题

        Returns:
            (hotspots, techniques) 元组
        """
        hotspot_coro = self._search_hotspots(script, topic)
        technique_coro = self._search_techniques(script)

        if self._config.parallel_search:
            results = await asyncio.gather(
                hotspot_coro, technique_coro, return_exceptions=True
            )
            hotspots = results[0] if not isinstance(results[0], Exception) else []
            techniques = results[1] if not isinstance(results[1], Exception) else []
        else:
            hotspots = await hotspot_coro
            techniques = await technique_coro

        return hotspots, techniques

    async def _search_hotspots(
        self, script: str, topic: str
    ) -> List[Hotspot]:
        """搜索热点，未启用时返回空列表。"""
        if not self._config.enable_hotspot_search:
            return []
        try:
            return await self._hotspot_searcher.search_hotspots(script, topic)
        except Exception as e:
            logger.error("Hotspot search error: %s", e)
            return []

    async def _search_techniques(self, script: str) -> List[Technique]:
        """搜索技巧，未启用时返回空列表。"""
        if not self._config.enable_technique_search:
            return []
        try:
            return await self._technique_searcher.search_techniques(
                script, "通用", []
            )
        except Exception as e:
            logger.error("Technique search error: %s", e)
            return []
