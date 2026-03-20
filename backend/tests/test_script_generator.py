"""剧本生成器单元测试

测试 ScriptGenerator 的初始生成、重新生成、提示词构建和错误处理。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.script_optimization import (
    DimensionScores,
    EvaluationResult,
    Hotspot,
    Technique,
)
from app.services.llm_service import (
    LLMApiError,
    LLMService,
    LLMServiceError,
    LLMTimeoutError,
)
from app.services.script_generator import (
    ScriptGenerationError,
    ScriptGenerator,
    _build_initial_prompt_messages,
    _build_regeneration_prompt,
)


# --- Fixtures ---


@pytest.fixture
def mock_llm():
    """创建 mock LLMService，_call_llm 返回默认剧本。"""
    mock = MagicMock(spec=LLMService)
    mock._call_llm = AsyncMock(return_value="这是一个精彩的视频剧本内容。")
    return mock


@pytest.fixture
def generator(mock_llm):
    """创建 ScriptGenerator 实例，使用较短的重试延迟。"""
    return ScriptGenerator(
        llm_service=mock_llm, max_retries=2, retry_base_delay=0.01
    )


@pytest.fixture
def sample_evaluation():
    return EvaluationResult(
        total_score=6.5,
        dimension_scores=DimensionScores(
            content_quality=7.0,
            structure=6.0,
            creativity=8.0,
            hotspot_relevance=5.0,
            technique_application=6.0,
        ),
        suggestions=["增加更多细节描述", "融入热点话题"],
    )


@pytest.fixture
def sample_hotspots():
    return [
        Hotspot(
            title="AI 技术突破",
            description="最新 AI 模型发布",
            source="tech_news",
            relevance_score=0.9,
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
    ]


# --- _build_initial_prompt_messages ---


class TestBuildInitialPromptMessages:
    def test_returns_two_messages(self):
        messages = _build_initial_prompt_messages("测试提示词")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_user_message_contains_prompt(self):
        messages = _build_initial_prompt_messages("关于太空探索的剧本")
        assert "关于太空探索的剧本" in messages[1]["content"]

    def test_system_message_has_instructions(self):
        messages = _build_initial_prompt_messages("test")
        system = messages[0]["content"]
        assert "剧本" in system
        assert "故事结构" in system


# --- _build_regeneration_prompt ---


class TestBuildRegenerationPrompt:
    def test_includes_previous_script(self, sample_evaluation):
        prompt = _build_regeneration_prompt(
            "原始剧本内容", sample_evaluation, [], []
        )
        assert "原始剧本内容" in prompt

    def test_includes_scores(self, sample_evaluation):
        prompt = _build_regeneration_prompt(
            "剧本", sample_evaluation, [], []
        )
        assert "6.5" in prompt
        assert "7.0" in prompt  # content_quality
        assert "6.0" in prompt  # structure

    def test_includes_suggestions(self, sample_evaluation):
        prompt = _build_regeneration_prompt(
            "剧本", sample_evaluation, [], []
        )
        assert "增加更多细节描述" in prompt
        assert "融入热点话题" in prompt

    def test_includes_hotspots(self, sample_evaluation, sample_hotspots):
        prompt = _build_regeneration_prompt(
            "剧本", sample_evaluation, sample_hotspots, []
        )
        assert "AI 技术突破" in prompt
        assert "最新 AI 模型发布" in prompt

    def test_includes_techniques(self, sample_evaluation, sample_techniques):
        prompt = _build_regeneration_prompt(
            "剧本", sample_evaluation, [], sample_techniques
        )
        assert "悬念设置" in prompt
        assert "以一个神秘事件开场" in prompt

    def test_no_hotspot_section_when_empty(self, sample_evaluation):
        prompt = _build_regeneration_prompt(
            "剧本", sample_evaluation, [], []
        )
        assert "当前热点信息" not in prompt

    def test_no_technique_section_when_empty(self, sample_evaluation):
        prompt = _build_regeneration_prompt(
            "剧本", sample_evaluation, [], []
        )
        assert "推荐创作技巧" not in prompt

    def test_no_suggestion_section_when_empty(self):
        evaluation = EvaluationResult(
            total_score=9.0,
            dimension_scores=DimensionScores(
                content_quality=9.0,
                structure=9.0,
                creativity=9.0,
                hotspot_relevance=9.0,
                technique_application=9.0,
            ),
            suggestions=[],
        )
        prompt = _build_regeneration_prompt("剧本", evaluation, [], [])
        assert "改进建议" not in prompt


# --- ScriptGenerator.generate_initial_script ---


class TestGenerateInitialScript:
    @pytest.mark.asyncio
    async def test_success(self, generator, mock_llm):
        result = await generator.generate_initial_script("写一个科幻剧本")
        assert result == "这是一个精彩的视频剧本内容。"
        mock_llm._call_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_prompt_to_llm(self, generator, mock_llm):
        await generator.generate_initial_script("太空探索主题")
        call_args = mock_llm._call_llm.call_args[0][0]
        assert any("太空探索主题" in m["content"] for m in call_args)

    @pytest.mark.asyncio
    async def test_empty_prompt_raises(self, generator):
        with pytest.raises(ScriptGenerationError, match="提示词不能为空"):
            await generator.generate_initial_script("")

    @pytest.mark.asyncio
    async def test_whitespace_prompt_raises(self, generator):
        with pytest.raises(ScriptGenerationError, match="提示词不能为空"):
            await generator.generate_initial_script("   ")

    @pytest.mark.asyncio
    async def test_strips_result(self, mock_llm):
        mock_llm._call_llm = AsyncMock(return_value="  剧本内容  \n")
        gen = ScriptGenerator(llm_service=mock_llm, max_retries=0)
        result = await gen.generate_initial_script("test")
        assert result == "剧本内容"


# --- ScriptGenerator.regenerate_script ---


class TestRegenerateScript:
    @pytest.mark.asyncio
    async def test_success(
        self, generator, mock_llm, sample_evaluation, sample_hotspots, sample_techniques
    ):
        result = await generator.regenerate_script(
            "原始剧本", sample_evaluation, sample_hotspots, sample_techniques
        )
        assert result == "这是一个精彩的视频剧本内容。"
        mock_llm._call_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_context_to_llm(
        self, generator, mock_llm, sample_evaluation, sample_hotspots, sample_techniques
    ):
        await generator.regenerate_script(
            "原始剧本", sample_evaluation, sample_hotspots, sample_techniques
        )
        call_args = mock_llm._call_llm.call_args[0][0]
        user_msg = next(m["content"] for m in call_args if m["role"] == "user")
        assert "原始剧本" in user_msg
        assert "AI 技术突破" in user_msg
        assert "悬念设置" in user_msg

    @pytest.mark.asyncio
    async def test_empty_previous_script_raises(
        self, generator, sample_evaluation
    ):
        with pytest.raises(ScriptGenerationError, match="上一版本剧本不能为空"):
            await generator.regenerate_script("", sample_evaluation, [], [])

    @pytest.mark.asyncio
    async def test_with_empty_hotspots_and_techniques(
        self, generator, sample_evaluation
    ):
        result = await generator.regenerate_script(
            "原始剧本", sample_evaluation, [], []
        )
        assert result == "这是一个精彩的视频剧本内容。"


# --- Retry and Error Handling ---


class TestRetryMechanism:
    @pytest.mark.asyncio
    async def test_retries_on_retryable_error(self, mock_llm):
        mock_llm._call_llm = AsyncMock(
            side_effect=[
                LLMTimeoutError("超时"),
                "重试后的剧本内容",
            ]
        )
        gen = ScriptGenerator(
            llm_service=mock_llm, max_retries=2, retry_base_delay=0.01
        )
        result = await gen.generate_initial_script("test")
        assert result == "重试后的剧本内容"
        assert mock_llm._call_llm.call_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_on_non_retryable_error(self, mock_llm):
        mock_llm._call_llm = AsyncMock(
            side_effect=LLMApiError("认证失败", status_code=401)
        )
        gen = ScriptGenerator(
            llm_service=mock_llm, max_retries=2, retry_base_delay=0.01
        )
        with pytest.raises(ScriptGenerationError):
            await gen.generate_initial_script("test")
        assert mock_llm._call_llm.call_count == 1

    @pytest.mark.asyncio
    async def test_exhausts_retries_then_raises(self, mock_llm):
        mock_llm._call_llm = AsyncMock(
            side_effect=LLMTimeoutError("超时")
        )
        gen = ScriptGenerator(
            llm_service=mock_llm, max_retries=2, retry_base_delay=0.01
        )
        with pytest.raises(ScriptGenerationError, match="已耗尽重试次数"):
            await gen.generate_initial_script("test")
        # initial attempt + 2 retries = 3 calls
        assert mock_llm._call_llm.call_count == 3

    @pytest.mark.asyncio
    async def test_retries_on_empty_response(self, mock_llm):
        mock_llm._call_llm = AsyncMock(
            side_effect=["", "有效剧本内容"]
        )
        gen = ScriptGenerator(
            llm_service=mock_llm, max_retries=2, retry_base_delay=0.01
        )
        result = await gen.generate_initial_script("test")
        assert result == "有效剧本内容"
        assert mock_llm._call_llm.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_server_error(self, mock_llm):
        mock_llm._call_llm = AsyncMock(
            side_effect=[
                LLMApiError("服务器错误", status_code=500),
                "恢复后的剧本",
            ]
        )
        gen = ScriptGenerator(
            llm_service=mock_llm, max_retries=2, retry_base_delay=0.01
        )
        result = await gen.generate_initial_script("test")
        assert result == "恢复后的剧本"

    @pytest.mark.asyncio
    async def test_unexpected_error_no_retry(self, mock_llm):
        mock_llm._call_llm = AsyncMock(
            side_effect=RuntimeError("意外错误")
        )
        gen = ScriptGenerator(
            llm_service=mock_llm, max_retries=2, retry_base_delay=0.01
        )
        with pytest.raises(ScriptGenerationError):
            await gen.generate_initial_script("test")
        assert mock_llm._call_llm.call_count == 1

    @pytest.mark.asyncio
    async def test_zero_retries_fails_immediately(self, mock_llm):
        mock_llm._call_llm = AsyncMock(
            side_effect=LLMTimeoutError("超时")
        )
        gen = ScriptGenerator(
            llm_service=mock_llm, max_retries=0, retry_base_delay=0.01
        )
        with pytest.raises(ScriptGenerationError):
            await gen.generate_initial_script("test")
        assert mock_llm._call_llm.call_count == 1
