"""剧本迭代优化系统核心数据模型和配置的单元测试"""

import pytest
from pydantic import ValidationError

from app.schemas.script_optimization import (
    DimensionScores,
    DimensionWeights,
    EvaluationResult,
    Hotspot,
    IterationProgress,
    ScriptVersion,
    Technique,
)
from app.config.optimization_config import IterationConfig


# --- DimensionScores ---

class TestDimensionScores:
    def test_valid_scores(self):
        scores = DimensionScores(
            content_quality=8.0,
            structure=7.5,
            creativity=9.0,
            hotspot_relevance=6.0,
            technique_application=7.0,
        )
        assert scores.content_quality == 8.0
        assert scores.creativity == 9.0

    def test_boundary_scores(self):
        scores = DimensionScores(
            content_quality=0,
            structure=0,
            creativity=0,
            hotspot_relevance=0,
            technique_application=0,
        )
        assert scores.content_quality == 0

        scores = DimensionScores(
            content_quality=10,
            structure=10,
            creativity=10,
            hotspot_relevance=10,
            technique_application=10,
        )
        assert scores.content_quality == 10

    def test_score_below_zero_rejected(self):
        with pytest.raises(ValidationError):
            DimensionScores(
                content_quality=-1,
                structure=5,
                creativity=5,
                hotspot_relevance=5,
                technique_application=5,
            )

    def test_score_above_ten_rejected(self):
        with pytest.raises(ValidationError):
            DimensionScores(
                content_quality=11,
                structure=5,
                creativity=5,
                hotspot_relevance=5,
                technique_application=5,
            )


# --- DimensionWeights ---

class TestDimensionWeights:
    def test_default_weights(self):
        weights = DimensionWeights()
        assert weights.content_quality == 0.3
        assert weights.structure == 0.2
        assert weights.creativity == 0.2
        assert weights.hotspot_relevance == 0.15
        assert weights.technique_application == 0.15

    def test_default_weights_sum_to_one(self):
        weights = DimensionWeights()
        total = (
            weights.content_quality
            + weights.structure
            + weights.creativity
            + weights.hotspot_relevance
            + weights.technique_application
        )
        assert abs(total - 1.0) < 0.01

    def test_custom_weights_valid(self):
        weights = DimensionWeights(
            content_quality=0.2,
            structure=0.2,
            creativity=0.2,
            hotspot_relevance=0.2,
            technique_application=0.2,
        )
        assert weights.content_quality == 0.2

    def test_weights_not_summing_to_one_rejected(self):
        with pytest.raises(ValidationError):
            DimensionWeights(
                content_quality=0.5,
                structure=0.5,
                creativity=0.5,
                hotspot_relevance=0.5,
                technique_application=0.5,
            )

    def test_calculate_total_score(self):
        weights = DimensionWeights()
        scores = DimensionScores(
            content_quality=8.0,
            structure=7.0,
            creativity=9.0,
            hotspot_relevance=6.0,
            technique_application=7.0,
        )
        total = weights.calculate_total_score(scores)
        expected = 8.0 * 0.3 + 7.0 * 0.2 + 9.0 * 0.2 + 6.0 * 0.15 + 7.0 * 0.15
        assert abs(total - expected) < 0.01


# --- IterationConfig ---

class TestIterationConfig:
    def test_default_config(self):
        config = IterationConfig()
        assert config.target_score == 8.0
        assert config.max_iterations == 20
        assert config.enable_hotspot_search is True
        assert config.enable_technique_search is True
        assert config.parallel_search is True

    def test_custom_config(self):
        config = IterationConfig(target_score=9.0, max_iterations=10)
        assert config.target_score == 9.0
        assert config.max_iterations == 10

    def test_negative_target_score_rejected(self):
        with pytest.raises(ValidationError):
            IterationConfig(target_score=-1.0)

    def test_target_score_above_ten_rejected(self):
        with pytest.raises(ValidationError):
            IterationConfig(target_score=10.5)

    def test_zero_max_iterations_rejected(self):
        with pytest.raises(ValidationError):
            IterationConfig(max_iterations=0)

    def test_negative_max_iterations_rejected(self):
        with pytest.raises(ValidationError):
            IterationConfig(max_iterations=-5)

    def test_config_with_custom_weights(self):
        config = IterationConfig(
            dimension_weights=DimensionWeights(
                content_quality=0.2,
                structure=0.2,
                creativity=0.2,
                hotspot_relevance=0.2,
                technique_application=0.2,
            )
        )
        assert config.dimension_weights.content_quality == 0.2

    def test_config_with_invalid_weights_rejected(self):
        with pytest.raises(ValidationError):
            IterationConfig(
                dimension_weights=DimensionWeights(
                    content_quality=0.5,
                    structure=0.5,
                    creativity=0.5,
                    hotspot_relevance=0.5,
                    technique_application=0.5,
                )
            )


# --- EvaluationResult ---

class TestEvaluationResult:
    def test_valid_result(self):
        scores = DimensionScores(
            content_quality=8.0,
            structure=7.0,
            creativity=9.0,
            hotspot_relevance=6.0,
            technique_application=7.0,
        )
        result = EvaluationResult(
            total_score=7.6,
            dimension_scores=scores,
            suggestions=["改进结构"],
        )
        assert result.total_score == 7.6
        assert len(result.suggestions) == 1
        assert result.timestamp is not None


# --- ScriptVersion ---

class TestScriptVersion:
    def test_valid_version(self):
        scores = DimensionScores(
            content_quality=8.0,
            structure=7.0,
            creativity=9.0,
            hotspot_relevance=6.0,
            technique_application=7.0,
        )
        evaluation = EvaluationResult(
            total_score=7.6,
            dimension_scores=scores,
            suggestions=["改进结构"],
        )
        version = ScriptVersion(
            session_id="test-session",
            iteration=0,
            script="测试剧本内容",
            evaluation=evaluation,
        )
        assert version.session_id == "test-session"
        assert version.iteration == 0
        assert version.is_final is False

    def test_negative_iteration_rejected(self):
        scores = DimensionScores(
            content_quality=5, structure=5, creativity=5,
            hotspot_relevance=5, technique_application=5,
        )
        evaluation = EvaluationResult(
            total_score=5, dimension_scores=scores, suggestions=[],
        )
        with pytest.raises(ValidationError):
            ScriptVersion(
                session_id="s", iteration=-1, script="x", evaluation=evaluation,
            )


# --- IterationProgress ---

class TestIterationProgress:
    def test_valid_progress(self):
        progress = IterationProgress(
            session_id="test",
            current_iteration=1,
            total_iterations=20,
            stage="generating",
            message="正在生成剧本",
        )
        assert progress.stage == "generating"
        assert progress.current_score is None
