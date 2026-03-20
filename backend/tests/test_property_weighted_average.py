"""加权平均计算正确性属性测试

Feature: script-iteration-optimizer, Property 5: 加权平均计算正确性

对于任何五个维度分数和对应权重，计算的总分应该等于各维度分数的加权平均值（误差 < 0.01）。

**Validates: Requirements 2.2**
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.schemas.script_optimization import DimensionScores, DimensionWeights


# ============================================================
# 自定义策略
# ============================================================

# 维度分数策略：每个维度 0-10 的浮点数
dimension_scores_strategy = st.builds(
    DimensionScores,
    content_quality=st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    structure=st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    creativity=st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    hotspot_relevance=st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    technique_application=st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
)


def _normalize_weights(raw: tuple[float, ...]) -> dict:
    """将 5 个正浮点数归一化为和为 1.0 的权重字典。"""
    total = sum(raw)
    normed = [r / total for r in raw]
    # 将每个权重限制在 [0, 1] 范围内（归一化后自然满足）
    keys = ["content_quality", "structure", "creativity", "hotspot_relevance", "technique_application"]
    return dict(zip(keys, normed))


# 权重策略：生成 5 个正浮点数后归一化，确保和为 1.0
dimension_weights_strategy = (
    st.tuples(
        st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    .map(_normalize_weights)
    .map(lambda d: DimensionWeights(**d))
)


# ============================================================
# Property 5: 加权平均计算正确性
# ============================================================

class TestWeightedAverageProperty:
    """Property 5: 加权平均计算正确性

    对于任何五个维度分数和对应权重，计算的总分应该等于各维度分数的加权平均值（误差 < 0.01）。

    **Validates: Requirements 2.2**
    """

    @given(scores=dimension_scores_strategy, weights=dimension_weights_strategy)
    @settings(max_examples=100)
    def test_weighted_average_matches_manual_calculation(
        self, scores: DimensionScores, weights: DimensionWeights
    ):
        """calculate_total_score 的结果应等于手动计算的加权平均值（误差 < 0.01）。

        **Validates: Requirements 2.2**
        """
        result = weights.calculate_total_score(scores)

        # 手动计算加权平均
        expected = (
            scores.content_quality * weights.content_quality
            + scores.structure * weights.structure
            + scores.creativity * weights.creativity
            + scores.hotspot_relevance * weights.hotspot_relevance
            + scores.technique_application * weights.technique_application
        )

        assert abs(result - expected) < 0.01, (
            f"加权平均计算不一致: 结果={result}, 期望={expected}, "
            f"差值={abs(result - expected)}"
        )

    @given(scores=dimension_scores_strategy, weights=dimension_weights_strategy)
    @settings(max_examples=100)
    def test_weighted_average_within_score_range(
        self, scores: DimensionScores, weights: DimensionWeights
    ):
        """加权平均总分应在 0-10 范围内（因为所有分数在 0-10，权重和为 1）。

        **Validates: Requirements 2.2**
        """
        result = weights.calculate_total_score(scores)

        assert 0.0 - 0.01 <= result <= 10.0 + 0.01, (
            f"加权平均总分超出范围: {result}"
        )

    @given(scores=dimension_scores_strategy)
    @settings(max_examples=100)
    def test_default_weights_sum_to_one(self, scores: DimensionScores):
        """默认权重之和应为 1.0，且计算结果与手动计算一致。

        **Validates: Requirements 2.2**
        """
        weights = DimensionWeights()  # 使用默认权重

        total_weight = (
            weights.content_quality + weights.structure + weights.creativity
            + weights.hotspot_relevance + weights.technique_application
        )
        assert abs(total_weight - 1.0) < 0.01

        result = weights.calculate_total_score(scores)
        expected = (
            scores.content_quality * 0.3
            + scores.structure * 0.2
            + scores.creativity * 0.2
            + scores.hotspot_relevance * 0.15
            + scores.technique_application * 0.15
        )
        assert abs(result - expected) < 0.01
