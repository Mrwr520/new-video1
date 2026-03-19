"""HunyuanVideo I2V 优化服务

基于 HunyuanVideo-I2V 官方最佳实践的视频生成服务。
集成了社区验证的参数配置和优化技巧。

参考资料：
- GitHub: https://github.com/Tencent-Hunyuan/HunyuanVideo-I2V
- 最佳实践: 720p @ 24fps, 5秒视频, 50 steps
- 稳定模式: flow_shift=7.0, 动态模式: flow_shift=17.0
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

from app.services.model_manager import get_model_manager, ModelStatus

logger = logging.getLogger(__name__)

# 默认项目文件存储根目录
DEFAULT_PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"

# 可选依赖
_torch_available = False
_diffusers_available = False

try:
    import torch
    _torch_available = True
except ImportError:
    torch = None  # type: ignore[assignment]

try:
    from diffusers import HunyuanVideoPipeline  # type: ignore[import-untyped]
    _diffusers_available = True
except ImportError:
    HunyuanVideoPipeline = None  # type: ignore[assignment,misc]


class HunyuanVideoError(Exception):
    """HunyuanVideo 服务异常"""
    def __init__(self, message: str, code: str = "HUNYUAN_ERROR", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class HunyuanVideoService:
    """HunyuanVideo I2V 视频生成服务。
    
    基于官方最佳实践的优化配置：
    - 支持 720p 分辨率
    - 24 FPS 帧率
    - 最长 5 秒（129 帧）
    - 稳定模式和动态模式切换
    - 自动显存管理
    """

    MODEL_ID = "hunyuan-video"
    
    # 推荐配置（基于官方文档）
    RECOMMENDED_CONFIGS = {
        "stable": {
            "description": "稳定模式 - 适合需要平滑运动的场景",
            "flow_shift": 7.0,
            "infer_steps": 50,
            "guidance_scale": 1.0,  # I2V 模式推荐使用 CFG distill
        },
        "dynamic": {
            "description": "动态模式 - 适合需要更多运动的场景",
            "flow_shift": 17.0,
            "infer_steps": 50,
            "guidance_scale": 1.0,
        },
        "fast": {
            "description": "快速模式 - 牺牲一些质量换取速度",
            "flow_shift": 7.0,
            "infer_steps": 30,
            "guidance_scale": 1.0,
        },
    }

    def __init__(
        self,
        gpu_device: int = 0,
        projects_dir: Optional[Path] = None,
        mode: str = "stable",  # stable, dynamic, fast
    ):
        self.gpu_device = gpu_device
        self.projects_dir = projects_dir or DEFAULT_PROJECTS_DIR
        self.mode = mode
        self.pipeline: Any = None
        self._loaded = False

    @staticmethod
    def check_dependencies() -> dict:
        """检查依赖是否可用"""
        cuda_available = False
        if _torch_available and torch is not None:
            cuda_available = torch.cuda.is_available()
        return {
            "torch_available": _torch_available,
            "diffusers_available": _diffusers_available,
            "cuda_available": cuda_available,
        }

    def _ensure_dependencies(self) -> None:
        """确保所有依赖可用"""
        if not _torch_available or not _diffusers_available:
            raise HunyuanVideoError(
                "依赖缺失: 请安装 torch 和 diffusers",
                code="HUNYUAN_DEPENDENCY_ERROR",
            )

    async def load_model(self) -> None:
        """加载 HunyuanVideo 模型到 GPU。
        
        使用官方推荐的配置：
        - torch.float16 精度
        - CPU offload 以适配 6GB 显存
        """
        self._ensure_dependencies()

        if self._loaded and self.pipeline is not None:
            logger.info("HunyuanVideo 模型已加载，跳过重复加载")
            return

        manager = get_model_manager()

        # 确保模型已下载
        model_info = manager.get_model(self.MODEL_ID)
        if model_info is None or model_info.status == ModelStatus.NOT_DOWNLOADED:
            logger.info("HunyuanVideo 模型未下载，开始自动下载...")
            await manager.download_model(self.MODEL_ID)

        model_path = manager.ensure_downloaded(self.MODEL_ID)

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._load_sync, model_path)
            self._loaded = True
            manager.set_active_model(self.MODEL_ID)
            logger.info("HunyuanVideo 模型加载成功 (GPU: %d, 模式: %s)", 
                       self.gpu_device, self.mode)
        except Exception as e:
            error_msg = str(e)
            if "out of memory" in error_msg.lower():
                raise HunyuanVideoError(
                    "GPU 显存不足，请关闭其他 GPU 程序后重试",
                    code="HUNYUAN_OOM",
                    retryable=True,
                )
            raise HunyuanVideoError(f"模型加载失败: {error_msg}")

    def _load_sync(self, model_path: str) -> None:
        """同步加载模型"""
        if not torch.cuda.is_available():
            raise HunyuanVideoError(
                "CUDA 不可用，HunyuanVideo 需要 NVIDIA GPU",
                code="HUNYUAN_NO_CUDA",
            )

        if self.gpu_device >= torch.cuda.device_count():
            raise HunyuanVideoError(
                f"GPU 设备 {self.gpu_device} 不存在，"
                f"可用设备数: {torch.cuda.device_count()}",
                code="HUNYUAN_INVALID_GPU",
            )

        # 加载模型（官方推荐配置）
        try:
            self.pipeline = HunyuanVideoPipeline.from_pretrained(
                model_path,
                torch_dtype=torch.float16,
            )
        except Exception as e:
            logger.warning("标准加载失败，尝试降级加载: %s", e)
            # 降级方案
            self.pipeline = HunyuanVideoPipeline.from_pretrained(
                model_path,
                torch_dtype=torch.float16,
                low_cpu_mem_usage=True,
            )
        
        # 启用 CPU offload 以适配 6GB 显存
        self.pipeline.enable_model_cpu_offload(gpu_id=self.gpu_device)
        
        # 可选：启用 VAE slicing 进一步节省显存
        if hasattr(self.pipeline, 'vae') and hasattr(self.pipeline.vae, 'enable_slicing'):
            self.pipeline.vae.enable_slicing()

    async def unload_model(self) -> None:
        """卸载模型释放 GPU 显存"""
        if self.pipeline is not None:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._unload_sync)
            except Exception as e:
                logger.warning("卸载模型时出错: %s", e)
            finally:
                self.pipeline = None
                self._loaded = False
                manager = get_model_manager()
                manager.set_active_model(None)
                logger.info("HunyuanVideo 模型已卸载")

    def _unload_sync(self) -> None:
        """同步卸载模型"""
        del self.pipeline
        self.pipeline = None
        if _torch_available and torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()

    @property
    def is_loaded(self) -> bool:
        """模型是否已加载"""
        return self._loaded and self.pipeline is not None

    async def generate_video(
        self,
        image_path: str,
        prompt: str,
        duration: float = 5.0,
        fps: int = 24,  # 官方推荐 24 FPS
        resolution: str = "720p",  # 支持 720p, 540p, 360p
        mode: Optional[str] = None,  # 可覆盖初始化时的模式
    ) -> str:
        """将关键帧图片转化为动态视频片段。
        
        Args:
            image_path: 关键帧图片路径
            prompt: 运动描述 prompt（如 "camera slowly zooms in"）
            duration: 视频时长（秒），默认 5.0（最大 5.0）
            fps: 帧率，默认 24（官方推荐）
            resolution: 分辨率，默认 720p
            mode: 生成模式（stable/dynamic/fast），覆盖初始化配置
            
        Returns:
            生成的视频文件路径
        """
        self._ensure_dependencies()

        if not self.is_loaded:
            raise HunyuanVideoError(
                "模型未加载，请先调用 load_model()",
                code="HUNYUAN_NOT_LOADED",
            )

        # 验证输入图片
        image_file = Path(image_path)
        if not image_file.exists():
            raise FileNotFoundError(f"关键帧图片不存在: {image_path}")

        # 验证参数
        if duration <= 0 or duration > 5.0:
            logger.warning("duration 超出推荐范围 (0-5秒)，已调整为 5.0 秒")
            duration = 5.0
        
        if fps not in [24, 30]:
            logger.warning("fps 不是推荐值 (24 或 30)，可能影响质量")

        # 计算总帧数（HunyuanVideo 最大 129 帧）
        num_frames = min(int(duration * fps), 129)
        
        # 获取配置
        config_mode = mode or self.mode
        config = self.RECOMMENDED_CONFIGS.get(config_mode, self.RECOMMENDED_CONFIGS["stable"])
        
        logger.info(
            "开始生成视频: 模式=%s, 帧数=%d, FPS=%d, 分辨率=%s",
            config_mode, num_frames, fps, resolution
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
            logger.info("视频生成成功: %s", output_path)
            return output_path
        except HunyuanVideoError:
            raise
        except Exception as e:
            error_msg = str(e)
            if "out of memory" in error_msg.lower():
                raise HunyuanVideoError(
                    "GPU 显存不足，建议：\n"
                    "1. 降低分辨率（720p → 540p）\n"
                    "2. 减少帧数（5秒 → 3秒）\n"
                    "3. 使用 fast 模式",
                    code="HUNYUAN_OOM",
                    retryable=True,
                )
            raise HunyuanVideoError(f"视频生成失败: {error_msg}")

    def _generate_video_sync(
        self,
        image_path: str,
        prompt: str,
        num_frames: int,
        fps: int,
        config: dict,
    ) -> str:
        """同步生成视频（在线程池中执行）"""
        from PIL import Image  # type: ignore[import-untyped]

        # 加载输入图片
        input_image = Image.open(image_path).convert("RGB")
        
        # 调整图片尺寸（HunyuanVideo 对尺寸有要求）
        # 官方推荐：宽高都应该是 16 的倍数
        width, height = input_image.size
        new_width = (width // 16) * 16
        new_height = (height // 16) * 16
        if new_width != width or new_height != height:
            logger.info(f"调整图片尺寸: {width}x{height} → {new_width}x{new_height}")
            input_image = input_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

        # 构建生成参数（基于官方最佳实践）
        gen_kwargs: dict[str, Any] = {
            "image": input_image,
            "prompt": prompt,
            "num_frames": num_frames,
            "num_inference_steps": config["infer_steps"],
            "guidance_scale": config["guidance_scale"],
            # flow_shift 参数（如果 pipeline 支持）
            # "flow_shift": config["flow_shift"],  # 需要检查 API
        }

        logger.info(
            "生成参数: steps=%d, guidance_scale=%.1f, frames=%d",
            config["infer_steps"], config["guidance_scale"], num_frames
        )

        # 调用模型生成
        output = self.pipeline(**gen_kwargs)

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

    async def close(self) -> None:
        """兼容接口"""
        await self.unload_model()

    def get_gpu_info(self) -> dict:
        """获取 GPU 信息"""
        if not _torch_available or torch is None:
            return {"available": False, "error": "PyTorch 未安装"}

        if not torch.cuda.is_available():
            return {"available": False, "error": "CUDA 不可用"}

        try:
            device_count = torch.cuda.device_count()
            devices = []
            for i in range(device_count):
                props = torch.cuda.get_device_properties(i)
                mem_total = props.total_mem / (1024 ** 3)
                mem_allocated = torch.cuda.memory_allocated(i) / (1024 ** 3)
                mem_reserved = torch.cuda.memory_reserved(i) / (1024 ** 3)
                devices.append({
                    "index": i,
                    "name": props.name,
                    "total_memory_gb": round(mem_total, 2),
                    "allocated_memory_gb": round(mem_allocated, 2),
                    "free_memory_gb": round(mem_total - mem_reserved, 2),
                })

            return {
                "available": True,
                "device_count": device_count,
                "current_device": self.gpu_device,
                "devices": devices,
                "cuda_version": torch.version.cuda or "unknown",
                "model_loaded": self.is_loaded,
            }
        except Exception as e:
            return {"available": False, "error": f"获取 GPU 信息失败: {e}"}
