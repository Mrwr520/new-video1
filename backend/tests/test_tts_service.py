"""TTS 服务单元测试

测试 TTS 可插拔适配器架构，包括：
- TTSAdapter 抽象基类
- EdgeTTSAdapter / ChatTTSAdapter
- 预留适配器骨架
- TTSService 管理器（引擎注册、选择、调用）
- 角色语音分配逻辑

所有实际 TTS 引擎调用均使用 mock，因为 edge-tts 和 ChatTTS 可能未安装。
"""

import asyncio
import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.tts_service import (
    TTSAdapter,
    TTSService,
    TTSError,
    TTSDependencyError,
    TTSEngineNotFoundError,
    TTSGenerationError,
    EdgeTTSAdapter,
    ChatTTSAdapter,
    FishSpeechAdapter,
    CosyVoiceAdapter,
    MiniMaxTTSAdapter,
    VolcEngineTTSAdapter,
    VoiceInfo,
    EngineInfo,
    assign_voices_to_characters,
)


# ============================================================
# 测试用 Mock 适配器
# ============================================================

class MockTTSAdapter(TTSAdapter):
    """用于测试的 Mock TTS 适配器"""

    def __init__(self, name: str = "mock-tts", voices: Optional[list[VoiceInfo]] = None):
        self._name = name
        self._voices = voices or [
            VoiceInfo(id="mock-voice-1", name="Mock Voice 1", language="zh-CN", gender="Female"),
            VoiceInfo(id="mock-voice-2", name="Mock Voice 2", language="zh-CN", gender="Male"),
            VoiceInfo(id="mock-voice-3", name="Mock Voice 3", language="en-US", gender="Female"),
        ]
        self.generate_calls: list[dict] = []

    async def generate_speech(self, text: str, voice_id: str, output_path: Optional[str] = None) -> str:
        self.generate_calls.append({"text": text, "voice_id": voice_id, "output_path": output_path})
        if output_path is None:
            output_path = f"/tmp/mock_{voice_id}.wav"
        # Create a dummy file
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text("mock audio data")
        return output_path

    async def list_voices(self) -> list[VoiceInfo]:
        return list(self._voices)

    def get_engine_info(self) -> EngineInfo:
        return EngineInfo(
            name=self._name,
            display_name=f"Mock TTS ({self._name})",
            is_paid=False,
            supported_languages=["zh-CN", "en-US"],
            requires_api_key=False,
            description="Mock TTS adapter for testing",
        )


# ============================================================
# TTSAdapter 抽象基类测试
# ============================================================

class TestTTSAdapterABC:
    """测试 TTSAdapter 抽象基类不能直接实例化"""

    def test_cannot_instantiate_abstract_class(self):
        with pytest.raises(TypeError):
            TTSAdapter()  # type: ignore[abstract]

    def test_mock_adapter_implements_interface(self):
        adapter = MockTTSAdapter()
        assert isinstance(adapter, TTSAdapter)


# ============================================================
# EdgeTTSAdapter 测试
# ============================================================

class TestEdgeTTSAdapter:
    """测试 EdgeTTSAdapter"""

    def test_get_engine_info(self):
        adapter = EdgeTTSAdapter()
        info = adapter.get_engine_info()
        assert info.name == "edge-tts"
        assert info.is_paid is False
        assert info.requires_api_key is False
        assert "zh-CN" in info.supported_languages

    @pytest.mark.asyncio
    async def test_list_voices_returns_defaults_when_dependency_missing(self):
        """当 edge-tts 不可用时，返回预定义语音列表"""
        adapter = EdgeTTSAdapter()
        with patch("app.services.tts_service._edge_tts_available", False):
            voices = await adapter.list_voices()
            assert len(voices) > 0
            assert all(isinstance(v, VoiceInfo) for v in voices)
            # 验证包含中文语音
            zh_voices = [v for v in voices if v.language == "zh-CN"]
            assert len(zh_voices) > 0

    @pytest.mark.asyncio
    async def test_generate_speech_raises_when_dependency_missing(self):
        """当 edge-tts 不可用时，generate_speech 应抛出 TTSDependencyError"""
        adapter = EdgeTTSAdapter()
        with patch("app.services.tts_service._edge_tts_available", False):
            with pytest.raises(TTSDependencyError) as exc_info:
                await adapter.generate_speech("测试文本", "zh-CN-XiaoxiaoNeural")
            assert "edge-tts" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_generate_speech_raises_on_empty_text(self):
        """空文本应抛出 TTSGenerationError"""
        adapter = EdgeTTSAdapter()
        with patch("app.services.tts_service._edge_tts_available", True):
            with pytest.raises(TTSGenerationError):
                await adapter.generate_speech("", "zh-CN-XiaoxiaoNeural")

    @pytest.mark.asyncio
    async def test_generate_speech_raises_on_whitespace_text(self):
        """纯空白文本应抛出 TTSGenerationError"""
        adapter = EdgeTTSAdapter()
        with patch("app.services.tts_service._edge_tts_available", True):
            with pytest.raises(TTSGenerationError):
                await adapter.generate_speech("   ", "zh-CN-XiaoxiaoNeural")

    @pytest.mark.asyncio
    async def test_generate_speech_with_mocked_edge_tts(self, tmp_path):
        """使用 mock 的 edge-tts 测试语音生成"""
        adapter = EdgeTTSAdapter(output_dir=tmp_path)
        output_file = str(tmp_path / "test_output.mp3")

        mock_communicate = MagicMock()
        mock_communicate.save = AsyncMock()

        with patch("app.services.tts_service._edge_tts_available", True), \
             patch("app.services.tts_service.edge_tts") as mock_edge:
            mock_edge.Communicate.return_value = mock_communicate
            result = await adapter.generate_speech("你好世界", "zh-CN-XiaoxiaoNeural", output_file)
            assert result == output_file
            mock_edge.Communicate.assert_called_once_with("你好世界", "zh-CN-XiaoxiaoNeural")
            mock_communicate.save.assert_called_once_with(output_file)

    def test_default_voices_have_unique_ids(self):
        """预定义语音列表中的 ID 应唯一"""
        ids = [v.id for v in EdgeTTSAdapter.DEFAULT_VOICES]
        assert len(ids) == len(set(ids))


# ============================================================
# ChatTTSAdapter 测试
# ============================================================

class TestChatTTSAdapter:
    """测试 ChatTTSAdapter"""

    def test_get_engine_info(self):
        adapter = ChatTTSAdapter()
        info = adapter.get_engine_info()
        assert info.name == "chattts"
        assert info.is_paid is False
        assert info.requires_api_key is False

    @pytest.mark.asyncio
    async def test_list_voices(self):
        adapter = ChatTTSAdapter()
        voices = await adapter.list_voices()
        assert len(voices) > 0
        assert all(isinstance(v, VoiceInfo) for v in voices)

    @pytest.mark.asyncio
    async def test_generate_speech_raises_when_dependency_missing(self):
        """当 ChatTTS 不可用时，应抛出 TTSDependencyError"""
        adapter = ChatTTSAdapter()
        with patch("app.services.tts_service._chattts_available", False):
            with pytest.raises(TTSDependencyError) as exc_info:
                await adapter.generate_speech("测试文本", "chattts-default")
            assert "ChatTTS" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_generate_speech_raises_on_empty_text(self):
        """空文本应抛出 TTSGenerationError"""
        adapter = ChatTTSAdapter()
        with patch("app.services.tts_service._chattts_available", True):
            with pytest.raises(TTSGenerationError):
                await adapter.generate_speech("", "chattts-default")

    def test_voice_id_to_seed(self):
        """测试 voice_id 到种子的映射"""
        assert ChatTTSAdapter._voice_id_to_seed("chattts-default") is None
        assert ChatTTSAdapter._voice_id_to_seed("chattts-seed-1") == 42
        assert ChatTTSAdapter._voice_id_to_seed("chattts-seed-2") == 123
        assert ChatTTSAdapter._voice_id_to_seed("unknown-voice") is None


# ============================================================
# 预留适配器骨架测试
# ============================================================

class TestPaidAdapters:
    """测试收费模型适配器"""

    @pytest.mark.parametrize("adapter_cls,expected_name,expected_paid", [
        (FishSpeechAdapter, "fish-speech", True),
        (CosyVoiceAdapter, "cosyvoice", True),
        (MiniMaxTTSAdapter, "minimax-tts", True),
        (VolcEngineTTSAdapter, "volcengine-tts", True),
    ])
    def test_engine_info(self, adapter_cls, expected_name, expected_paid):
        adapter = adapter_cls()
        info = adapter.get_engine_info()
        assert info.name == expected_name
        assert info.is_paid is expected_paid
        assert info.requires_api_key is True

    @pytest.mark.parametrize("adapter_cls", [
        FishSpeechAdapter,
        CosyVoiceAdapter,
        MiniMaxTTSAdapter,
        VolcEngineTTSAdapter,
    ])
    @pytest.mark.asyncio
    async def test_generate_speech_raises_without_api_key(self, adapter_cls):
        """未配置 API Key 时应抛出 TTSError"""
        adapter = adapter_cls()
        with pytest.raises(TTSError):
            await adapter.generate_speech("测试", "voice-1")

    @pytest.mark.parametrize("adapter_cls", [
        FishSpeechAdapter,
        CosyVoiceAdapter,
        MiniMaxTTSAdapter,
        VolcEngineTTSAdapter,
    ])
    @pytest.mark.asyncio
    async def test_list_voices_returns_defaults(self, adapter_cls):
        """未配置 API Key 时应返回预定义的默认语音列表"""
        adapter = adapter_cls()
        voices = await adapter.list_voices()
        assert isinstance(voices, list)
        # 所有适配器都有预定义的默认语音
        for v in voices:
            assert isinstance(v, VoiceInfo)

    @pytest.mark.parametrize("adapter_cls", [
        FishSpeechAdapter,
        CosyVoiceAdapter,
        MiniMaxTTSAdapter,
        VolcEngineTTSAdapter,
    ])
    def test_is_tts_adapter_subclass(self, adapter_cls):
        assert issubclass(adapter_cls, TTSAdapter)


# ============================================================
# assign_voices_to_characters 测试
# ============================================================

class TestAssignVoicesToCharacters:
    """测试角色语音分配逻辑 (Property 9: 角色语音分配唯一性)"""

    def _make_voices(self, n: int) -> list[VoiceInfo]:
        """创建 n 个测试语音"""
        return [
            VoiceInfo(id=f"voice-{i}", name=f"Voice {i}", language="zh-CN", gender="Female" if i % 2 == 0 else "Male")
            for i in range(n)
        ]

    def test_empty_characters(self):
        """空角色列表返回空字典"""
        voices = self._make_voices(3)
        result = assign_voices_to_characters([], voices)
        assert result == {}

    def test_empty_voices_raises(self):
        """空语音列表应抛出 ValueError"""
        with pytest.raises(ValueError, match="可用语音列表不能为空"):
            assign_voices_to_characters(["角色A"], [])

    def test_single_character(self):
        """单个角色分配第一个语音"""
        voices = self._make_voices(3)
        result = assign_voices_to_characters(["角色A"], voices)
        assert result == {"角色A": "voice-0"}

    def test_multiple_characters_get_different_voices(self):
        """多个角色应获得不同的 voice_id（角色数 <= 语音数时）"""
        voices = self._make_voices(5)
        characters = ["角色A", "角色B", "角色C"]
        result = assign_voices_to_characters(characters, voices)

        # 每个角色都有分配
        assert len(result) == 3
        assert set(result.keys()) == {"角色A", "角色B", "角色C"}

        # 所有 voice_id 不同
        voice_ids = list(result.values())
        assert len(voice_ids) == len(set(voice_ids)), "不同角色应分配不同的 voice_id"

    def test_characters_equal_to_voices(self):
        """角色数等于语音数时，每个角色获得唯一语音"""
        voices = self._make_voices(3)
        characters = ["A", "B", "C"]
        result = assign_voices_to_characters(characters, voices)
        voice_ids = list(result.values())
        assert len(voice_ids) == len(set(voice_ids))

    def test_more_characters_than_voices_wraps_around(self):
        """角色数超过语音数时，循环复用语音"""
        voices = self._make_voices(2)
        characters = ["A", "B", "C", "D"]
        result = assign_voices_to_characters(characters, voices)
        assert len(result) == 4
        # 前两个不同，后面循环
        assert result["A"] == "voice-0"
        assert result["B"] == "voice-1"
        assert result["C"] == "voice-0"
        assert result["D"] == "voice-1"

    def test_duplicate_character_names_deduplicated(self):
        """重复的角色名称应去重"""
        voices = self._make_voices(5)
        characters = ["角色A", "角色B", "角色A", "角色C", "角色B"]
        result = assign_voices_to_characters(characters, voices)
        assert len(result) == 3
        # 去重后的唯一角色应获得不同语音
        voice_ids = list(result.values())
        assert len(voice_ids) == len(set(voice_ids))

    def test_assignment_is_deterministic(self):
        """相同输入应产生相同的分配结果"""
        voices = self._make_voices(5)
        characters = ["角色A", "角色B", "角色C"]
        result1 = assign_voices_to_characters(characters, voices)
        result2 = assign_voices_to_characters(characters, voices)
        assert result1 == result2


# ============================================================
# TTSService 管理器测试
# ============================================================

class TestTTSService:
    """测试 TTSService 管理器"""

    def test_default_adapters_registered(self):
        """默认应注册 edge-tts 和 chattts 适配器"""
        service = TTSService()
        assert "edge-tts" in service.adapters
        assert "chattts" in service.adapters
        assert isinstance(service.adapters["edge-tts"], EdgeTTSAdapter)
        assert isinstance(service.adapters["chattts"], ChatTTSAdapter)

    def test_register_adapter(self):
        """注册新适配器"""
        service = TTSService()
        mock_adapter = MockTTSAdapter(name="custom-tts")
        service.register_adapter("custom-tts", mock_adapter)
        assert "custom-tts" in service.adapters
        assert service.adapters["custom-tts"] is mock_adapter

    def test_register_adapter_overwrites_existing(self):
        """注册同名适配器应覆盖"""
        service = TTSService()
        mock_adapter = MockTTSAdapter(name="edge-tts")
        service.register_adapter("edge-tts", mock_adapter)
        assert service.adapters["edge-tts"] is mock_adapter

    def test_unregister_adapter(self):
        """注销适配器"""
        service = TTSService()
        service.unregister_adapter("edge-tts")
        assert "edge-tts" not in service.adapters

    def test_unregister_nonexistent_adapter_no_error(self):
        """注销不存在的适配器不应报错"""
        service = TTSService()
        service.unregister_adapter("nonexistent")  # should not raise

    def test_list_engines(self):
        """列出所有已注册引擎"""
        service = TTSService()
        engines = service.list_engines()
        assert len(engines) >= 2
        engine_names = [e.name for e in engines]
        assert "edge-tts" in engine_names
        assert "chattts" in engine_names
        assert all(isinstance(e, EngineInfo) for e in engines)

    @pytest.mark.asyncio
    async def test_generate_speech_with_mock_adapter(self, tmp_path):
        """使用 mock 适配器测试语音生成"""
        service = TTSService(projects_dir=tmp_path)
        mock_adapter = MockTTSAdapter()
        service.register_adapter("mock", mock_adapter)

        result = await service.generate_speech("你好", "mock-voice-1", engine="mock")
        assert result.endswith(".wav")
        assert len(mock_adapter.generate_calls) == 1
        assert mock_adapter.generate_calls[0]["text"] == "你好"
        assert mock_adapter.generate_calls[0]["voice_id"] == "mock-voice-1"

    @pytest.mark.asyncio
    async def test_generate_speech_with_project_and_scene(self, tmp_path):
        """指定 project_id 和 scene_id 时，输出到项目目录"""
        service = TTSService(projects_dir=tmp_path)
        mock_adapter = MockTTSAdapter()
        service.register_adapter("mock", mock_adapter)

        result = await service.generate_speech(
            "你好", "mock-voice-1", engine="mock",
            project_id="proj-1", scene_id="scene-1",
        )
        # 应该输出到 projects_dir/proj-1/audio/scene_scene-1.wav
        assert "proj-1" in result
        assert "audio" in result
        assert "scene_scene-1" in result

    @pytest.mark.asyncio
    async def test_generate_speech_unknown_engine_raises(self):
        """使用未注册的引擎应抛出 TTSEngineNotFoundError"""
        service = TTSService()
        with pytest.raises(TTSEngineNotFoundError) as exc_info:
            await service.generate_speech("你好", "voice-1", engine="nonexistent")
        assert "nonexistent" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_list_voices_with_mock_adapter(self):
        """列出 mock 适配器的语音"""
        service = TTSService()
        mock_adapter = MockTTSAdapter()
        service.register_adapter("mock", mock_adapter)

        voices = await service.list_voices("mock")
        assert len(voices) == 3
        assert all(isinstance(v, VoiceInfo) for v in voices)

    @pytest.mark.asyncio
    async def test_list_voices_unknown_engine_raises(self):
        """列出未注册引擎的语音应抛出 TTSEngineNotFoundError"""
        service = TTSService()
        with pytest.raises(TTSEngineNotFoundError):
            await service.list_voices("nonexistent")

    @pytest.mark.asyncio
    async def test_assign_voices_with_mock_adapter(self):
        """测试通过 TTSService 分配角色语音"""
        service = TTSService()
        mock_adapter = MockTTSAdapter(voices=[
            VoiceInfo(id="v1", name="V1", language="zh-CN", gender="Female"),
            VoiceInfo(id="v2", name="V2", language="zh-CN", gender="Male"),
            VoiceInfo(id="v3", name="V3", language="zh-CN", gender="Female"),
        ])
        service.register_adapter("mock", mock_adapter)

        assignment = await service.assign_voices(["角色A", "角色B"], engine="mock")
        assert len(assignment) == 2
        assert assignment["角色A"] != assignment["角色B"]

    @pytest.mark.asyncio
    async def test_assign_voices_unknown_engine_raises(self):
        """分配语音时使用未注册引擎应抛出错误"""
        service = TTSService()
        with pytest.raises(TTSEngineNotFoundError):
            await service.assign_voices(["角色A"], engine="nonexistent")


# ============================================================
# 异常类测试
# ============================================================

class TestExceptions:
    """测试自定义异常类"""

    def test_tts_error(self):
        err = TTSError("test error", code="TEST", retryable=True)
        assert str(err) == "test error"
        assert err.code == "TEST"
        assert err.retryable is True

    def test_tts_dependency_error(self):
        err = TTSDependencyError("edge-tts", "edge-tts")
        assert "edge-tts" in str(err)
        assert err.code == "TTS_DEPENDENCY_ERROR"
        assert err.retryable is False

    def test_tts_engine_not_found_error(self):
        err = TTSEngineNotFoundError("unknown-engine")
        assert "unknown-engine" in str(err)
        assert err.code == "TTS_ENGINE_NOT_FOUND"

    def test_tts_generation_error(self):
        err = TTSGenerationError("生成失败")
        assert str(err) == "生成失败"
        assert err.code == "TTS_GENERATION_ERROR"
        assert err.retryable is True
