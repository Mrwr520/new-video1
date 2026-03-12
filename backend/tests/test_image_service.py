"""图像生成服务单元测试

测试 prompt 构建、API 调用、图片下载存储和错误处理。
使用 mock HTTP 客户端避免真实 API 调用。
"""

import base64
import json
from pathlib import Path

import pytest
import httpx

from app.services.image_service import (
    ImageGeneratorService,
    ImageGenError,
    ImageGenApiError,
    ImageGenTimeoutError,
    build_image_prompt,
    build_negative_prompt,
    get_image_size,
)
from app.models.character import Character
from app.models.scene import StoryboardScene


# ============================================================
# Fixtures / Helpers
# ============================================================

def _make_scene(**overrides) -> StoryboardScene:
    defaults = dict(
        id="scene-001",
        order=1,
        scene_description="夕阳下的城市天际线",
        dialogue="故事从这里开始",
        camera_direction="远景",
        image_prompt="city skyline at sunset, golden hour",
        motion_prompt="slow zoom in",
    )
    defaults.update(overrides)
    return StoryboardScene(**defaults)


def _make_characters() -> list[Character]:
    return [
        Character(
            id="c1", name="张三",
            appearance="黑色短发，身材高大",
            personality="沉稳冷静",
            background="退役军人",
            image_prompt="a tall man with short black hair, calm expression",
        ),
        Character(
            id="c2", name="李四",
            appearance="金色长发，纤细身材",
            personality="活泼开朗",
            background="大学生",
            image_prompt="a girl with long golden hair, cheerful expression",
        ),
    ]


def _make_style_config() -> dict:
    return {
        "style_preset": "anime",
        "negative_prompt": "realistic, photo, blurry, low quality",
        "width": 1024,
        "height": 576,
        "guidance_scale": 7.5,
        "extra": {
            "sampler": "euler_a",
            "steps": 30,
            "style_keywords": "anime style, vibrant colors, detailed",
        },
    }


def _mock_image_response(url: str = "https://example.com/image.png") -> httpx.Response:
    """构造 OpenAI 兼容的图像生成 mock 响应"""
    return httpx.Response(200, json={"data": [{"url": url}]})


def _mock_image_b64_response() -> httpx.Response:
    """构造 base64 格式的图像生成 mock 响应"""
    # 1x1 白色 PNG
    b64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50).decode()
    return httpx.Response(200, json={"data": [{"b64_json": b64}]})


def _mock_download_response(content: bytes = b"fake-png-data") -> httpx.Response:
    return httpx.Response(200, content=content)


class MockAsyncClient:
    """Mock HTTP 客户端，支持 post 和 get"""

    def __init__(self, responses=None, side_effects=None):
        self.responses = responses or []
        self.side_effects = side_effects or []
        self.call_count = 0
        self.calls: list[dict] = []

    async def post(self, url, **kwargs):
        return await self._handle_call("post", url, **kwargs)

    async def get(self, url, **kwargs):
        return await self._handle_call("get", url, **kwargs)

    async def _handle_call(self, method, url, **kwargs):
        idx = self.call_count
        self.calls.append({"method": method, "url": url, **kwargs})
        self.call_count += 1
        if idx < len(self.side_effects) and self.side_effects[idx]:
            raise self.side_effects[idx]
        if idx < len(self.responses):
            return self.responses[idx]
        raise RuntimeError(f"No more mock responses (call #{idx})")

    async def aclose(self):
        pass


# ============================================================
# Prompt 构建测试
# ============================================================

class TestBuildImagePrompt:
    def test_uses_scene_image_prompt(self):
        scene = _make_scene(image_prompt="city at sunset")
        result = build_image_prompt(scene, [], {})
        assert "city at sunset" in result

    def test_falls_back_to_scene_description(self):
        scene = _make_scene(image_prompt="", scene_description="夕阳下的城市")
        result = build_image_prompt(scene, [], {})
        assert "夕阳下的城市" in result

    def test_includes_character_image_prompts(self):
        scene = _make_scene()
        chars = _make_characters()
        result = build_image_prompt(scene, chars, {})
        assert "tall man with short black hair" in result
        assert "long golden hair" in result

    def test_character_falls_back_to_appearance(self):
        char = Character(
            id="c1", name="A", appearance="红色头发", personality="", background="", image_prompt=""
        )
        result = build_image_prompt(_make_scene(), [char], {})
        assert "红色头发" in result

    def test_includes_style_keywords(self):
        style = _make_style_config()
        result = build_image_prompt(_make_scene(), [], style)
        assert "anime style" in result
        assert "vibrant colors" in result

    def test_includes_style_preset(self):
        style = {"style_preset": "anime"}
        result = build_image_prompt(_make_scene(), [], style)
        assert "anime style" in result

    def test_empty_inputs(self):
        scene = _make_scene(image_prompt="", scene_description="")
        result = build_image_prompt(scene, [], {})
        assert result == ""

    def test_full_combination(self):
        scene = _make_scene()
        chars = _make_characters()
        style = _make_style_config()
        result = build_image_prompt(scene, chars, style)
        # Should contain scene prompt, character descriptions, and style
        assert "city skyline at sunset" in result
        assert "tall man" in result
        assert "anime style" in result


class TestBuildNegativePrompt:
    def test_returns_negative_prompt(self):
        style = {"negative_prompt": "blurry, low quality"}
        assert build_negative_prompt(style) == "blurry, low quality"

    def test_empty_when_missing(self):
        assert build_negative_prompt({}) == ""


class TestGetImageSize:
    def test_returns_configured_size(self):
        style = {"width": 1280, "height": 720}
        assert get_image_size(style) == (1280, 720)

    def test_enforces_minimum_width(self):
        style = {"width": 512, "height": 576}
        w, h = get_image_size(style)
        assert w >= 1024

    def test_enforces_minimum_height(self):
        style = {"width": 1024, "height": 256}
        w, h = get_image_size(style)
        assert h >= 576

    def test_defaults_when_missing(self):
        assert get_image_size({}) == (1024, 576)


# ============================================================
# _extract_image_url 测试
# ============================================================

class TestExtractImageUrl:
    def test_extracts_url(self):
        data = {"data": [{"url": "https://example.com/img.png"}]}
        assert ImageGeneratorService._extract_image_url(data) == "https://example.com/img.png"

    def test_extracts_b64(self):
        data = {"data": [{"b64_json": "abc123"}]}
        result = ImageGeneratorService._extract_image_url(data)
        assert result == "data:image/png;base64,abc123"

    def test_empty_data_raises(self):
        with pytest.raises(ImageGenError):
            ImageGeneratorService._extract_image_url({"data": []})

    def test_no_url_or_b64_raises(self):
        with pytest.raises(ImageGenError):
            ImageGeneratorService._extract_image_url({"data": [{}]})

    def test_missing_data_key_raises(self):
        with pytest.raises(ImageGenError):
            ImageGeneratorService._extract_image_url({})


# ============================================================
# generate_keyframe 集成测试（mock 客户端）
# ============================================================

class TestGenerateKeyframe:
    @pytest.mark.asyncio
    async def test_success_with_url(self, tmp_path):
        """成功生成关键帧：API 返回 URL，下载并保存"""
        mock_client = MockAsyncClient(responses=[
            _mock_image_response("https://example.com/generated.png"),
            _mock_download_response(b"fake-image-bytes"),
        ])
        service = ImageGeneratorService(
            api_key="test",
            projects_dir=tmp_path,
            client=mock_client,
        )

        scene = _make_scene()
        result = await service.generate_keyframe(
            scene, _make_characters(), _make_style_config(), project_id="proj-1"
        )

        assert "proj-1" in result
        assert "keyframes" in result
        assert "scene_scene-001.png" in result
        assert Path(result).exists()
        assert Path(result).read_bytes() == b"fake-image-bytes"

    @pytest.mark.asyncio
    async def test_success_with_b64(self, tmp_path):
        """成功生成关键帧：API 返回 base64"""
        b64_data = base64.b64encode(b"fake-png-data").decode()
        mock_client = MockAsyncClient(responses=[
            httpx.Response(200, json={"data": [{"b64_json": b64_data}]}),
        ])
        service = ImageGeneratorService(
            api_key="test",
            projects_dir=tmp_path,
            client=mock_client,
        )

        result = await service.generate_keyframe(
            _make_scene(), [], _make_style_config(), project_id="proj-2"
        )

        assert Path(result).exists()
        assert Path(result).read_bytes() == b"fake-png-data"

    @pytest.mark.asyncio
    async def test_creates_keyframes_directory(self, tmp_path):
        """自动创建 keyframes 目录"""
        mock_client = MockAsyncClient(responses=[
            _mock_image_response("https://example.com/img.png"),
            _mock_download_response(b"data"),
        ])
        service = ImageGeneratorService(
            api_key="test",
            projects_dir=tmp_path,
            client=mock_client,
        )

        result = await service.generate_keyframe(
            _make_scene(), [], {}, project_id="new-proj"
        )

        keyframes_dir = tmp_path / "new-proj" / "keyframes"
        assert keyframes_dir.is_dir()

    @pytest.mark.asyncio
    async def test_sends_correct_api_payload(self, tmp_path):
        """验证发送给 API 的 payload 格式正确"""
        mock_client = MockAsyncClient(responses=[
            _mock_image_response("https://example.com/img.png"),
            _mock_download_response(b"data"),
        ])
        service = ImageGeneratorService(
            api_url="https://api.test.com/v1",
            api_key="sk-test",
            model="dall-e-3",
            projects_dir=tmp_path,
            client=mock_client,
        )

        style = _make_style_config()
        await service.generate_keyframe(
            _make_scene(), _make_characters(), style, project_id="p1"
        )

        # Check the POST call
        post_call = mock_client.calls[0]
        assert post_call["method"] == "post"
        assert "images/generations" in post_call["url"]
        payload = post_call["json"]
        assert payload["model"] == "dall-e-3"
        assert payload["n"] == 1
        assert payload["size"] == "1024x576"
        assert "prompt" in payload
        assert payload["negative_prompt"] == style["negative_prompt"]

        # Check auth header
        headers = post_call["headers"]
        assert headers["Authorization"] == "Bearer sk-test"


# ============================================================
# regenerate_keyframe 测试
# ============================================================

class TestRegenerateKeyframe:
    @pytest.mark.asyncio
    async def test_regenerate_works(self, tmp_path):
        """regenerate_keyframe 与 generate_keyframe 行为一致"""
        mock_client = MockAsyncClient(responses=[
            _mock_image_response("https://example.com/img.png"),
            _mock_download_response(b"new-image"),
        ])
        service = ImageGeneratorService(
            api_key="test",
            projects_dir=tmp_path,
            client=mock_client,
        )

        result = await service.regenerate_keyframe(
            _make_scene(), [], {}, project_id="proj-regen"
        )
        assert Path(result).exists()
        assert Path(result).read_bytes() == b"new-image"


# ============================================================
# 错误处理测试
# ============================================================

class TestImageApiRetry:
    @pytest.mark.asyncio
    async def test_retry_on_500(self, tmp_path):
        mock_client = MockAsyncClient(responses=[
            httpx.Response(500, text="Internal Server Error"),
            httpx.Response(500, text="Internal Server Error"),
            _mock_image_response("https://example.com/img.png"),
            _mock_download_response(b"data"),
        ])
        service = ImageGeneratorService(
            api_key="test",
            max_retries=3,
            projects_dir=tmp_path,
            client=mock_client,
        )

        result = await service.generate_keyframe(
            _make_scene(), [], {}, project_id="p1"
        )
        assert Path(result).exists()
        # 2 failed POSTs + 1 success POST + 1 GET download = 4 calls
        assert mock_client.call_count == 4

    @pytest.mark.asyncio
    async def test_retry_on_429(self, tmp_path):
        mock_client = MockAsyncClient(responses=[
            httpx.Response(429, text="Rate limited"),
            _mock_image_response("https://example.com/img.png"),
            _mock_download_response(b"data"),
        ])
        service = ImageGeneratorService(
            api_key="test",
            max_retries=3,
            projects_dir=tmp_path,
            client=mock_client,
        )

        result = await service.generate_keyframe(
            _make_scene(), [], {}, project_id="p1"
        )
        assert Path(result).exists()

    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        mock_client = MockAsyncClient(responses=[
            httpx.Response(500, text="error"),
            httpx.Response(500, text="error"),
            httpx.Response(500, text="error"),
        ])
        service = ImageGeneratorService(
            api_key="test", max_retries=3, client=mock_client,
        )

        with pytest.raises(ImageGenApiError):
            await service.generate_keyframe(_make_scene(), [], {})

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self, tmp_path):
        mock_client = MockAsyncClient(
            responses=[None, _mock_image_response("https://example.com/img.png"), _mock_download_response(b"data")],
            side_effects=[httpx.TimeoutException("timeout"), None, None],
        )
        service = ImageGeneratorService(
            api_key="test",
            max_retries=3,
            projects_dir=tmp_path,
            client=mock_client,
        )

        result = await service.generate_keyframe(
            _make_scene(), [], {}, project_id="p1"
        )
        assert Path(result).exists()

    @pytest.mark.asyncio
    async def test_non_retryable_error(self):
        mock_client = MockAsyncClient(responses=[
            httpx.Response(401, text="Unauthorized"),
        ])
        service = ImageGeneratorService(
            api_key="bad", max_retries=3, client=mock_client,
        )

        with pytest.raises(ImageGenApiError) as exc_info:
            await service.generate_keyframe(_make_scene(), [], {})
        assert exc_info.value.status_code == 401


class TestDownloadErrors:
    @pytest.mark.asyncio
    async def test_download_failure(self, tmp_path):
        mock_client = MockAsyncClient(responses=[
            _mock_image_response("https://example.com/img.png"),
            httpx.Response(404, text="Not Found"),
        ])
        service = ImageGeneratorService(
            api_key="test",
            projects_dir=tmp_path,
            client=mock_client,
        )

        with pytest.raises(ImageGenError, match="下载图片失败"):
            await service.generate_keyframe(
                _make_scene(), [], {}, project_id="p1"
            )

    @pytest.mark.asyncio
    async def test_download_timeout(self, tmp_path):
        mock_client = MockAsyncClient(
            responses=[_mock_image_response("https://example.com/img.png"), None],
            side_effects=[None, httpx.TimeoutException("timeout")],
        )
        service = ImageGeneratorService(
            api_key="test",
            projects_dir=tmp_path,
            client=mock_client,
        )

        with pytest.raises(ImageGenTimeoutError):
            await service.generate_keyframe(
                _make_scene(), [], {}, project_id="p1"
            )


# ============================================================
# close 测试
# ============================================================

class TestServiceLifecycle:
    @pytest.mark.asyncio
    async def test_close_owned_client(self):
        """关闭自己创建的客户端"""
        service = ImageGeneratorService(api_key="test")
        # Force client creation
        await service._get_client()
        assert service._client is not None
        await service.close()
        assert service._client is None

    @pytest.mark.asyncio
    async def test_close_injected_client(self):
        """不关闭注入的客户端"""
        mock_client = MockAsyncClient()
        service = ImageGeneratorService(api_key="test", client=mock_client)
        await service.close()
        # Injected client is not owned, so _client stays
        # (but _owns_client is False so aclose is not called)
