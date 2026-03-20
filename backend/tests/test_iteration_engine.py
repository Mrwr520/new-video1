"""迭代引擎单元测试

测试 IterationEngine 的完整优化流程、迭代循环、并行搜索、
终止条件判断和进度回调机制。所有依赖使用 mock。
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from app.config.optimization_config import IterationConfig
from app.schemas.script_optimization import (
    DimensionScores,
    EvaluationResult,
    Hotspot,
    IterationProgress,
    ScriptVersion,
    Technique,
)
from app.services.iteration_engine import IterationEngine, OptimizationResult


# --- Helpers ---


def _make_evaluation(score: float) -> EvaluationResult:
    """Create an EvaluationResult with the given total_score."""
    return EvaluationResult(
        total_score=score,
        dimension_scores=DimensionScores(
            content_quality=score,
            structure=score,
            creativity=score,
            hotspot_relevance=score,
            technique_application=score,
        ),
        suggestions=["改进建议"],
    )


def _make_version(
    session_id: str, iteration: int, score: float
) -> ScriptVersion:
    return ScriptVersion(
        session_id=session_id,
        iteration=iteration,
        script=f"剧本 v{iteration}",
        evaluation=_make_evaluation(score),
    )


# --- Fixtures ---


@pytest.fixture
def mock_generator():
    gen = MagicMock()
    gen.generate_initial_script = AsyncMock(return_value="初始剧本内容")
    gen.regenerate_script = AsyncMock(return_value="优化后的剧本内容")
    return gen


@pytest.fixture
def mock_evaluator():
    ev = MagicMock()
    ev.evaluate_script = AsyncMock(return_value=_make_evaluation(9.0))
    return ev


@pytest.fixture
def mock_hotspot_searcher():
    hs = MagicMock()
    hs.search_hotspots = AsyncMock(return_value=[])
    return hs


@pytest.fixture
def mock_technique_searcher():
    ts = MagicMock()
    ts.search_techniques = AsyncMock(return_value=[])
    return ts


@pytest.fixture
def mock_version_manager():
    vm = MagicMock()
    vm.save_version = AsyncMock(
        side_effect=lambda **kwargs: _make_version(
            kwargs["session_id"],
            kwargs["iteration"],
            kwargs["evaluation"].total_score,
        )
    )
    vm.mark_final_version = AsyncMock()
    return vm


@pytest.fixture
def default_config():
    return IterationConfig(target_score=8.0, max_iterations=5)


@pytest.fixture
def progress_callback():
    return MagicMock()


@pytest.fixture
def engine(
    mock_generator,
    mock_evaluator,
    mock_hotspot_searcher,
    mock_technique_searcher,
    mock_version_manager,
    default_config,
):
    return IterationEngine(
        script_generator=mock_generator,
        script_evaluator=mock_evaluator,
        hotspot_searcher=mock_hotspot_searcher,
        technique_searcher=mock_technique_searcher,
        version_manager=mock_version_manager,
        config=default_config,
    )


# --- optimize_script ---


class TestOptimizeScript:
    """需求 1.1: 生成初始剧本并开始迭代循环"""

    @pytest.mark.asyncio
    async def test_returns_optimization_result(
        self, engine, progress_callback
    ):
        result = await engine.optimize_script(
            "测试提示词", "session-1", progress_callback
        )
        assert isinstance(result, OptimizationResult)
        assert result.session_id == "session-1"
        assert result.final_score == 9.0
        assert result.total_iterations == 1
        assert len(result.versions) == 1

    @pytest.mark.asyncio
    async def test_marks_best_version_as_final(
        self, engine, mock_version_manager, progress_callback
    ):
        await engine.optimize_script("测试", "session-1", progress_callback)
        mock_version_manager.mark_final_version.assert_called_once_with(
            "session-1", 0
        )

    @pytest.mark.asyncio
    async def test_pushes_completed_progress(
        self, engine, progress_callback
    ):
        await engine.optimize_script("测试", "session-1", progress_callback)
        # Last call should be "completed" stage
        last_call = progress_callback.call_args_list[-1]
        progress: IterationProgress = last_call[0][0]
        assert progress.stage == "completed"
        assert progress.current_score == 9.0

    @pytest.mark.asyncio
    async def test_generates_initial_script(
        self, engine, mock_generator, progress_callback
    ):
        """需求 1.1: 生成初始剧本"""
        await engine.optimize_script("我的提示词", "s1", progress_callback)
        mock_generator.generate_initial_script.assert_called_once_with(
            "我的提示词"
        )


# --- Termination conditions ---


class TestTerminationConditions:
    @pytest.mark.asyncio
    async def test_stops_when_score_meets_target(
        self, engine, mock_evaluator, progress_callback
    ):
        """需求 1.4: 分数 >= target_score 时终止"""
        mock_evaluator.evaluate_script = AsyncMock(
            return_value=_make_evaluation(8.5)
        )
        result = await engine.optimize_script("测试", "s1", progress_callback)
        assert result.total_iterations == 1
        assert result.final_score == 8.5

    @pytest.mark.asyncio
    async def test_stops_when_score_equals_target(
        self, engine, mock_evaluator, progress_callback
    ):
        """需求 1.4: 分数 == target_score 时终止"""
        mock_evaluator.evaluate_script = AsyncMock(
            return_value=_make_evaluation(8.0)
        )
        result = await engine.optimize_script("测试", "s1", progress_callback)
        assert result.total_iterations == 1

    @pytest.mark.asyncio
    async def test_continues_when_score_below_target(
        self,
        mock_generator,
        mock_evaluator,
        mock_hotspot_searcher,
        mock_technique_searcher,
        mock_version_manager,
        progress_callback,
    ):
        """需求 1.3: 分数 < target_score 时继续"""
        # Score below target for 3 iterations, then meets target
        mock_evaluator.evaluate_script = AsyncMock(
            side_effect=[
                _make_evaluation(5.0),
                _make_evaluation(6.0),
                _make_evaluation(8.5),
            ]
        )
        config = IterationConfig(target_score=8.0, max_iterations=10)
        engine = IterationEngine(
            script_generator=mock_generator,
            script_evaluator=mock_evaluator,
            hotspot_searcher=mock_hotspot_searcher,
            technique_searcher=mock_technique_searcher,
            version_manager=mock_version_manager,
            config=config,
        )
        result = await engine.optimize_script("测试", "s1", progress_callback)
        assert result.total_iterations == 3
        assert result.final_score == 8.5

    @pytest.mark.asyncio
    async def test_stops_at_max_iterations(
        self,
        mock_generator,
        mock_evaluator,
        mock_hotspot_searcher,
        mock_technique_searcher,
        mock_version_manager,
        progress_callback,
    ):
        """需求 1.5: 迭代次数超过最大限制时终止并返回最佳剧本"""
        mock_evaluator.evaluate_script = AsyncMock(
            return_value=_make_evaluation(5.0)
        )
        config = IterationConfig(target_score=8.0, max_iterations=3)
        engine = IterationEngine(
            script_generator=mock_generator,
            script_evaluator=mock_evaluator,
            hotspot_searcher=mock_hotspot_searcher,
            technique_searcher=mock_technique_searcher,
            version_manager=mock_version_manager,
            config=config,
        )
        result = await engine.optimize_script("测试", "s1", progress_callback)
        assert result.total_iterations == 3
        assert result.final_score == 5.0

    @pytest.mark.asyncio
    async def test_returns_best_version_when_max_reached(
        self,
        mock_generator,
        mock_evaluator,
        mock_hotspot_searcher,
        mock_technique_searcher,
        mock_version_manager,
        progress_callback,
    ):
        """需求 1.5: 返回最佳剧本（最高分版本）"""
        mock_evaluator.evaluate_script = AsyncMock(
            side_effect=[
                _make_evaluation(5.0),
                _make_evaluation(7.0),
                _make_evaluation(6.0),
            ]
        )
        config = IterationConfig(target_score=8.0, max_iterations=3)
        engine = IterationEngine(
            script_generator=mock_generator,
            script_evaluator=mock_evaluator,
            hotspot_searcher=mock_hotspot_searcher,
            technique_searcher=mock_technique_searcher,
            version_manager=mock_version_manager,
            config=config,
        )
        result = await engine.optimize_script("测试", "s1", progress_callback)
        # Best score is 7.0 at iteration 1
        assert result.final_score == 7.0
        mock_version_manager.mark_final_version.assert_called_once_with(
            "s1", 1
        )


# --- Iteration loop ---


class TestIterationLoop:
    @pytest.mark.asyncio
    async def test_first_iteration_uses_generate_initial(
        self, engine, mock_generator, progress_callback
    ):
        await engine.optimize_script("提示词", "s1", progress_callback)
        mock_generator.generate_initial_script.assert_called_once()
        # Should not call regenerate on first iteration when score meets target
        mock_generator.regenerate_script.assert_not_called()

    @pytest.mark.asyncio
    async def test_subsequent_iterations_use_regenerate(
        self,
        mock_generator,
        mock_evaluator,
        mock_hotspot_searcher,
        mock_technique_searcher,
        mock_version_manager,
        progress_callback,
    ):
        mock_evaluator.evaluate_script = AsyncMock(
            side_effect=[
                _make_evaluation(5.0),
                _make_evaluation(9.0),
            ]
        )
        config = IterationConfig(target_score=8.0, max_iterations=5)
        engine = IterationEngine(
            script_generator=mock_generator,
            script_evaluator=mock_evaluator,
            hotspot_searcher=mock_hotspot_searcher,
            technique_searcher=mock_technique_searcher,
            version_manager=mock_version_manager,
            config=config,
        )
        await engine.optimize_script("提示词", "s1", progress_callback)
        mock_generator.generate_initial_script.assert_called_once()
        mock_generator.regenerate_script.assert_called_once()

    @pytest.mark.asyncio
    async def test_saves_each_version(
        self,
        mock_generator,
        mock_evaluator,
        mock_hotspot_searcher,
        mock_technique_searcher,
        mock_version_manager,
        progress_callback,
    ):
        """需求 1.2: 每次迭代保存版本"""
        mock_evaluator.evaluate_script = AsyncMock(
            side_effect=[
                _make_evaluation(5.0),
                _make_evaluation(6.0),
                _make_evaluation(9.0),
            ]
        )
        config = IterationConfig(target_score=8.0, max_iterations=5)
        engine = IterationEngine(
            script_generator=mock_generator,
            script_evaluator=mock_evaluator,
            hotspot_searcher=mock_hotspot_searcher,
            technique_searcher=mock_technique_searcher,
            version_manager=mock_version_manager,
            config=config,
        )
        result = await engine.optimize_script("测试", "s1", progress_callback)
        assert mock_version_manager.save_version.call_count == 3
        assert result.total_iterations == 3


# --- Parallel search ---


class TestParallelSearch:
    @pytest.mark.asyncio
    async def test_parallel_search_calls_both_searchers(
        self,
        engine,
        mock_hotspot_searcher,
        mock_technique_searcher,
        progress_callback,
    ):
        """需求 10.1: 并行调用热点搜索和技巧搜索"""
        await engine.optimize_script("测试", "s1", progress_callback)
        mock_hotspot_searcher.search_hotspots.assert_called_once()
        mock_technique_searcher.search_techniques.assert_called_once()

    @pytest.mark.asyncio
    async def test_parallel_search_is_actually_parallel(self):
        """需求 10.1: 验证搜索确实并行执行"""
        import time

        async def slow_hotspot_search(script, topic):
            await asyncio.sleep(0.2)
            return []

        async def slow_technique_search(script, script_type, weaknesses):
            await asyncio.sleep(0.2)
            return []

        mock_gen = MagicMock()
        mock_gen.generate_initial_script = AsyncMock(return_value="剧本")
        mock_ev = MagicMock()
        mock_ev.evaluate_script = AsyncMock(return_value=_make_evaluation(9.0))
        mock_hs = MagicMock()
        mock_hs.search_hotspots = AsyncMock(side_effect=slow_hotspot_search)
        mock_ts = MagicMock()
        mock_ts.search_techniques = AsyncMock(side_effect=slow_technique_search)
        mock_vm = MagicMock()
        mock_vm.save_version = AsyncMock(
            side_effect=lambda **kw: _make_version(kw["session_id"], kw["iteration"], 9.0)
        )
        mock_vm.mark_final_version = AsyncMock()

        config = IterationConfig(
            target_score=8.0, max_iterations=1, parallel_search=True
        )
        engine = IterationEngine(
            script_generator=mock_gen,
            script_evaluator=mock_ev,
            hotspot_searcher=mock_hs,
            technique_searcher=mock_ts,
            version_manager=mock_vm,
            config=config,
        )

        start = time.time()
        await engine.optimize_script("测试", "s1", MagicMock())
        elapsed = time.time() - start

        # Parallel: ~0.2s. Sequential would be ~0.4s.
        assert elapsed < 0.35

    @pytest.mark.asyncio
    async def test_search_disabled_returns_empty(self):
        """搜索禁用时返回空列表"""
        mock_gen = MagicMock()
        mock_gen.generate_initial_script = AsyncMock(return_value="剧本")
        mock_ev = MagicMock()
        mock_ev.evaluate_script = AsyncMock(return_value=_make_evaluation(9.0))
        mock_hs = MagicMock()
        mock_hs.search_hotspots = AsyncMock()
        mock_ts = MagicMock()
        mock_ts.search_techniques = AsyncMock()
        mock_vm = MagicMock()
        mock_vm.save_version = AsyncMock(
            side_effect=lambda **kw: _make_version(kw["session_id"], kw["iteration"], 9.0)
        )
        mock_vm.mark_final_version = AsyncMock()

        config = IterationConfig(
            target_score=8.0,
            max_iterations=1,
            enable_hotspot_search=False,
            enable_technique_search=False,
        )
        engine = IterationEngine(
            script_generator=mock_gen,
            script_evaluator=mock_ev,
            hotspot_searcher=mock_hs,
            technique_searcher=mock_ts,
            version_manager=mock_vm,
            config=config,
        )
        await engine.optimize_script("测试", "s1", MagicMock())
        mock_hs.search_hotspots.assert_not_called()
        mock_ts.search_techniques.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_error_returns_empty_gracefully(
        self,
        mock_generator,
        mock_evaluator,
        mock_hotspot_searcher,
        mock_technique_searcher,
        mock_version_manager,
        progress_callback,
    ):
        """搜索失败时不中断流程"""
        mock_hotspot_searcher.search_hotspots = AsyncMock(
            side_effect=RuntimeError("搜索失败")
        )
        mock_technique_searcher.search_techniques = AsyncMock(
            side_effect=RuntimeError("搜索失败")
        )
        config = IterationConfig(target_score=8.0, max_iterations=1)
        engine = IterationEngine(
            script_generator=mock_generator,
            script_evaluator=mock_evaluator,
            hotspot_searcher=mock_hotspot_searcher,
            technique_searcher=mock_technique_searcher,
            version_manager=mock_version_manager,
            config=config,
        )
        # Should not raise
        result = await engine.optimize_script("测试", "s1", progress_callback)
        assert result.total_iterations == 1


# --- Progress callback ---


class TestProgressCallback:
    @pytest.mark.asyncio
    async def test_progress_stages_in_order(
        self, engine, progress_callback
    ):
        """验证进度回调按正确顺序推送"""
        await engine.optimize_script("测试", "s1", progress_callback)
        stages = [
            c[0][0].stage for c in progress_callback.call_args_list
        ]
        # For a single iteration: generating, searching, evaluating, completed
        assert stages == ["generating", "searching", "evaluating", "completed"]

    @pytest.mark.asyncio
    async def test_progress_includes_session_id(
        self, engine, progress_callback
    ):
        await engine.optimize_script("测试", "my-session", progress_callback)
        for c in progress_callback.call_args_list:
            progress: IterationProgress = c[0][0]
            assert progress.session_id == "my-session"

    @pytest.mark.asyncio
    async def test_progress_iteration_numbers(
        self,
        mock_generator,
        mock_evaluator,
        mock_hotspot_searcher,
        mock_technique_searcher,
        mock_version_manager,
        progress_callback,
    ):
        mock_evaluator.evaluate_script = AsyncMock(
            side_effect=[
                _make_evaluation(5.0),
                _make_evaluation(9.0),
            ]
        )
        config = IterationConfig(target_score=8.0, max_iterations=5)
        engine = IterationEngine(
            script_generator=mock_generator,
            script_evaluator=mock_evaluator,
            hotspot_searcher=mock_hotspot_searcher,
            technique_searcher=mock_technique_searcher,
            version_manager=mock_version_manager,
            config=config,
        )
        await engine.optimize_script("测试", "s1", progress_callback)
        # 2 iterations × 3 stages + 1 completed = 7 calls
        assert progress_callback.call_count == 7
