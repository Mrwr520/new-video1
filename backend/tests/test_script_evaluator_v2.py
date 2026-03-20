"""剧本评审器 v2 单元测试

测试 ScriptEvaluator 的多维度评审、加权平均计算和改进建议生成。
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from app.schemas.script_optimization import (
    DimensionScores,
    DimensionWeights,
    EvaluationResult,
    Hotspot,
    Technique,
)
from app.services.llm_service import LLMService, LLMServiceError
from app.services.script_evaluator_v2 import (
    ScriptEvaluator,
    _build_evaluation_messages,
    _clamp_score,
    _parse_evaluation_response,
)


# --- Fixtures ---

@pytest.fixture
def default_weights():
    return DimensionWeights()


@pytest.fixture
def sample_hotspots():
    return [
        Hotspot(
            title="AI 技术突破",
            description="最新 AI 模型发布",
            source="tech_news",
            relevance_score=0.9,
        ),
        Hotspot(
            title="短视频趋势",
            description="短视频平台新功能上线",
            source="social_media",
            relevance_score=0.7,
        ),
    ]


@pytest.fixture
def sample_techniques():
    return [
        Technique(
            name="悬念设置",
            description="在剧本开头设置悬念吸引观众",
            example="以一个神秘事件开场",
            category="叙事技巧",
            source="writing_guide",
        ),
        Technique(
            name="情感共鸣",
            description="通过角色情感引发观众共鸣",
            example="展示角色的内心挣扎",
            category="情感技巧",
            source="writing_guide",
        ),
    ]


def _make_llm_response(
    content_quality=8.0,
    structure=7.5,
    creativity=9.0,
    hotspot_relevance=6.0,
    technique_application=7.0,
    reasoning="评审完成",
):
    """构造 LLM 评审响应 JSON 字符串。"""
    return json.dumps({
        "content_quality": content_quality,
        "structure": structure,
        "creativity": creativity,
        "hotspot_relevance": hotspot_relevance,
        "technique_application": technique_application,
        "reasoning": reasoning,
    })


def _make_mock_llm(response_text: str) -> LLMService:
    """创建 mock LLMService，_call_llm 返回指定文本。"""
    mock = MagicMock(spec=LLMService)
    mock._call_llm = AsyncMock(return_value=response_text)
    return mock


# --- _clamp_score ---

class TestClampScore:
    def test_normal_value(self):
        assert _clamp_score(5.0) == 5.0

    def test_below_zero(self):
        assert _clamp_score(-1.0) == 0.0

    def test_above_ten(self):
        assert _clamp_score(15.0) == 10.0

    def test_boundary_zero(self):
        assert _clamp_score(0.0) == 0.0

    def test_boundary_ten(self):
        assert _clamp_score(10.0) == 10.0

    def test_invalid_type_returns_default(self):
        assert _clamp_score("invalid") == 5.0

    def test_none_returns_default(self):
        assert _clamp_score(None) == 5.0


# --- _parse_evaluation_response ---

class TestParseEvaluationResponse:
    def test_valid_json(self):
        raw = _make_llm_response()
        result = _parse_evaluation_response(raw)
        assert result["content_quality"] == 8.0
        assert result["structure"] == 7.5

    def test_json_in_code_block(self):
        raw = "```json\n" + _make_llm_response() + "\n```"
        result = _parse_evaluation_response(raw)
        assert result["content_quality"] == 8.0

    def test_missing_field_raises(self):
        raw = json.dumps({"content_quality": 8.0, "structure": 7.0})
        with pytest.raises(LLMServiceError, match="缺少字段"):
            _parse_evaluation_response(raw)

    def test_invalid_json_raises(self):
        with pytest.raises(LLMServiceError, match="JSON 解析失败"):
            _parse_evaluation_response("not json at all")

    def test_array_instead_of_object_raises(self):
        with pytest.raises(LLMServiceError, match="期望 JSON 对象"):
            _parse_evaluation_response("[1, 2, 3]")


# --- _build_evaluation_messages ---

class TestBuildEvaluationMessages:
    def test_basic_messages(self):
        messages = _build_evaluation_messages("测试剧本", [], [])
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "测试剧本" in messages[1]["content"]

    def test_includes_hotspots(self, sample_hotspots):
        messages = _build_evaluation_messages("剧本", sample_hotspots, [])
        user_content = messages[1]["content"]
        assert "AI 技术突破" in user_content
        assert "当前热点信息" in user_content

    def test_includes_techniques(self, sample_techniques):
        messages = _build_evaluation_messages("剧本", [], sample_techniques)
        user_content = messages[1]["content"]
        assert "悬念设置" in user_content
        assert "推荐创作技巧" in user_content

    def test_no_hotspot_section_when_empty(self):
        messages = _build_evaluation_messages("剧本", [], [])
        user_content = messages[1]["content"]
        assert "当前热点信息" not in user_content


# --- ScriptEvaluator._calculate_total_score ---

class TestCalculateTotalScore:
    def test_default_weights(self, default_weights):
        evaluator = ScriptEvaluator(
            llm_service=MagicMock(), weights=default_weights
        )
        scores = DimensionScores(
            content_quality=8.0,
            structure=7.0,
            creativity=9.0,
            hotspot_relevance=6.0,
            technique_application=7.0,
        )
        total = evaluator._calculate_total_score(scores)
        expected = 8.0 * 0.3 + 7.0 * 0.2 + 9.0 * 0.2 + 6.0 * 0.15 + 7.0 * 0.15
        assert abs(total - round(expected, 2)) < 0.01

    def test_equal_weights(self):
        weights = DimensionWeights(
            content_quality=0.2,
            structure=0.2,
            creativity=0.2,
            hotspot_relevance=0.2,
            technique_application=0.2,
        )
        evaluator = ScriptEvaluator(
            llm_service=MagicMock(), weights=weights
        )
        scores = DimensionScores(
            content_quality=10.0,
            structure=10.0,
            creativity=10.0,
            hotspot_relevance=10.0,
            technique_application=10.0,
        )
        assert evaluator._calculate_total_score(scores) == 10.0

    def test_all_zeros(self, default_weights):
        evaluator = ScriptEvaluator(
            llm_service=MagicMock(), weights=default_weights
        )
        scores = DimensionScores(
            content_quality=0, structure=0, creativity=0,
            hotspot_relevance=0, technique_application=0,
        )
        assert evaluator._calculate_total_score(scores) == 0.0


# --- ScriptEvaluator._generate_suggestions ---

class TestGenerateSuggestions:
    def test_all_high_scores_gives_general_suggestion(self, default_weights):
        evaluator = ScriptEvaluator(
            llm_service=MagicMock(), weights=default_weights
        )
        scores = DimensionScores(
            content_quality=9.0, structure=8.0, creativity=8.5,
            hotspot_relevance=7.5, technique_application=7.0,
        )
        suggestions = evaluator._generate_suggestions("剧本", scores, [], [])
        assert len(suggestions) >= 1
        assert "整体质量良好" in suggestions[0]

    def test_low_content_quality(self, default_weights):
        evaluator = ScriptEvaluator(
            llm_service=MagicMock(), weights=default_weights
        )
        scores = DimensionScores(
            content_quality=5.0, structure=8.0, creativity=8.0,
            hotspot_relevance=8.0, technique_application=8.0,
        )
        suggestions = evaluator._generate_suggestions("剧本", scores, [], [])
        assert any("内容质量" in s for s in suggestions)

    def test_low_hotspot_with_hotspots(self, default_weights, sample_hotspots):
        evaluator = ScriptEvaluator(
            llm_service=MagicMock(), weights=default_weights
        )
        scores = DimensionScores(
            content_quality=8.0, structure=8.0, creativity=8.0,
            hotspot_relevance=4.0, technique_application=8.0,
        )
        suggestions = evaluator._generate_suggestions(
            "剧本", scores, sample_hotspots, []
        )
        assert any("AI 技术突破" in s for s in suggestions)

    def test_low_technique_with_techniques(self, default_weights, sample_techniques):
        evaluator = ScriptEvaluator(
            llm_service=MagicMock(), weights=default_weights
        )
        scores = DimensionScores(
            content_quality=8.0, structure=8.0, creativity=8.0,
            hotspot_relevance=8.0, technique_application=4.0,
        )
        suggestions = evaluator._generate_suggestions(
            "剧本", scores, [], sample_techniques
        )
        assert any("悬念设置" in s for s in suggestions)

    def test_multiple_low_scores(self, default_weights):
        evaluator = ScriptEvaluator(
            llm_service=MagicMock(), weights=default_weights
        )
        scores = DimensionScores(
            content_quality=3.0, structure=4.0, creativity=5.0,
            hotspot_relevance=2.0, technique_application=3.0,
        )
        suggestions = evaluator._generate_suggestions("剧本", scores, [], [])
        assert len(suggestions) == 5

    def test_always_at_least_one_suggestion(self, default_weights):
        evaluator = ScriptEvaluator(
            llm_service=MagicMock(), weights=default_weights
        )
        scores = DimensionScores(
            content_quality=10.0, structure=10.0, creativity=10.0,
            hotspot_relevance=10.0, technique_application=10.0,
        )
        suggestions = evaluator._generate_suggestions("剧本", scores, [], [])
        assert len(suggestions) >= 1


# --- ScriptEvaluator.evaluate_script ---

class TestEvaluateScript:
    @pytest.mark.asyncio
    async def test_successful_evaluation(self, default_weights):
        mock_llm = _make_mock_llm(_make_llm_response())
        evaluator = ScriptEvaluator(llm_service=mock_llm, weights=default_weights)

        result = await evaluator.evaluate_script("测试剧本", [], [])

        assert isinstance(result, EvaluationResult)
        assert result.dimension_scores.content_quality == 8.0
        assert result.dimension_scores.structure == 7.5
        assert result.dimension_scores.creativity == 9.0
        assert result.total_score > 0
        assert len(result.suggestions) >= 1
        assert result.timestamp is not None

    @pytest.mark.asyncio
    async def test_evaluation_with_hotspots_and_techniques(
        self, default_weights, sample_hotspots, sample_techniques
    ):
        mock_llm = _make_mock_llm(_make_llm_response(hotspot_relevance=3.0))
        evaluator = ScriptEvaluator(llm_service=mock_llm, weights=default_weights)

        result = await evaluator.evaluate_script(
            "测试剧本", sample_hotspots, sample_techniques
        )

        assert result.dimension_scores.hotspot_relevance == 3.0
        # Should have suggestion about hotspot relevance
        assert any("热点" in s for s in result.suggestions)

    @pytest.mark.asyncio
    async def test_evaluation_clamps_out_of_range_scores(self, default_weights):
        mock_llm = _make_mock_llm(
            _make_llm_response(content_quality=15.0, structure=-2.0)
        )
        evaluator = ScriptEvaluator(llm_service=mock_llm, weights=default_weights)

        result = await evaluator.evaluate_script("剧本", [], [])

        assert result.dimension_scores.content_quality == 10.0
        assert result.dimension_scores.structure == 0.0

    @pytest.mark.asyncio
    async def test_evaluation_calls_llm(self, default_weights):
        mock_llm = _make_mock_llm(_make_llm_response())
        evaluator = ScriptEvaluator(llm_service=mock_llm, weights=default_weights)

        await evaluator.evaluate_script("剧本内容", [], [])

        mock_llm._call_llm.assert_called_once()
        call_args = mock_llm._call_llm.call_args[0][0]
        assert len(call_args) == 2
        assert call_args[0]["role"] == "system"
        assert "剧本内容" in call_args[1]["content"]

    @pytest.mark.asyncio
    async def test_evaluation_llm_error_propagates(self, default_weights):
        mock_llm = MagicMock(spec=LLMService)
        mock_llm._call_llm = AsyncMock(
            side_effect=LLMServiceError("API 调用失败")
        )
        evaluator = ScriptEvaluator(llm_service=mock_llm, weights=default_weights)

        with pytest.raises(LLMServiceError, match="API 调用失败"):
            await evaluator.evaluate_script("剧本", [], [])

    @pytest.mark.asyncio
    async def test_total_score_matches_weighted_average(self, default_weights):
        mock_llm = _make_mock_llm(
            _make_llm_response(
                content_quality=8.0,
                structure=7.0,
                creativity=9.0,
                hotspot_relevance=6.0,
                technique_application=7.0,
            )
        )
        evaluator = ScriptEvaluator(llm_service=mock_llm, weights=default_weights)

        result = await evaluator.evaluate_script("剧本", [], [])

        expected = (
            8.0 * 0.3 + 7.0 * 0.2 + 9.0 * 0.2
            + 6.0 * 0.15 + 7.0 * 0.15
        )
        assert abs(result.total_score - round(expected, 2)) < 0.01
