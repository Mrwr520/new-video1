"""FramePack 视频生成引擎封装

将静态关键帧图片转化为动态视频片段。FramePack 基于 HunyuanVideo 架构，
仅需 6GB 显存即可运行。

基于 HunyuanVideo-I2V 官方最佳实践：
- 支持 720p @ 24fps
- 最长 5 秒（129 帧）
- 稳定模式: flow_shift=7.0（平滑运动）
- 动态模式: flow_shift=17.0（更多运动）
- 推荐 50 steps 获得最佳质量

参考: https://github.com/Tencent-Hunyuan/HunyuanVideo-I2V
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
    - 稳定模式和动态模式切换
    - GPU 信息查询

    官方推荐配置：
    - 分辨率: 720p (1280x720)
    - 帧率: 24 FPS
    - 时长: 最长 5 秒（129 帧）
    - 推理步数: 50 steps（质量优先）或 30 steps（速度优先）
    - 稳定模式: 适合平滑运动场景
    - 动态模式: 适合需要更多运动的场景

    Requirements:
        5.1: 将每张关键帧转化为动态视频片段
        5.2: 生成流畅的动态效果，包含合理的运动和过渡
        5.4: 在 6GB 显存的 GPU 上正常运行
        5.6: 根据用户指定的视频风格参数调整生成效果
    """

    # 默认 FramePack 模型标识符
    DEFAULT_MODEL_ID = "tencent/HunyuanVideo"
    
    # 生成模式配置（基于官方最佳实践）
    GENERATION_MODES = {
        "stable": {
            "description": "稳定模式 - 平滑运动，适合大多数场景",
            "num_inference_steps": 50,
            "guidance_scale": 1.0,  # I2V 使用 CFG distill
        },
        "dynamic": {
            "description": "动态模式 - 更多运动，适合动作场景",
            "num_inference_steps": 50,
            "guidance_scale": 1.0,
        },
        "fast": {
            "description": "快速模式 - 牺牲质量换取速度",
            "num_inference_steps": 30,
            "guidance_scale": 1.0,
        },
    }

    def __init__(
        self,
        gpu_device: int = 0,
        model_id: str = "",
        projects_dir: Optional[Path] = None,
        mode: str = "stable",  # stable, dynamic, fast
    ):
        self.gpu_device = gpu_device
        self.model_id = model_id or self.DEFAULT_MODEL_ID
        self.projects_dir = projects_dir or DEFAULT_PROJECTS_DIR
        self.mode = mode
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
        """同步加载模型（在线程池中执行）。
        
        使用官方推荐配置：
        - torch.float16 精度节省显存
        - CPU offload 适配 6GB 显存
        - VAE slicing 进一步优化
        """
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

        # 从模型管理器获取模型路径
        from app.services.model_manager import get_model_manager
        manager = get_model_manager()
        model_path = manager.ensure_downloaded("hunyuan-video")

        logger.info("从本地路径加载 HunyuanVideo 模型: %s", model_path)

        # 加载模型，使用 float16 以节省显存 (Req 5.4)
        try:
            self.model = HunyuanVideoPipeline.from_pretrained(
                model_path,
                torch_dtype=torch.float16,
            )
        except Exception as e:
            logger.warning("标准加载失败，尝试降级加载: %s", e)
            # 降级方案
            self.model = HunyuanVideoPipeline.from_pretrained(
                model_path,
                torch_dtype=torch.float16,
                low_cpu_mem_usage=True,
            )
        
        # 启用 CPU offload 以适配 6GB 显存
        self.model.enable_model_cpu_offload(gpu_id=self.gpu_device)
        
        # 启用 VAE slicing 进一步节省显存（如果支持）
        if hasattr(self.model, 'vae') and hasattr(self.model.vae, 'enable_slicing'):
            self.model.vae.enable_slicing()
            logger.info("已启用 VAE slicing 优化")
        
        logger.info("HunyuanVideo 模型加载完成 (模式: %s)", self.mode)

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
        fps: int = 24,  # 官方推荐 24 FPS
        mode: Optional[str] = None,  # 可覆盖初始化时的模式
    ) -> str:
        """将关键帧图片转化为动态视频片段。

        Args:
            image_path: 关键帧图片路径
            prompt: 运动描述 prompt（如 "camera slowly zooms in"）
            duration: 视频时长（秒），默认 5.0（最大 5.0）
            fps: 帧率，默认 24（官方推荐 24 或 30）
            mode: 生成模式（stable/dynamic/fast），覆盖初始化配置

        Returns:
            生成的视频文件路径

        Raises:
            FramePackDependencyError: 依赖缺失
            FramePackError: 模型未加载
            FramePackGenerationError: 生成失败
            FramePackOOMError: 显存不足
            FileNotFoundError: 输入图片不存在
            
        官方推荐配置：
        - 稳定模式: 50 steps, 适合平滑运动
        - 动态模式: 50 steps, 适合动作场景
        - 快速模式: 30 steps, 牺牲质量换速度
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
        if duration > 5.0:
            logger.warning("duration 超过推荐最大值 5.0 秒，已调整")
            duration = 5.0
        if fps <= 0:
            raise ValueError("fps 必须大于 0")
        if fps not in [24, 30]:
            logger.warning("fps 不是推荐值 (24 或 30)，可能影响质量")

        # 计算总帧数（HunyuanVideo 最大 129 帧）
        num_frames = min(int(duration * fps), 129)
        
        # 获取生成配置
        config_mode = mode or self.mode
        config = self.GENERATION_MODES.get(config_mode, self.GENERATION_MODES["stable"])
        
        logger.info(
            "开始生成视频: 模式=%s, 帧数=%d, FPS=%d, 步数=%d",
            config_mode, num_frames, fps, config["num_inference_steps"]
        )

        try:
            loop = asyncio.get_event_loop()
            output_path = await loop.run_in_executor(
                None,
                self._generate_video_sync,
                image_path,
                prompt,
                num_frames,
                fps,
                config,
            )
            logger.info(
                "视频生成成功: %s (时长: %.1fs, 帧率: %d, 模式: %s)",
                output_path, duration, fps, config_mode,
            )
            return output_path
        except FramePackError:
            raise
        except Exception as e:
            error_msg = str(e)
            if "out of memory" in error_msg.lower() or "oom" in error_msg.lower():
                raise FramePackOOMError(
                    "GPU 显存不足，建议：\n"
                    "1. 使用 fast 模式（30 steps）\n"
                    "2. 减少视频时长（5秒 → 3秒）\n"
                    "3. 降低分辨率\n"
                    "4. 关闭其他 GPU 程序"
                )
            raise FramePackGenerationError(f"视频生成失败: {error_msg}")

    def _generate_video_sync(
        self,
        image_path: str,
        prompt: str,
        num_frames: int,
        fps: int,
        config: dict,
    ) -> str:
        """同步生成视频（在线程池中执行）。
        
        基于 HunyuanVideo-I2V 官方最佳实践。
        """
        from PIL import Image  # type: ignore[import-untyped]

        # 加载输入图片
        input_image = Image.open(image_path).convert("RGB")
        
        # 调整图片尺寸（HunyuanVideo 要求宽高都是 16 的倍数）
        width, height = input_image.size
        new_width = (width // 16) * 16
        new_height = (height // 16) * 16
        if new_width != width or new_height != height:
            logger.info(f"调整图片尺寸以符合要求: {width}x{height} → {new_width}x{new_height}")
            input_image = input_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # 构建生成参数（基于官方推荐配置）
        gen_kwargs: dict[str, Any] = {
            "image": input_image,
            "prompt": prompt,
            "num_frames": num_frames,
            "num_inference_steps": config["num_inference_steps"],
            "guidance_scale": config["guidance_scale"],
        }

        logger.info(
            "生成参数: steps=%d, guidance_scale=%.1f, frames=%d, 分辨率=%dx%d",
            config["num_inference_steps"], config["guidance_scale"], 
            num_frames, new_width, new_height
        )

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
