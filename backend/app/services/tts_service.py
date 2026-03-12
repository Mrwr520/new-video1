"""TTS 语音配音服务（可插拔适配器架构）

采用适配器模式，支持多种 TTS 引擎的注册和切换。
当前实现免费引擎（Edge-TTS、ChatTTS），并预留主流收费模型的适配器骨架。

Requirements:
    6.1: TTS_Engine SHALL 为每段文本生成对应的语音音频
    6.2: TTS_Engine SHALL 为不同角色分配不同的语音风格
    6.4: WHEN 用户选择语音引擎, TTS_Engine SHALL 使用指定的引擎生成语音
"""

import asyncio
import logging
import os
import tempfile
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 默认项目文件存储根目录
DEFAULT_PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"

# ============================================================
# 可选依赖导入
# ============================================================

_edge_tts_available = False
try:
    import edge_tts  # type: ignore[import-untyped]
    _edge_tts_available = True
except ImportError:
    edge_tts = None  # type: ignore[assignment]

_chattts_available = False
try:
    import ChatTTS  # type: ignore[import-untyped]
    _chattts_available = True
except ImportError:
    ChatTTS = None  # type: ignore[assignment]


# ============================================================
# 数据类
# ============================================================

@dataclass
class VoiceInfo:
    """语音信息"""
    id: str
    name: str
    language: str
    gender: str
    preview_url: Optional[str] = None


@dataclass
class EngineInfo:
    """引擎信息"""
    name: str
    display_name: str
    is_paid: bool
    supported_languages: list[str] = field(default_factory=list)
    requires_api_key: bool = False
    description: str = ""


# ============================================================
# 异常类
# ============================================================

class TTSError(Exception):
    """TTS 服务基础异常"""

    def __init__(self, message: str, code: str = "TTS_ERROR", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class TTSDependencyError(TTSError):
    """TTS 引擎依赖缺失"""

    def __init__(self, engine: str, package: str):
        super().__init__(
            f"TTS 引擎 '{engine}' 依赖缺失，请安装: pip install {package}",
            code="TTS_DEPENDENCY_ERROR",
            retryable=False,
        )


class TTSEngineNotFoundError(TTSError):
    """TTS 引擎未注册"""

    def __init__(self, engine: str):
        super().__init__(
            f"TTS 引擎 '{engine}' 未注册",
            code="TTS_ENGINE_NOT_FOUND",
            retryable=False,
        )


class TTSGenerationError(TTSError):
    """语音生成失败"""

    def __init__(self, message: str = "语音生成失败"):
        super().__init__(message, code="TTS_GENERATION_ERROR", retryable=True)


# ============================================================
# TTSAdapter 抽象基类
# ============================================================

class TTSAdapter(ABC):
    """TTS 适配器基类，所有引擎实现此接口。"""

    @abstractmethod
    async def generate_speech(self, text: str, voice_id: str, output_path: Optional[str] = None) -> str:
        """生成语音音频，返回文件路径。

        Args:
            text: 要转换的文本
            voice_id: 语音 ID
            output_path: 可选的输出文件路径，不指定则自动生成

        Returns:
            生成的音频文件路径
        """
        ...

    @abstractmethod
    async def list_voices(self) -> list[VoiceInfo]:
        """列出可用的语音列表。"""
        ...

    @abstractmethod
    def get_engine_info(self) -> EngineInfo:
        """返回引擎信息。"""
        ...


# ============================================================
# EdgeTTSAdapter（免费引擎）
# ============================================================

class EdgeTTSAdapter(TTSAdapter):
    """Edge-TTS 适配器（微软免费 TTS 引擎）。

    使用 edge-tts 库调用微软 Edge 浏览器的在线 TTS 服务。
    支持多语言、多音色，无需 API Key。
    """

    # 预定义的常用中文语音列表（用于离线场景或快速选择）
    DEFAULT_VOICES = [
        VoiceInfo(id="zh-CN-XiaoxiaoNeural", name="晓晓（女）", language="zh-CN", gender="Female"),
        VoiceInfo(id="zh-CN-YunxiNeural", name="云希（男）", language="zh-CN", gender="Male"),
        VoiceInfo(id="zh-CN-YunjianNeural", name="云健（男）", language="zh-CN", gender="Male"),
        VoiceInfo(id="zh-CN-XiaoyiNeural", name="晓伊（女）", language="zh-CN", gender="Female"),
        VoiceInfo(id="zh-CN-YunyangNeural", name="云扬（男）", language="zh-CN", gender="Male"),
        VoiceInfo(id="zh-CN-XiaochenNeural", name="晓辰（女）", language="zh-CN", gender="Female"),
        VoiceInfo(id="zh-CN-XiaohanNeural", name="晓涵（女）", language="zh-CN", gender="Female"),
        VoiceInfo(id="zh-CN-XiaomengNeural", name="晓梦（女）", language="zh-CN", gender="Female"),
        VoiceInfo(id="zh-CN-XiaomoNeural", name="晓墨（女）", language="zh-CN", gender="Female"),
        VoiceInfo(id="zh-CN-XiaoqiuNeural", name="晓秋（女）", language="zh-CN", gender="Female"),
        VoiceInfo(id="zh-CN-XiaoruiNeural", name="晓睿（女）", language="zh-CN", gender="Female"),
        VoiceInfo(id="zh-CN-XiaoshuangNeural", name="晓双（女/童声）", language="zh-CN", gender="Female"),
        VoiceInfo(id="zh-CN-XiaoxuanNeural", name="晓萱（女）", language="zh-CN", gender="Female"),
        VoiceInfo(id="zh-CN-XiaoyanNeural", name="晓颜（女）", language="zh-CN", gender="Female"),
        VoiceInfo(id="zh-CN-XiaozhenNeural", name="晓甄（女）", language="zh-CN", gender="Female"),
        VoiceInfo(id="zh-CN-YunfengNeural", name="云枫（男）", language="zh-CN", gender="Male"),
        VoiceInfo(id="zh-CN-YunhaoNeural", name="云皓（男）", language="zh-CN", gender="Male"),
        VoiceInfo(id="zh-CN-YunxiaNeural", name="云夏（男）", language="zh-CN", gender="Male"),
        VoiceInfo(id="zh-CN-YunzeNeural", name="云泽（男）", language="zh-CN", gender="Male"),
        VoiceInfo(id="en-US-JennyNeural", name="Jenny (Female)", language="en-US", gender="Female"),
        VoiceInfo(id="en-US-GuyNeural", name="Guy (Male)", language="en-US", gender="Male"),
        VoiceInfo(id="ja-JP-NanamiNeural", name="七海（女）", language="ja-JP", gender="Female"),
        VoiceInfo(id="ja-JP-KeitaNeural", name="圭太（男）", language="ja-JP", gender="Male"),
    ]

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir

    async def generate_speech(self, text: str, voice_id: str, output_path: Optional[str] = None) -> str:
        """使用 Edge-TTS 生成语音。"""
        if not _edge_tts_available:
            raise TTSDependencyError("edge-tts", "edge-tts")

        if not text or not text.strip():
            raise TTSGenerationError("文本内容不能为空")

        # 确定输出路径
        if output_path is None:
            out_dir = self.output_dir or Path(tempfile.gettempdir()) / "tts_output"
            out_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(out_dir / f"edge_tts_{uuid.uuid4().hex[:8]}.mp3")

        try:
            communicate = edge_tts.Communicate(text, voice_id)
            await communicate.save(output_path)
            return output_path
        except Exception as e:
            raise TTSGenerationError(f"Edge-TTS 生成失败: {e}")

    async def list_voices(self) -> list[VoiceInfo]:
        """列出 Edge-TTS 可用语音。

        如果 edge-tts 可用，尝试在线获取完整列表（过滤为常用语言）；
        否则返回预定义的常用语音列表。
        优先显示中文语音，其次英文、日文。
        """
        if not _edge_tts_available:
            return list(self.DEFAULT_VOICES)

        # 只显示这些语言的语音，避免用户选到不支持中文的语音导致生成失败
        SUPPORTED_LOCALES = {"zh-CN", "zh-TW", "zh-HK", "en-US", "en-GB", "ja-JP", "ko-KR"}
        # 排序优先级：中文 > 英文 > 日文 > 韩文
        LOCALE_PRIORITY = {"zh-CN": 0, "zh-TW": 1, "zh-HK": 2, "en-US": 3, "en-GB": 4, "ja-JP": 5, "ko-KR": 6}

        try:
            voices_data = await edge_tts.list_voices()
            voices = []
            for v in voices_data:
                locale = v.get("Locale", "unknown")
                if locale not in SUPPORTED_LOCALES:
                    continue
                voices.append(VoiceInfo(
                    id=v["ShortName"],
                    name=v.get("FriendlyName", v["ShortName"]),
                    language=locale,
                    gender=v.get("Gender", "unknown"),
                ))
            # 按语言优先级排序
            voices.sort(key=lambda v: LOCALE_PRIORITY.get(v.language, 99))
            if voices:
                return voices
        except Exception:
            logger.warning("获取 Edge-TTS 在线语音列表失败，使用预定义列表")
        return list(self.DEFAULT_VOICES)

    def get_engine_info(self) -> EngineInfo:
        return EngineInfo(
            name="edge-tts",
            display_name="Edge-TTS（微软免费）",
            is_paid=False,
            supported_languages=["zh-CN", "en-US", "ja-JP", "ko-KR", "fr-FR", "de-DE"],
            requires_api_key=False,
            description="微软 Edge 浏览器内置 TTS 引擎，免费使用，支持多语言多音色",
        )


# ============================================================
# ChatTTSAdapter（免费本地引擎）
# ============================================================

class ChatTTSAdapter(TTSAdapter):
    """ChatTTS 适配器（免费，本地运行）。

    ChatTTS 是一个开源的中文语音合成模型，支持本地 GPU 推理。
    需要安装 ChatTTS 包和 PyTorch。
    """

    DEFAULT_VOICES = [
        VoiceInfo(id="chattts-default", name="默认音色", language="zh-CN", gender="Unknown"),
        VoiceInfo(id="chattts-seed-1", name="音色种子 1", language="zh-CN", gender="Female"),
        VoiceInfo(id="chattts-seed-2", name="音色种子 2", language="zh-CN", gender="Male"),
        VoiceInfo(id="chattts-seed-3", name="音色种子 3", language="zh-CN", gender="Female"),
        VoiceInfo(id="chattts-seed-4", name="音色种子 4", language="zh-CN", gender="Male"),
    ]

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir
        self._model = None
        self._loaded = False

    async def generate_speech(self, text: str, voice_id: str, output_path: Optional[str] = None) -> str:
        """使用 ChatTTS 生成语音。"""
        if not _chattts_available:
            raise TTSDependencyError("chattts", "ChatTTS")

        if not text or not text.strip():
            raise TTSGenerationError("文本内容不能为空")

        if output_path is None:
            out_dir = self.output_dir or Path(tempfile.gettempdir()) / "tts_output"
            out_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(out_dir / f"chattts_{uuid.uuid4().hex[:8]}.wav")

        try:
            if not self._loaded:
                await self._load_model()

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self._generate_sync, text, voice_id, output_path
            )
            return output_path
        except TTSError:
            raise
        except Exception as e:
            raise TTSGenerationError(f"ChatTTS 生成失败: {e}")

    async def _load_model(self) -> None:
        """加载 ChatTTS 模型。"""
        try:
            self._model = ChatTTS.Chat()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._model.load)
            self._loaded = True
        except Exception as e:
            raise TTSGenerationError(f"ChatTTS 模型加载失败: {e}")

    def _generate_sync(self, text: str, voice_id: str, output_path: str) -> None:
        """同步生成语音（在线程池中执行）。"""
        import numpy as np
        import wave

        # 根据 voice_id 设置种子以获得不同音色
        seed = self._voice_id_to_seed(voice_id)
        params = ChatTTS.Chat.InferCodeParams(spk_emb=None, temperature=0.3)
        if seed is not None:
            import torch
            torch.manual_seed(seed)

        wavs = self._model.infer([text], params_infer_code=params)
        audio_data = wavs[0]

        # 保存为 WAV 文件
        if isinstance(audio_data, np.ndarray):
            audio_data = (audio_data * 32767).astype(np.int16)
            with wave.open(output_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(audio_data.tobytes())

    @staticmethod
    def _voice_id_to_seed(voice_id: str) -> Optional[int]:
        """将 voice_id 转换为随机种子。"""
        seed_map = {
            "chattts-default": None,
            "chattts-seed-1": 42,
            "chattts-seed-2": 123,
            "chattts-seed-3": 456,
            "chattts-seed-4": 789,
        }
        return seed_map.get(voice_id)

    async def list_voices(self) -> list[VoiceInfo]:
        return list(self.DEFAULT_VOICES)

    def get_engine_info(self) -> EngineInfo:
        return EngineInfo(
            name="chattts",
            display_name="ChatTTS（本地免费）",
            is_paid=False,
            supported_languages=["zh-CN", "en-US"],
            requires_api_key=False,
            description="开源中文语音合成模型，本地 GPU 推理，免费使用",
        )


# ============================================================
# 预留的收费模型适配器骨架
# ============================================================

class FishSpeechAdapter(TTSAdapter):
    """Fish Audio 适配器（收费，高质量多语言语音合成 + 语音克隆）。

    API 文档: https://docs.fish.audio
    - POST https://api.fish.audio/v1/tts  (TTS 合成)
    - GET  https://api.fish.audio/model   (语音模型列表)

    需要在 https://fish.audio 注册获取 API Key。
    """

    # 预定义的常用系统语音
    DEFAULT_VOICES = [
        VoiceInfo(id="default", name="默认语音", language="zh-CN", gender="Female"),
        VoiceInfo(id="speech-1", name="中文女声 1", language="zh-CN", gender="Female"),
        VoiceInfo(id="speech-2", name="中文男声 1", language="zh-CN", gender="Male"),
    ]

    def __init__(self, api_key: str = "", api_url: str = "https://api.fish.audio"):
        self.api_key = api_key
        self.api_url = api_url.rstrip("/")

    async def generate_speech(self, text: str, voice_id: str, output_path: Optional[str] = None) -> str:
        """调用 Fish Audio TTS API 生成语音。"""
        if not self.api_key:
            raise TTSError("Fish Audio API Key 未配置", code="TTS_NO_API_KEY")
        if not text or not text.strip():
            raise TTSGenerationError("文本内容不能为空")

        if output_path is None:
            out_dir = Path(tempfile.gettempdir()) / "tts_output"
            out_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(out_dir / f"fish_{uuid.uuid4().hex[:8]}.mp3")

        import httpx
        url = f"{self.api_url}/v1/tts"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "reference_id": voice_id if voice_id != "default" else None,
            "format": "mp3",
            "latency": "normal",
        }
        # 移除 None 值
        payload = {k: v for k, v in payload.items() if v is not None}

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code != 200:
                    raise TTSGenerationError(f"Fish Audio API 错误: {resp.status_code} - {resp.text[:200]}")
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(resp.content)
            return output_path
        except TTSError:
            raise
        except Exception as e:
            raise TTSGenerationError(f"Fish Audio 生成失败: {e}")

    async def list_voices(self) -> list[VoiceInfo]:
        """获取 Fish Audio 可用语音模型列表。"""
        if not self.api_key:
            return list(self.DEFAULT_VOICES)
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    f"{self.api_url}/model",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    params={"page_size": 50, "title": "", "tag": "zh"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("items", [])
                    voices = []
                    for item in items[:30]:
                        voices.append(VoiceInfo(
                            id=item.get("_id", ""),
                            name=item.get("title", "未知"),
                            language="zh-CN",
                            gender="Unknown",
                        ))
                    if voices:
                        return voices
        except Exception:
            logger.warning("获取 Fish Audio 语音列表失败，使用默认列表")
        return list(self.DEFAULT_VOICES)

    def get_engine_info(self) -> EngineInfo:
        return EngineInfo(
            name="fish-speech",
            display_name="Fish Audio（收费）",
            is_paid=True,
            supported_languages=["zh-CN", "en-US", "ja-JP", "ko-KR"],
            requires_api_key=True,
            description="高质量多语言语音合成，支持语音克隆。注册: https://fish.audio",
        )


class CosyVoiceAdapter(TTSAdapter):
    """CosyVoice (阿里通义) 适配器（收费，兼容 OpenAI TTS API 格式）。

    阿里 DashScope 平台提供 CosyVoice 语音合成服务。
    API 文档: https://help.aliyun.com/zh/model-studio/developer-reference/cosyvoice

    使用 OpenAI 兼容格式:
    POST {base_url}/v1/audio/speech
    """

    DEFAULT_VOICES = [
        VoiceInfo(id="longxiaochun", name="龙小淳（女）", language="zh-CN", gender="Female"),
        VoiceInfo(id="longxiaoxia", name="龙小夏（女）", language="zh-CN", gender="Female"),
        VoiceInfo(id="longxiaobai", name="龙小白（男）", language="zh-CN", gender="Male"),
        VoiceInfo(id="longlaotie", name="龙老铁（男）", language="zh-CN", gender="Male"),
        VoiceInfo(id="longshu", name="龙叔（男）", language="zh-CN", gender="Male"),
        VoiceInfo(id="longjielidou", name="龙杰力豆（男）", language="zh-CN", gender="Male"),
        VoiceInfo(id="loongstella", name="Stella（女/英文）", language="en-US", gender="Female"),
    ]

    def __init__(self, api_key: str = "", api_url: str = "https://dashscope.aliyuncs.com/compatible-mode"):
        self.api_key = api_key
        self.api_url = api_url.rstrip("/")

    async def generate_speech(self, text: str, voice_id: str, output_path: Optional[str] = None) -> str:
        """调用阿里 DashScope CosyVoice API 生成语音。"""
        if not self.api_key:
            raise TTSError("CosyVoice API Key 未配置", code="TTS_NO_API_KEY")
        if not text or not text.strip():
            raise TTSGenerationError("文本内容不能为空")

        if output_path is None:
            out_dir = Path(tempfile.gettempdir()) / "tts_output"
            out_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(out_dir / f"cosyvoice_{uuid.uuid4().hex[:8]}.mp3")

        import httpx
        url = f"{self.api_url}/v1/audio/speech"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "cosyvoice-v1",
            "input": text,
            "voice": voice_id or "longxiaochun",
            "response_format": "mp3",
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code != 200:
                    raise TTSGenerationError(f"CosyVoice API 错误: {resp.status_code} - {resp.text[:200]}")
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(resp.content)
            return output_path
        except TTSError:
            raise
        except Exception as e:
            raise TTSGenerationError(f"CosyVoice 生成失败: {e}")

    async def list_voices(self) -> list[VoiceInfo]:
        return list(self.DEFAULT_VOICES)

    def get_engine_info(self) -> EngineInfo:
        return EngineInfo(
            name="cosyvoice",
            display_name="CosyVoice（阿里通义）",
            is_paid=True,
            supported_languages=["zh-CN", "en-US", "ja-JP", "ko-KR"],
            requires_api_key=True,
            description="阿里通义 CosyVoice 语音合成。注册: https://dashscope.console.aliyun.com",
        )


class MiniMaxTTSAdapter(TTSAdapter):
    """MiniMax TTS 适配器（收费，情感丰富语音合成）。

    API 文档: https://platform.minimaxi.com/document/T2A%20V2
    - POST https://api.minimax.chat/v1/t2a_v2?GroupId={group_id}

    响应格式（JSON）:
    {
      "base_resp": {"status_code": 0, "status_msg": "success"},
      "data": {
        "audio": "<hex编码的音频数据>",
        "status": 1  (1=最后一段)
      },
      "extra_info": {"audio_file": ..., "audio_size": ..., "bitrate": ...}
    }

    注意: audio 字段是十六进制编码的 MP3 数据，需要 bytes.fromhex() 解码。
    需要 API Key 和 Group ID（从 MiniMax 开放平台获取）。
    """

    DEFAULT_VOICES = [
        VoiceInfo(id="male-qn-qingse", name="青涩青年（男）", language="zh-CN", gender="Male"),
        VoiceInfo(id="male-qn-jingying", name="精英青年（男）", language="zh-CN", gender="Male"),
        VoiceInfo(id="male-qn-badao", name="霸道青年（男）", language="zh-CN", gender="Male"),
        VoiceInfo(id="male-qn-daxuesheng", name="大学生（男）", language="zh-CN", gender="Male"),
        VoiceInfo(id="female-shaonv", name="少女（女）", language="zh-CN", gender="Female"),
        VoiceInfo(id="female-yujie", name="御姐（女）", language="zh-CN", gender="Female"),
        VoiceInfo(id="female-chengshu", name="成熟女性（女）", language="zh-CN", gender="Female"),
        VoiceInfo(id="female-tianmei", name="甜美女声（女）", language="zh-CN", gender="Female"),
        VoiceInfo(id="presenter_male", name="男性主持人", language="zh-CN", gender="Male"),
        VoiceInfo(id="presenter_female", name="女性主持人", language="zh-CN", gender="Female"),
    ]

    def __init__(self, api_key: str = "", group_id: str = "", api_url: str = "https://api.minimax.chat"):
        self.api_key = api_key
        self.group_id = group_id
        self.api_url = api_url.rstrip("/")

    async def generate_speech(self, text: str, voice_id: str, output_path: Optional[str] = None) -> str:
        """调用 MiniMax T2A V2 API 生成语音。

        MiniMax 返回 JSON，其中 data.audio 是十六进制编码的 MP3 音频。
        """
        if not self.api_key:
            raise TTSError("MiniMax API Key 未配置", code="TTS_NO_API_KEY")
        if not self.group_id:
            raise TTSError("MiniMax Group ID 未配置", code="TTS_NO_GROUP_ID")
        if not text or not text.strip():
            raise TTSGenerationError("文本内容不能为空")

        if output_path is None:
            out_dir = Path(tempfile.gettempdir()) / "tts_output"
            out_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(out_dir / f"minimax_{uuid.uuid4().hex[:8]}.mp3")

        import httpx
        url = f"{self.api_url}/v1/t2a_v2?GroupId={self.group_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "speech-01-turbo",
            "text": text,
            "stream": False,
            "voice_setting": {
                "voice_id": voice_id or "male-qn-qingse",
                "speed": 1.0,
                "vol": 1.0,
                "pitch": 0,
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code != 200:
                    raise TTSGenerationError(f"MiniMax API HTTP 错误: {resp.status_code} - {resp.text[:200]}")

                data = resp.json()
                # 检查业务状态码
                base_resp = data.get("base_resp", {})
                if base_resp.get("status_code", -1) != 0:
                    err_msg = base_resp.get("status_msg", "未知错误")
                    raise TTSGenerationError(f"MiniMax API 业务错误: {err_msg}")

                # 提取十六进制编码的音频数据
                audio_hex = data.get("data", {}).get("audio")
                if not audio_hex:
                    raise TTSGenerationError("MiniMax API 返回数据中没有音频内容")

                # 十六进制解码为二进制 MP3
                audio_bytes = bytes.fromhex(audio_hex)
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(audio_bytes)

            return output_path
        except TTSError:
            raise
        except Exception as e:
            raise TTSGenerationError(f"MiniMax 生成失败: {e}")

    async def list_voices(self) -> list[VoiceInfo]:
        return list(self.DEFAULT_VOICES)

    def get_engine_info(self) -> EngineInfo:
        return EngineInfo(
            name="minimax-tts",
            display_name="MiniMax TTS（情感丰富）",
            is_paid=True,
            supported_languages=["zh-CN", "en-US"],
            requires_api_key=True,
            description="MiniMax 情感丰富语音合成，支持多种音色和情感控制。注册: https://platform.minimaxi.com",
        )


class VolcEngineTTSAdapter(TTSAdapter):
    """火山引擎 TTS 适配器（收费，字节跳动，抖音同款音色）。

    API 文档: https://www.volcengine.com/docs/6561/79823
    - POST https://openspeech.bytedance.com/api/v1/tts

    请求头需要 Authorization: Bearer;{access_token}
    请求体:
    {
      "app": {"appid": "xxx", "token": "access_token", "cluster": "volcano_tts"},
      "user": {"uid": "xxx"},
      "audio": {"voice_type": "xxx", "encoding": "mp3", "speed_ratio": 1.0},
      "request": {"reqid": "xxx", "text": "xxx", "operation": "query"}
    }

    响应格式（JSON）:
    {
      "code": 3000,  (3000=成功)
      "message": "Success",
      "data": "<base64编码的音频数据>"
    }

    注意: data 字段是 base64 编码的音频，需要 base64.b64decode() 解码。
    需要 App ID 和 Access Token（从火山引擎控制台获取）。
    """

    DEFAULT_VOICES = [
        VoiceInfo(id="zh_female_cancan", name="灿灿（女）", language="zh-CN", gender="Female"),
        VoiceInfo(id="zh_male_chunhou", name="淳厚（男）", language="zh-CN", gender="Male"),
        VoiceInfo(id="zh_female_shuangkuai", name="爽快（女）", language="zh-CN", gender="Female"),
        VoiceInfo(id="zh_male_yangguang", name="阳光（男）", language="zh-CN", gender="Male"),
        VoiceInfo(id="zh_female_wenrou", name="温柔（女）", language="zh-CN", gender="Female"),
        VoiceInfo(id="zh_male_qinqie", name="亲切（男）", language="zh-CN", gender="Male"),
        VoiceInfo(id="zh_female_story", name="故事女声", language="zh-CN", gender="Female"),
        VoiceInfo(id="zh_male_story", name="故事男声", language="zh-CN", gender="Male"),
    ]

    def __init__(self, app_id: str = "", access_token: str = "",
                 api_url: str = "https://openspeech.bytedance.com"):
        self.app_id = app_id
        self.access_token = access_token
        self.api_url = api_url.rstrip("/")

    async def generate_speech(self, text: str, voice_id: str, output_path: Optional[str] = None) -> str:
        """调用火山引擎 TTS API 生成语音。

        火山引擎返回 JSON，其中 data 是 base64 编码的音频。
        """
        if not self.access_token:
            raise TTSError("火山引擎 Access Token 未配置", code="TTS_NO_API_KEY")
        if not self.app_id:
            raise TTSError("火山引擎 App ID 未配置", code="TTS_NO_APP_ID")
        if not text or not text.strip():
            raise TTSGenerationError("文本内容不能为空")

        if output_path is None:
            out_dir = Path(tempfile.gettempdir()) / "tts_output"
            out_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(out_dir / f"volc_{uuid.uuid4().hex[:8]}.mp3")

        import base64
        import httpx

        url = f"{self.api_url}/api/v1/tts"
        headers = {
            "Authorization": f"Bearer;{self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "app": {
                "appid": self.app_id,
                "token": self.access_token,
                "cluster": "volcano_tts",
            },
            "user": {
                "uid": "ai-video-generator",
            },
            "audio": {
                "voice_type": voice_id or "zh_female_cancan",
                "encoding": "mp3",
                "speed_ratio": 1.0,
            },
            "request": {
                "reqid": uuid.uuid4().hex,
                "text": text,
                "operation": "query",
            },
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code != 200:
                    raise TTSGenerationError(f"火山引擎 API HTTP 错误: {resp.status_code} - {resp.text[:200]}")

                data = resp.json()
                # 检查业务状态码 (3000 = 成功)
                code = data.get("code", -1)
                if code != 3000:
                    err_msg = data.get("message", "未知错误")
                    raise TTSGenerationError(f"火山引擎 API 错误 (code={code}): {err_msg}")

                # 提取 base64 编码的音频数据
                audio_b64 = data.get("data")
                if not audio_b64:
                    raise TTSGenerationError("火山引擎 API 返回数据中没有音频内容")

                # base64 解码为二进制 MP3
                audio_bytes = base64.b64decode(audio_b64)
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(audio_bytes)

            return output_path
        except TTSError:
            raise
        except Exception as e:
            raise TTSGenerationError(f"火山引擎生成失败: {e}")

    async def list_voices(self) -> list[VoiceInfo]:
        return list(self.DEFAULT_VOICES)

    def get_engine_info(self) -> EngineInfo:
        return EngineInfo(
            name="volcengine-tts",
            display_name="火山引擎 TTS（字节跳动）",
            is_paid=True,
            supported_languages=["zh-CN", "en-US", "ja-JP"],
            requires_api_key=True,
            description="字节跳动火山引擎语音合成，抖音同款音色。注册: https://console.volcengine.com",
        )


# ============================================================
# 角色语音分配逻辑
# ============================================================

def assign_voices_to_characters(
    character_names: list[str],
    available_voices: list[VoiceInfo],
) -> dict[str, str]:
    """为不同角色分配不同的 voice_id。

    策略：
    1. 从可用语音列表中轮询分配，确保不同角色获得不同 voice_id
    2. 如果角色数量超过可用语音数量，则循环复用（但尽量保证唯一性）

    Property 9: 角色语音分配唯一性
    - 当角色数 <= 可用语音数时，每个角色的 voice_id 必须不同

    Args:
        character_names: 角色名称列表
        available_voices: 可用语音列表

    Returns:
        dict 映射 {角色名称: voice_id}

    Raises:
        ValueError: 角色列表或语音列表为空
    """
    if not character_names:
        return {}

    if not available_voices:
        raise ValueError("可用语音列表不能为空")

    # 去重角色名称，保持顺序
    seen = set()
    unique_names = []
    for name in character_names:
        if name not in seen:
            seen.add(name)
            unique_names.append(name)

    assignment: dict[str, str] = {}
    for idx, name in enumerate(unique_names):
        voice_idx = idx % len(available_voices)
        assignment[name] = available_voices[voice_idx].id

    return assignment


# ============================================================
# TTSService 管理器
# ============================================================

class TTSService:
    """TTS 服务管理器，管理引擎注册、选择和调用。

    Requirements:
        6.1: 为每段文本生成对应的语音音频
        6.2: 为不同角色分配不同的语音风格
        6.4: 使用用户指定的引擎生成语音
    """

    def __init__(self, projects_dir: Optional[Path] = None, config: Optional[dict] = None):
        self.adapters: dict[str, TTSAdapter] = {}
        self.projects_dir = projects_dir or DEFAULT_PROJECTS_DIR
        self._config = config or {}
        self._register_default_adapters()

    def _register_default_adapters(self) -> None:
        """注册默认的免费 TTS 适配器 + 已配置 API Key 的收费适配器。"""
        self.adapters["edge-tts"] = EdgeTTSAdapter()
        self.adapters["chattts"] = ChatTTSAdapter()

        # Fish Audio — 需要 API Key
        fish_key = self._config.get("fish_audio_api_key", "")
        if fish_key:
            self.adapters["fish-speech"] = FishSpeechAdapter(api_key=fish_key)
        else:
            # 即使没有 key 也注册，让用户能在引擎列表中看到（生成时会报错提示配置）
            self.adapters["fish-speech"] = FishSpeechAdapter()

        # CosyVoice（阿里通义）— 需要 DashScope API Key
        cosy_key = self._config.get("cosyvoice_api_key", "")
        if cosy_key:
            self.adapters["cosyvoice"] = CosyVoiceAdapter(api_key=cosy_key)
        else:
            self.adapters["cosyvoice"] = CosyVoiceAdapter()

        # MiniMax — 需要 API Key + Group ID
        minimax_key = self._config.get("minimax_api_key", "")
        minimax_group = self._config.get("minimax_group_id", "")
        if minimax_key:
            self.adapters["minimax-tts"] = MiniMaxTTSAdapter(
                api_key=minimax_key, group_id=minimax_group
            )
        else:
            self.adapters["minimax-tts"] = MiniMaxTTSAdapter()

        # 火山引擎 — 需要 App ID + Access Token
        volc_token = self._config.get("volcengine_access_token", "")
        volc_app_id = self._config.get("volcengine_app_id", "")
        if volc_token:
            self.adapters["volcengine-tts"] = VolcEngineTTSAdapter(
                app_id=volc_app_id, access_token=volc_token
            )
        else:
            self.adapters["volcengine-tts"] = VolcEngineTTSAdapter()

    def register_adapter(self, name: str, adapter: TTSAdapter) -> None:
        """注册新的 TTS 适配器。

        Args:
            name: 引擎名称标识符
            adapter: TTSAdapter 实例
        """
        self.adapters[name] = adapter

    def unregister_adapter(self, name: str) -> None:
        """注销 TTS 适配器。"""
        self.adapters.pop(name, None)

    async def generate_speech(
        self,
        text: str,
        voice_id: str,
        engine: str = "edge-tts",
        project_id: Optional[str] = None,
        scene_id: Optional[str] = None,
    ) -> str:
        """使用指定引擎生成语音。

        Args:
            text: 要转换的文本
            voice_id: 语音 ID
            engine: 引擎名称，默认 "edge-tts"
            project_id: 项目 ID（用于确定输出路径）
            scene_id: 场景 ID（用于文件命名）

        Returns:
            生成的音频文件路径

        Raises:
            TTSEngineNotFoundError: 引擎未注册
            TTSError: 生成失败
        """
        adapter = self.adapters.get(engine)
        if not adapter:
            raise TTSEngineNotFoundError(engine)

        # 确定输出路径
        output_path = None
        if project_id and scene_id:
            audio_dir = self.projects_dir / project_id / "audio"
            audio_dir.mkdir(parents=True, exist_ok=True)
            # ChatTTS 输出 WAV，其他引擎（edge-tts 和所有收费引擎）都输出 MP3
            ext = "wav" if engine == "chattts" else "mp3"
            output_path = str(audio_dir / f"scene_{scene_id}.{ext}")

        return await adapter.generate_speech(text, voice_id, output_path)

    async def list_voices(self, engine: str) -> list[VoiceInfo]:
        """列出指定引擎的可用语音。

        Args:
            engine: 引擎名称

        Returns:
            语音信息列表

        Raises:
            TTSEngineNotFoundError: 引擎未注册
        """
        adapter = self.adapters.get(engine)
        if not adapter:
            raise TTSEngineNotFoundError(engine)
        return await adapter.list_voices()

    def list_engines(self) -> list[EngineInfo]:
        """列出所有已注册的引擎信息。"""
        return [adapter.get_engine_info() for adapter in self.adapters.values()]

    async def assign_voices(
        self,
        character_names: list[str],
        engine: str = "edge-tts",
    ) -> dict[str, str]:
        """为角色列表分配语音。

        Args:
            character_names: 角色名称列表
            engine: 使用的引擎名称

        Returns:
            dict 映射 {角色名称: voice_id}
        """
        voices = await self.list_voices(engine)
        if not voices:
            raise TTSError(f"引擎 '{engine}' 没有可用语音", code="TTS_NO_VOICES")
        return assign_voices_to_characters(character_names, voices)
