"""FramePack 视频生成引擎封装

将静态关键帧图片转化为动态视频片段。FramePack 基于 HunyuanVideo 架构，
仅需 6GB 显存即可运行。

由于 FramePack 依赖 PyTorch 和 GPU 环境，本模块使用 try/except 导入，
在依赖不可用时提供清晰的错误提示。
"""

import asyncio
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 默认项目文件存储根目录
DEFAULT_PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"

# ============================================================
# 可选依赖导入
# ============================================================

_torch_available = False
_framepack_available = False

try:
    import torch
    _torch_available = True
except ImportError:
    torch = None  # type: ignore[assignment]

try:
    from diffusers import HunyuanVideoPipeline  # type: ignore[import-untyped]
    _framepack_available = True
except ImportError:
    HunyuanVideoPipeline = None  # type: ignore[assignment,misc]


# ============================================================
# 异常类
# ============================================================

class FramePackError(Exception):
    """FramePack 服务基础异常"""

    def __init__(self, message: str, code: str = "FRAMEPACK_ERROR", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class FramePackDependencyError(FramePackError):
    """FramePack 依赖缺失"""

    def __init__(self, message: str = ""):
        missing = []
        if not _torch_available:
            missing.append("torch (PyTorch)")
        if not _framepack_available:
            missing.append("diffusers (HunyuanVideoPipeline)")
        detail = message or (
            f"FramePack 依赖缺失: {', '.join(missing)}。"
            "请安装 PyTorch 和 diffusers: pip install torch diffusers"
        )
        super().__init__(detail, code="FRAMEPACK_DEPENDENCY_ERROR", retryable=False)


class FramePackLoadError(FramePackError):
    """模型加载失败"""

    def __init__(self, message: str = "FramePack 模型加载失败"):
        super().__init__(message, code="FRAMEPACK_LOAD_ERROR", retryable=True)


class FramePackOOMError(FramePackError):
    """GPU 显存不足"""

    def __init__(self, message: str = "GPU 显存不足，请降低分辨率或关闭其他 GPU 程序"):
        super().__init__(message, code="FRAMEPACK_OOM", retryable=True)


class FramePackGenerationError(FramePackError):
    """视频生成失败"""

    def __init__(self, message: str = "视频生成失败"):
        super().__init__(message, code="FRAMEPACK_GENERATION_ERROR", retryable=True)


# ============================================================
# FramePack 服务
# ============================================================

class FramePackService:
    """FramePack 视频生成引擎封装。

    将关键帧图片转化为动态视频片段。支持：
    - 模型加载/卸载（管理 GPU 显存）
    - 图片转视频生成（prompt、duration、fps 参数）
    - TeaCache 加速
    - GPU 信息查询

    Requirements:
        5.1: 将每张关键帧转化为动态视频片段
        5.2: 生成流畅的动态效果，包含合理的运动和过渡
        5.4: 在 6GB 显存的 GPU 上正常运行
        5.6: 根据用户指定的视频风格参数调整生成效果
    """

    # 默认 FramePack 模型标识符
    DEFAULT_MODEL_ID = "tencent/HunyuanVideo"

    def __init__(
        self,
        gpu_device: int = 0,
        model_id: str = "",
        projects_dir: Optional[Path] = None,
    ):
        self.gpu_device = gpu_device
        self.model_id = model_id or self.DEFAULT_MODEL_ID
        self.projects_dir = projects_dir or DEFAULT_PROJECTS_DIR
        self.model: Any = None
        self._loaded = False

    # ----------------------------------------------------------
    # 依赖检查
    # ----------------------------------------------------------

    @staticmethod
    def check_dependencies() -> dict:
        """检查 FramePack 所需依赖是否可用。

        Returns:
            dict 包含 torch_available, framepack_available, cuda_available
        """
        cuda_available = False
        if _torch_available and torch is not None:
            cuda_available = torch.cuda.is_available()
        return {
            "torch_available": _torch_available,
            "framepack_available": _framepack_available,
            "cuda_available": cuda_available,
        }

    def _ensure_dependencies(self) -> None:
        """确保所有依赖可用，否则抛出异常。"""
        if not _torch_available or not _framepack_available:
            raise FramePackDependencyError()

    # ----------------------------------------------------------
    # 模型加载/卸载
    # ----------------------------------------------------------

    async def load_model(self) -> None:
        """加载 FramePack 模型到 GPU。

        使用 float16 精度和 CPU offload 策略以适配 6GB 显存 (Req 5.4)。

        Raises:
            FramePackDependencyError: 依赖缺失
            FramePackLoadError: 模型加载失败
        """
        self._ensure_dependencies()

        if self._loaded and self.model is not None:
            logger.info("FramePack 模型已加载，跳过重复加载")
            return

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._load_model_sync)
            self._loaded = True
            logger.info("FramePack 模型加载成功 (GPU: %d)", self.gpu_device)
        except FramePackError:
            raise
        except Exception as e:
            error_msg = str(e)
            if "out of memory" in error_msg.lower() or "oom" in error_msg.lower():
                raise FramePackOOMError()
            raise FramePackLoadError(f"模型加载失败: {error_msg}")

    def _load_model_sync(self) -> None:
        """同步加载模型（在线程池中执行）。"""
        device = f"cuda:{self.gpu_device}"

        # 检查 CUDA 设备可用性
        if not torch.cuda.is_available():
            raise FramePackLoadError(
                "CUDA 不可用，FramePack 需要 NVIDIA GPU。"
                "请确认已安装 CUDA 版本的 PyTorch。"
            )

        if self.gpu_device >= torch.cuda.device_count():
            raise FramePackLoadError(
                f"GPU 设备 {self.gpu_device} 不存在，"
                f"可用设备数: {torch.cuda.device_count()}"
            )

        # 加载模型，使用 float16 以节省显存 (Req 5.4)
        self.model = HunyuanVideoPipeline.from_pretrained(
            self.model_id,
            torch_dtype=torch.float16,
        )
        # 启用 CPU offload 以适配 6GB 显存
        self.model.enable_model_cpu_offload(gpu_id=self.gpu_device)

    async def unload_model(self) -> None:
        """卸载模型释放 GPU 显存。"""
        if self.model is not None:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._unload_model_sync)
            except Exception as e:
                logger.warning("卸载模型时出错: %s", e)
            finally:
                self.model = None
                self._loaded = False
                logger.info("FramePack 模型已卸载")

    def _unload_model_sync(self) -> None:
        """同步卸载模型。"""
        del self.model
        self.model = None
        if _torch_available and torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()

    @property
    def is_loaded(self) -> bool:
        """模型是否已加载。"""
        return self._loaded and self.model is not None

    # ----------------------------------------------------------
    # 视频生成
    # ----------------------------------------------------------

    async def generate_video(
        self,
        image_path: str,
        prompt: str,
        duration: float = 5.0,
        fps: int = 30,
        use_teacache: bool = True,
    ) -> str:
        """将关键帧图片转化为动态视频片段。

        Args:
            image_path: 关键帧图片路径
            prompt: 运动描述 prompt（如 "camera slowly zooms in"）
            duration: 视频时长（秒），默认 5.0
            fps: 帧率，默认 30
            use_teacache: 是否启用 TeaCache 加速，默认 True

        Returns:
            生成的视频文件路径

        Raises:
            FramePackDependencyError: 依赖缺失
            FramePackError: 模型未加载
            FramePackGenerationError: 生成失败
            FramePackOOMError: 显存不足
            FileNotFoundError: 输入图片不存在
        """
        self._ensure_dependencies()

        if not self.is_loaded:
            raise FramePackError(
                "模型未加载，请先调用 load_model()",
                code="FRAMEPACK_NOT_LOADED",
            )

        # 验证输入图片
        image_file = Path(image_path)
        if not image_file.exists():
            raise FileNotFoundError(f"关键帧图片不存在: {image_path}")

        # 验证参数
        if duration <= 0:
            raise ValueError("duration 必须大于 0")
        if fps <= 0:
            raise ValueError("fps 必须大于 0")

        # 计算总帧数
        num_frames = int(duration * fps)

        try:
            loop = asyncio.get_event_loop()
            output_path = await loop.run_in_executor(
                None,
                self._generate_video_sync,
                image_path,
                prompt,
                num_frames,
                fps,
                use_teacache,
            )
            logger.info(
                "视频生成成功: %s (时长: %.1fs, 帧率: %d, TeaCache: %s)",
                output_path, duration, fps, use_teacache,
            )
            return output_path
        except FramePackError:
            raise
        except Exception as e:
            error_msg = str(e)
            if "out of memory" in error_msg.lower() or "oom" in error_msg.lower():
                raise FramePackOOMError()
            raise FramePackGenerationError(f"视频生成失败: {error_msg}")

    def _generate_video_sync(
        self,
        image_path: str,
        prompt: str,
        num_frames: int,
        fps: int,
        use_teacache: bool,
    ) -> str:
        """同步生成视频（在线程池中执行）。"""
        from PIL import Image  # type: ignore[import-untyped]

        # 加载输入图片
        input_image = Image.open(image_path).convert("RGB")

        # 构建生成参数
        gen_kwargs: dict[str, Any] = {
            "image": input_image,
            "prompt": prompt,
            "num_frames": num_frames,
            "num_inference_steps": 30,
            "guidance_scale": 7.0,
        }

        # TeaCache 加速选项 — 减少推理步骤以加速生成
        if use_teacache:
            gen_kwargs["num_inference_steps"] = 20

        # 调用模型生成
        output = self.model(**gen_kwargs)

        # 导出视频文件
        output_dir = Path(image_path).parent.parent / "videos"
        output_dir.mkdir(parents=True, exist_ok=True)

        scene_id = Path(image_path).stem  # e.g. "scene_abc123"
        output_filename = f"{scene_id}.mp4"
        output_path = output_dir / output_filename

        # 使用 diffusers 的 export_to_video 工具
        from diffusers.utils import export_to_video  # type: ignore[import-untyped]
        export_to_video(output.frames[0], str(output_path), fps=fps)

        return str(output_path)

    # ----------------------------------------------------------
    # GPU 信息查询
    # ----------------------------------------------------------

    def get_gpu_info(self) -> dict:
        """获取 GPU 信息（显存、型号等）。

        Returns:
            dict 包含 GPU 信息，如果 torch/CUDA 不可用则返回错误信息。
        """
        if not _torch_available or torch is None:
            return {
                "available": False,
                "error": "PyTorch 未安装",
            }

        if not torch.cuda.is_available():
            return {
                "available": False,
                "error": "CUDA 不可用，请确认已安装 NVIDIA 驱动和 CUDA",
            }

        try:
            device_count = torch.cuda.device_count()
            devices = []
            for i in range(device_count):
                props = torch.cuda.get_device_properties(i)
                mem_total = props.total_mem / (1024 ** 3)  # GB
                mem_allocated = torch.cuda.memory_allocated(i) / (1024 ** 3)
                mem_reserved = torch.cuda.memory_reserved(i) / (1024 ** 3)
                devices.append({
                    "index": i,
                    "name": props.name,
                    "total_memory_gb": round(mem_total, 2),
                    "allocated_memory_gb": round(mem_allocated, 2),
                    "reserved_memory_gb": round(mem_reserved, 2),
                    "free_memory_gb": round(mem_total - mem_reserved, 2),
                    "compute_capability": f"{props.major}.{props.minor}",
                })

            current_device = self.gpu_device if self.gpu_device < device_count else 0
            return {
                "available": True,
                "device_count": device_count,
                "current_device": current_device,
                "devices": devices,
                "cuda_version": torch.version.cuda or "unknown",
                "model_loaded": self.is_loaded,
            }
        except Exception as e:
            return {
                "available": False,
                "error": f"获取 GPU 信息失败: {e}",
            }
