"""LLM 服务单元测试

测试角色提取、分镜生成、JSON 解析和错误处理。
使用 mock HTTP 客户端避免真实 API 调用。
"""

import json
import pytest
import httpx

from app.services.llm_service import (
    LLMService,
    LLMParseError,
    LLMTimeoutError,
    LLMApiError,
    LLMServiceError,
    parse_characters_response,
    parse_storyboard_response,
    _extract_json_from_text,
    _build_character_extraction_messages,
    _build_storyboard_messages,
)
from app.models.character import Character
from app.services.template_service import ContentTemplate


# ============================================================
# Fixtures
# ============================================================

def _make_template() -> ContentTemplate:
    """创建测试用模板"""
    return ContentTemplate(
        id="anime",
        name="动漫模板",
        type="anime",
        character_extraction_prompt="请从以下动漫小说文本中提取角色信息。",
        storyboard_prompt="请将以下动漫小说文本拆解为分镜脚本。",
        image_style={"style_preset": "anime"},
        motion_style={"motion_intensity": 0.5},
        voice_config={"engine": "edge-tts"},
        subtitle_style={"font_size": 24},
    )


def _make_characters() -> list[Character]:
    return [
        Character(id="c1", name="张三", appearance="黑发", personality="冷静", background="军人", image_prompt="a man"),
        Character(id="c2", name="李四", appearance="金发", personality="活泼", background="学生", image_prompt="a girl"),
    ]


def _mock_openai_response(content: str) -> httpx.Response:
    """构造 OpenAI 兼容的 mock 响应"""
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}}],
            "usage": {"total_tokens": 100},
        },
    )


class MockAsyncClient:
    """Mock HTTP 客户端"""

    def __init__(self, responses=None, side_effects=None):
        self.responses = responses or []
        self.side_effects = side_effects or []
        self.call_count = 0
        self.last_request_json = None

    async def post(self, url, **kwargs):
        self.last_request_json = kwargs.get("json")
        idx = self.call_count
        self.call_count += 1
        if idx < len(self.side_effects) and self.side_effects[idx]:
            raise self.side_effects[idx]
        if idx < len(self.responses):
            return self.responses[idx]
        raise RuntimeError("No more mock responses")

    async def aclose(self):
        pass


# ============================================================
# JSON 提取测试
# ============================================================

class TestExtractJsonFromText:
    def test_plain_json_array(self):
        assert _extract_json_from_text('[{"a":1}]') == '[{"a":1}]'

    def test_markdown_code_block(self):
        text = '```json\n[{"a":1}]\n```'
        assert json.loads(_extract_json_from_text(text)) == [{"a": 1}]

    def test_text_with_prefix(self):
        text = '以下是结果：\n[{"name":"test"}]'
        result = _extract_json_from_text(text)
        assert json.loads(result) == [{"name": "test"}]

    def test_json_object(self):
        text = '{"key": "value"}'
        assert json.loads(_extract_json_from_text(text)) == {"key": "value"}

    def test_no_json(self):
        assert _extract_json_from_text("no json here") == "no json here"


# ============================================================
# 角色解析测试
# ============================================================

class TestParseCharactersResponse:
    def test_valid_array(self):
        raw = json.dumps([{"name": "张三", "appearance": "高大"}])
        result = parse_characters_response(raw)
        assert len(result) == 1
        assert result[0]["name"] == "张三"

    def test_wrapped_in_object(self):
        raw = json.dumps({"characters": [{"name": "A"}, {"name": "B"}]})
        result = parse_characters_response(raw)
        assert len(result) == 2

    def test_single_object(self):
        raw = json.dumps({"name": "Solo"})
        result = parse_characters_response(raw)
        assert len(result) == 1

    def test_invalid_json(self):
        with pytest.raises(LLMParseError):
            parse_characters_response("not json at all {{{")

    def test_non_list_result(self):
        with pytest.raises(LLMParseError):
            parse_characters_response('"just a string"')


# ============================================================
# 分镜解析测试
# ============================================================

class TestParseStoryboardResponse:
    def test_valid_array(self):
        raw = json.dumps([{"scene_description": "夕阳", "dialogue": "你好", "camera_direction": "远景"}])
        result = parse_storyboard_response(raw)
        assert len(result) == 1

    def test_wrapped_in_object(self):
        raw = json.dumps({"scenes": [{"scene_description": "A"}, {"scene_description": "B"}]})
        result = parse_storyboard_response(raw)
        assert len(result) == 2

    def test_invalid_json(self):
        with pytest.raises(LLMParseError):
            parse_storyboard_response("broken json")


# ============================================================
# Prompt 构建测试
# ============================================================

class TestPromptBuilding:
    def test_character_extraction_messages(self):
        template = _make_template()
        messages = _build_character_extraction_messages("测试文本", template)
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "测试文本" in messages[1]["content"]
        assert template.character_extraction_prompt in messages[1]["content"]

    def test_storyboard_messages(self):
        template = _make_template()
        chars = _make_characters()
        messages = _build_storyboard_messages("测试文本", chars, template)
        assert len(messages) == 2
        assert "张三" in messages[1]["content"]
        assert "李四" in messages[1]["content"]


# ============================================================
# LLMService 集成测试（使用 mock 客户端）
# ============================================================

class TestLLMServiceExtractCharacters:
    @pytest.mark.asyncio
    async def test_success(self):
        chars_json = json.dumps([
            {"name": "主角", "appearance": "黑发少年", "personality": "勇敢", "background": "孤儿", "image_prompt": "a brave boy"},
        ])
        mock_client = MockAsyncClient(responses=[_mock_openai_response(chars_json)])
        service = LLMService(api_key="test", client=mock_client)

        result = await service.extract_characters("测试小说文本", _make_template())
        assert len(result) == 1
        assert result[0].name == "主角"
        assert result[0].appearance == "黑发少年"
        assert result[0].id.startswith("char-")

    @pytest.mark.asyncio
    async def test_missing_fields_use_defaults(self):
        chars_json = json.dumps([{"name": "无名"}])
        mock_client = MockAsyncClient(responses=[_mock_openai_response(chars_json)])
        service = LLMService(api_key="test", client=mock_client)

        result = await service.extract_characters("文本", _make_template())
        assert result[0].name == "无名"
        assert result[0].appearance == ""

    @pytest.mark.asyncio
    async def test_parse_error(self):
        mock_client = MockAsyncClient(responses=[_mock_openai_response("这不是JSON")])
        service = LLMService(api_key="test", client=mock_client)

        with pytest.raises(LLMParseError):
            await service.extract_characters("文本", _make_template())


class TestLLMServiceGenerateStoryboard:
    @pytest.mark.asyncio
    async def test_success(self):
        scenes_json = json.dumps([
            {"scene_description": "城市远景", "dialogue": "故事开始", "camera_direction": "远景",
             "image_prompt": "city", "motion_prompt": "slow zoom"},
            {"scene_description": "室内近景", "dialogue": "你好", "camera_direction": "近景",
             "image_prompt": "room", "motion_prompt": "pan left"},
        ])
        mock_client = MockAsyncClient(responses=[_mock_openai_response(scenes_json)])
        service = LLMService(api_key="test", client=mock_client)

        result = await service.generate_storyboard("文本", _make_characters(), _make_template())
        assert len(result) == 2
        assert result[0].order == 1
        assert result[1].order == 2
        assert result[0].scene_description == "城市远景"
        assert result[0].id.startswith("scene-")


class TestLLMServiceRetry:
    @pytest.mark.asyncio
    async def test_retry_on_500(self):
        chars_json = json.dumps([{"name": "A"}])
        mock_client = MockAsyncClient(responses=[
            httpx.Response(500, text="Internal Server Error"),
            httpx.Response(500, text="Internal Server Error"),
            _mock_openai_response(chars_json),
        ])
        service = LLMService(api_key="test", max_retries=3, client=mock_client)

        result = await service.extract_characters("文本", _make_template())
        assert len(result) == 1
        assert mock_client.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        mock_client = MockAsyncClient(responses=[
            httpx.Response(500, text="error"),
            httpx.Response(500, text="error"),
            httpx.Response(500, text="error"),
        ])
        service = LLMService(api_key="test", max_retries=3, client=mock_client)

        with pytest.raises(LLMApiError):
            await service.extract_characters("文本", _make_template())

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self):
        chars_json = json.dumps([{"name": "B"}])
        mock_client = MockAsyncClient(
            responses=[None, _mock_openai_response(chars_json)],
            side_effects=[httpx.TimeoutException("timeout"), None],
        )
        service = LLMService(api_key="test", max_retries=3, client=mock_client)

        result = await service.extract_characters("文本", _make_template())
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_non_retryable_error(self):
        mock_client = MockAsyncClient(responses=[httpx.Response(401, text="Unauthorized")])
        service = LLMService(api_key="bad", max_retries=3, client=mock_client)

        with pytest.raises(LLMApiError) as exc_info:
            await service.extract_characters("文本", _make_template())
        assert exc_info.value.status_code == 401


class TestLLMServiceExtractContent:
    def test_empty_choices(self):
        with pytest.raises(LLMParseError):
            LLMService._extract_content({"choices": []})

    def test_empty_content(self):
        with pytest.raises(LLMParseError):
            LLMService._extract_content({"choices": [{"message": {"content": ""}}]})

    def test_valid_content(self):
        result = LLMService._extract_content({"choices": [{"message": {"content": "hello"}}]})
        assert result == "hello"
