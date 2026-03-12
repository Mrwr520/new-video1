"""TTS API 端点测试

测试 TTS 引擎列表、语音列表和语音生成 API 端点。

Requirements:
    6.3: 语音生成完成后，提供音频预览和播放功能
    6.5: TTS_Engine 失败时，显示错误信息并提供重试选项
    6.6: TTS_Engine 生成采样率不低于 16kHz 的音频文件
"""

import uuid
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from app.services.tts_service import (
    TTSAdapter,
    TTSService,
    TTSGenerationError,
    VoiceInfo,
    EngineInfo,
)
from app.api.tts import get_tts_service, _tts_service


# ============================================================
# Mock 适配器
# ============================================================

class MockTTSAdapter(TTSAdapter):
    """测试用 Mock TTS 适配器"""

    def __init__(self, name: str = "mock-tts", should_fail: bool = False):
        self._name = name
        self._should_fail = should_fail

    async def generate_speech(self, text: str, voice_id: str, output_path: Optional[str] = None) -> str:
        if self._should_fail:
            raise TTSGenerationError("模拟生成失败")
        if output_path is None:
            output_path = f"/tmp/mock_{voice_id}.wav"
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text("mock audio")
        return output_path

    async def list_voices(self) -> list[VoiceInfo]:
        return [
            VoiceInfo(id="mock-voice-1", name="Mock 女声", language="zh-CN", gender="Female"),
            VoiceInfo(id="mock-voice-2", name="Mock 男声", language="zh-CN", gender="Male"),
        ]

    def get_engine_info(self) -> EngineInfo:
        return EngineInfo(
            name=self._name,
            display_name=f"Mock TTS ({self._name})",
            is_paid=False,
            supported_languages=["zh-CN", "en-US"],
            requires_api_key=False,
            description="Mock adapter for testing",
        )


# ============================================================
# Fixtures
# ============================================================

@pytest_asyncio.fixture
async def setup_tts(client, tmp_path):
    """设置 TTS 服务使用 mock 适配器，并清理全局状态"""
    import app.api.tts as tts_module

    service = TTSService(projects_dir=tmp_path)
    service.register_adapter("mock-tts", MockTTSAdapter("mock-tts"))
    service.register_adapter("mock-fail", MockTTSAdapter("mock-fail", should_fail=True))

    old_service = tts_module._tts_service
    tts_module._tts_service = service
    yield service
    tts_module._tts_service = old_service


async def _create_project(client) -> str:
    """创建测试项目并返回 ID"""
    resp = await client.post("/api/projects", json={"name": "TTS 测试项目", "template_id": "anime"})
    assert resp.status_code == 201
    return resp.json()["id"]


async def _create_scene_with_dialogue(client, project_id: str, dialogue: str = "你好世界") -> str:
    """创建带台词的分镜并返回 ID"""
    resp = await client.post(f"/api/projects/{project_id}/scenes", json={
        "scene_description": "测试场景",
        "dialogue": dialogue,
        "camera_direction": "近景",
    })
    assert resp.status_code == 201
    return resp.json()["id"]


# ============================================================
# GET /api/tts/engines 测试
# ============================================================

class TestListEngines:
    """测试 TTS 引擎列表端点"""

    @pytest.mark.asyncio
    async def test_list_engines_returns_registered_engines(self, client, setup_tts):
        resp = await client.get("/api/tts/engines")
        assert resp.status_code == 200
        engines = resp.json()
        assert isinstance(engines, list)
        assert len(engines) >= 2  # edge-tts, chattts + mock adapters
        names = [e["name"] for e in engines]
        assert "mock-tts" in names

    @pytest.mark.asyncio
    async def test_engine_info_fields(self, client, setup_tts):
        resp = await client.get("/api/tts/engines")
        engines = resp.json()
        for engine in engines:
            assert "name" in engine
            assert "display_name" in engine
            assert "is_paid" in engine
            assert "supported_languages" in engine
            assert "requires_api_key" in engine
            assert "description" in engine


# ============================================================
# GET /api/tts/engines/{engine}/voices 测试
# ============================================================

class TestListVoices:
    """测试语音列表端点"""

    @pytest.mark.asyncio
    async def test_list_voices_for_mock_engine(self, client, setup_tts):
        resp = await client.get("/api/tts/engines/mock-tts/voices")
        assert resp.status_code == 200
        voices = resp.json()
        assert isinstance(voices, list)
        assert len(voices) == 2
        assert voices[0]["id"] == "mock-voice-1"
        assert voices[1]["id"] == "mock-voice-2"

    @pytest.mark.asyncio
    async def test_voice_info_fields(self, client, setup_tts):
        resp = await client.get("/api/tts/engines/mock-tts/voices")
        voices = resp.json()
        for voice in voices:
            assert "id" in voice
            assert "name" in voice
            assert "language" in voice
            assert "gender" in voice

    @pytest.mark.asyncio
    async def test_list_voices_unknown_engine_returns_404(self, client, setup_tts):
        resp = await client.get("/api/tts/engines/nonexistent/voices")
        assert resp.status_code == 404


# ============================================================
# POST /api/projects/{id}/scenes/{sid}/generate-speech 测试
# ============================================================

class TestGenerateSpeech:
    """测试语音生成端点"""

    @pytest.mark.asyncio
    async def test_generate_speech_success(self, client, setup_tts):
        project_id = await _create_project(client)
        scene_id = await _create_scene_with_dialogue(client, project_id)

        resp = await client.post(
            f"/api/projects/{project_id}/scenes/{scene_id}/generate-speech",
            json={"engine": "mock-tts", "voice_id": "mock-voice-1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["scene_id"] == scene_id
        assert data["engine"] == "mock-tts"
        assert data["voice_id"] == "mock-voice-1"
        assert "audio_path" in data

    @pytest.mark.asyncio
    async def test_generate_speech_updates_scene_audio_path(self, client, setup_tts):
        project_id = await _create_project(client)
        scene_id = await _create_scene_with_dialogue(client, project_id)

        await client.post(
            f"/api/projects/{project_id}/scenes/{scene_id}/generate-speech",
            json={"engine": "mock-tts", "voice_id": "mock-voice-1"},
        )

        # 验证分镜的 audio_path 已更新
        resp = await client.get(f"/api/projects/{project_id}/scenes")
        scenes = resp.json()
        scene = next(s for s in scenes if s["id"] == scene_id)
        assert scene["audio_path"] is not None

    @pytest.mark.asyncio
    async def test_generate_speech_project_not_found(self, client, setup_tts):
        resp = await client.post(
            "/api/projects/nonexistent/scenes/scene-1/generate-speech",
            json={"engine": "mock-tts", "voice_id": "mock-voice-1"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_speech_scene_not_found(self, client, setup_tts):
        project_id = await _create_project(client)
        resp = await client.post(
            f"/api/projects/{project_id}/scenes/nonexistent/generate-speech",
            json={"engine": "mock-tts", "voice_id": "mock-voice-1"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_speech_empty_dialogue(self, client, setup_tts):
        """没有台词的分镜应返回 400"""
        project_id = await _create_project(client)
        resp = await client.post(f"/api/projects/{project_id}/scenes", json={
            "scene_description": "无台词场景",
            "dialogue": "",
            "camera_direction": "远景",
        })
        scene_id = resp.json()["id"]

        resp = await client.post(
            f"/api/projects/{project_id}/scenes/{scene_id}/generate-speech",
            json={"engine": "mock-tts", "voice_id": "mock-voice-1"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_generate_speech_unknown_engine(self, client, setup_tts):
        project_id = await _create_project(client)
        scene_id = await _create_scene_with_dialogue(client, project_id)

        resp = await client.post(
            f"/api/projects/{project_id}/scenes/{scene_id}/generate-speech",
            json={"engine": "nonexistent", "voice_id": "voice-1"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_speech_engine_failure_returns_502(self, client, setup_tts):
        """TTS 引擎失败时应返回 502 并包含重试信息 (Req 6.5)"""
        project_id = await _create_project(client)
        scene_id = await _create_scene_with_dialogue(client, project_id)

        resp = await client.post(
            f"/api/projects/{project_id}/scenes/{scene_id}/generate-speech",
            json={"engine": "mock-fail", "voice_id": "voice-1"},
        )
        assert resp.status_code == 502
        detail = resp.json()["detail"]
        assert detail["retryable"] is True
        assert "code" in detail

    @pytest.mark.asyncio
    async def test_generate_speech_default_params(self, client, setup_tts):
        """不传参数时使用默认引擎和语音"""
        project_id = await _create_project(client)
        scene_id = await _create_scene_with_dialogue(client, project_id)

        # 注册 edge-tts mock 以覆盖默认引擎
        setup_tts.register_adapter("edge-tts", MockTTSAdapter("edge-tts"))

        resp = await client.post(
            f"/api/projects/{project_id}/scenes/{scene_id}/generate-speech",
            json={},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["engine"] == "edge-tts"
