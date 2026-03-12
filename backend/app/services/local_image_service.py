"""本地图像生成服务

使用 Stable Diffusion XL 在本地 GPU 上生成关键帧图片。
与 ImageGeneratorService 接口一致，通过配置切换。

特点：
- 开箱即用，无需 API Key
- 首次使用自动下载模型
- 使用 CPU offload 适配 6GB 显存
- 与 FramePack 视频模型共享 GPU（串行使用）
"""

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any, Optional

from app.models.character import Character
from app.models.scene import StoryboardScene
from app.services.image_service import (
    ImageGenError,
    ImageGenTimeoutError,
    build_image_prompt,
    build_negative_prompt,
    get_image_size,
    DEFAULT_PROJECTS_DIR,
)
from app.services.model_manager import get_model_manager, ModelStatus

logger = logging.getLogger(__name__)

# 可选依赖
_torch_available = False
_diffusers_available = False

try:
    import torch
    _torch_available = True
except ImportError:
    torch = None  # type: ignore[assignment]

try:
    from diffusers import StableDiffusionXLPipeline  # type: ignore[import-untyped]
    _diffusers_available = True
except ImportError:
    StableDiffusionXLPipeline = None  # type: ignore[assignment,misc]


class LocalImageGenError(ImageGenError):
    """本地图像生成错误"""
    pass


class LocalImageGeneratorService:
    """本地 SDXL 图像生成服务。

    与 ImageGeneratorService 接口兼容，pipeline executor 可无缝切换。
    """

    MODEL_ID = "sdxl-base"

    def __init__(
        self,
        gpu_device: int = 0,
        projects_dir: Optional[Path] = None,
    ):
        self.gpu_device = gpu_device
        self.projects_dir = projects_dir or DEFAULT_PROJECTS_DIR
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

    async def load_model(self) -> None:
        """加载 SDXL 模型到 GPU。"""
        if not _torch_available or not _diffusers_available:
            raise LocalImageGenError(
                "依赖缺失: 请安装 torch 和 diffusers",
                code="LOCAL_IMAGE_DEPENDENCY_ERROR",
            )

        if self._loaded and self.pipeline is not None:
            return

        manager = get_model_manager()

        # 确保模型已下载
        model_info = manager.get_model(self.MODEL_ID)
        if model_info is None or model_info.status == ModelStatus.NOT_DOWNLOADED:
            logger.info("SDXL 模型未下载，开始自动下载...")
            await manager.download_model(self.MODEL_ID)

        model_path = manager.ensure_downloaded(self.MODEL_ID)

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._load_sync, model_path)
            self._loaded = True
            manager.set_active_model(self.MODEL_ID)
            logger.info("SDXL 模型加载成功 (GPU: %d)", self.gpu_device)
        except Exception as e:
            error_msg = str(e)
            if "out of memory" in error_msg.lower():
                raise LocalImageGenError(
                    "GPU 显存不足，请关闭其他 GPU 程序后重试",
                    code="LOCAL_IMAGE_OOM",
                    retryable=True,
                )
            raise LocalImageGenError(f"SDXL 模型加载失败: {error_msg}")

    def _load_sync(self, model_path: str) -> None:
        """同步加载模型"""
        self.pipeline = StableDiffusionXLPipeline.from_pretrained(
            model_path,
            torch_dtype=torch.float16,
            use_safetensors=True,
            variant="fp16",
        )
        self.pipeline.enable_model_cpu_offload(gpu_id=self.gpu_device)

    async def unload_model(self) -> None:
        """卸载模型释放 GPU 显存"""
        if self.pipeline is not None:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._unload_sync)
            except Exception as e:
                logger.warning("卸载 SDXL 模型时出错: %s", e)
            finally:
                self.pipeline = None
                self._loaded = False
                manager = get_model_manager()
                manager.set_active_model(None)
                logger.info("SDXL 模型已卸载")

    def _unload_sync(self) -> None:
        del self.pipeline
        self.pipeline = None
        if _torch_available and torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()

    @property
    def is_loaded(self) -> bool:
        return self._loaded and self.pipeline is not None

    # ----------------------------------------------------------
    # 图像生成（与 ImageGeneratorService 接口一致）
    # ----------------------------------------------------------

    async def generate_keyframe(
        self,
        scene: StoryboardScene,
        characters: list[Character],
        style_config: dict,
        project_id: str = "default",
    ) -> str:
        """生成单个分镜的关键帧图片，返回文件路径。"""
        if not self.is_loaded:
            await self.load_model()

        prompt = build_image_prompt(scene, characters, style_config)
        negative_prompt = build_negative_prompt(style_config)
        width, height = get_image_size(style_config)

        try:
            loop = asyncio.get_event_loop()
            image = await loop.run_in_executor(
                None,
                self._generate_sync,
                prompt,
                negative_prompt,
                width,
                height,
                style_config,
            )
        except Exception as e:
            error_msg = str(e)
            if "out of memory" in error_msg.lower():
                raise LocalImageGenError(
                    "GPU 显存不足，请降低分辨率或关闭其他 GPU 程序",
                    code="LOCAL_IMAGE_OOM",
                    retryable=True,
                )
            raise LocalImageGenError(f"图像生成失败: {error_msg}")

        # 保存图片
        file_path = self._save_image(image, project_id, scene.id)
        return file_path

    async def regenerate_keyframe(
        self,
        scene: StoryboardScene,
        characters: list[Character],
        style_config: dict,
        project_id: str = "default",
    ) -> str:
        """重新生成关键帧"""
        return await self.generate_keyframe(scene, characters, style_config, project_id)

    def _generate_sync(
        self,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        style_config: dict,
    ) -> Any:
        """同步生成图像（在线程池中执行）"""
        extra = style_config.get("extra", {})
        steps = extra.get("steps", 30)
        guidance_scale = style_config.get("guidance_scale", 7.5)

        result = self.pipeline(
            prompt=prompt,
            negative_prompt=negative_prompt if negative_prompt else None,
            width=width,
            height=height,
            num_inference_steps=steps,
            guidance_scale=guidance_scale,
            num_images_per_prompt=1,
        )
        return result.images[0]

    def _save_image(self, image: Any, project_id: str, scene_id: str) -> str:
        """保存 PIL Image 到项目的 keyframes 目录"""
        keyframes_dir = self.projects_dir / project_id / "keyframes"
        keyframes_dir.mkdir(parents=True, exist_ok=True)

        filename = f"scene_{scene_id}.png"
        file_path = keyframes_dir / filename
        image.save(str(file_path), format="PNG")
        return str(file_path)

    async def close(self) -> None:
        """兼容 ImageGeneratorService 的 close 接口"""
        await self.unload_model()
