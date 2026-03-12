"""模型管理服务

统一管理本地 AI 模型的下载、缓存、状态查询和 GPU 检测。
首次使用时自动下载模型到本地缓存，后续直接加载。
提供下载进度回调，便于前端展示。

设计原则：
- 开箱即用：用户不需要手动下载模型
- 透明管理：前端可查询每个模型的状态和大小
- 显存协调：图像模型和视频模型不同时占用 GPU
"""

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# 默认模型缓存目录（用户 home 下）
DEFAULT_CACHE_DIR = Path.home() / ".ai-video-generator" / "models"


class ModelStatus(str, Enum):
    """模型状态"""
    NOT_DOWNLOADED = "not_downloaded"   # 未下载
    DOWNLOADING = "downloading"         # 下载中
    DOWNLOADED = "downloaded"           # 已下载，未加载
    LOADING = "loading"                 # 加载中
    LOADED = "loaded"                   # 已加载到 GPU
    ERROR = "error"                     # 出错


@dataclass
class ModelInfo:
    """模型信息"""
    id: str                              # 模型标识符
    name: str                            # 显示名称
    description: str                     # 描述
    hf_repo_id: str                      # HuggingFace 仓库 ID
    estimated_size_gb: float             # 预估下载大小 (GB)
    min_vram_gb: float                   # 最低显存需求 (GB)
    status: ModelStatus = ModelStatus.NOT_DOWNLOADED
    download_progress: float = 0.0       # 下载进度 0.0 ~ 1.0
    error_message: str = ""
    local_path: str = ""                 # 本地缓存路径

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


# ============================================================
# 预定义模型注册表
# ============================================================

REGISTERED_MODELS: dict[str, ModelInfo] = {
    "sdxl-base": ModelInfo(
        id="sdxl-base",
        name="Stable Diffusion XL Base",
        description="高质量图像生成模型，支持 1024x 分辨率，适合关键帧生成",
        hf_repo_id="stabilityai/stable-diffusion-xl-base-1.0",
        estimated_size_gb=6.9,
        min_vram_gb=6.0,
    ),
    "hunyuan-video": ModelInfo(
        id="hunyuan-video",
        name="HunyuanVideo (FramePack)",
        description="腾讯混元视频生成模型，将关键帧转化为动态视频",
        hf_repo_id="tencent/HunyuanVideo",
        estimated_size_gb=15.0,
        min_vram_gb=6.0,
    ),
}


# ============================================================
# GPU 信息
# ============================================================

@dataclass
class GPUInfo:
    """GPU 设备信息"""
    available: bool = False
    device_count: int = 0
    devices: list[dict] = field(default_factory=list)
    cuda_version: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def detect_gpu() -> GPUInfo:
    """检测 GPU 环境，返回设备信息。"""
    try:
        import torch
    except ImportError:
        return GPUInfo(available=False, error="PyTorch 未安装")

    if not torch.cuda.is_available():
        return GPUInfo(
            available=False,
            error="CUDA 不可用，请确认已安装 NVIDIA 驱动和 CUDA 版本的 PyTorch",
        )

    try:
        device_count = torch.cuda.device_count()
        devices = []
        for i in range(device_count):
            props = torch.cuda.get_device_properties(i)
            total_gb = props.total_mem / (1024 ** 3)
            allocated_gb = torch.cuda.memory_allocated(i) / (1024 ** 3)
            reserved_gb = torch.cuda.memory_reserved(i) / (1024 ** 3)
            devices.append({
                "index": i,
                "name": props.name,
                "total_memory_gb": round(total_gb, 2),
                "free_memory_gb": round(total_gb - reserved_gb, 2),
            })

        return GPUInfo(
            available=True,
            device_count=device_count,
            devices=devices,
            cuda_version=torch.version.cuda or "unknown",
        )
    except Exception as e:
        return GPUInfo(available=False, error=f"GPU 检测失败: {e}")


# ============================================================
# 模型管理器
# ============================================================

class ModelManager:
    """模型管理器 — 单例使用。

    职责：
    1. 检查模型是否已下载到本地缓存
    2. 触发模型下载（带进度回调）
    3. 查询所有模型状态
    4. 协调 GPU 显存（确保同一时间只有一个大模型在 GPU 上）
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._models: dict[str, ModelInfo] = {}
        self._active_model_id: Optional[str] = None  # 当前占用 GPU 的模型
        self._download_tasks: dict[str, asyncio.Task] = {}
        self._progress_callbacks: dict[str, list[Callable]] = {}

        # 初始化模型注册表并检查本地缓存
        for model_id, info in REGISTERED_MODELS.items():
            model = ModelInfo(
                id=info.id,
                name=info.name,
                description=info.description,
                hf_repo_id=info.hf_repo_id,
                estimated_size_gb=info.estimated_size_gb,
                min_vram_gb=info.min_vram_gb,
            )
            # 检查是否已下载
            local_path = self.cache_dir / model_id
            if local_path.exists() and any(local_path.iterdir()):
                model.status = ModelStatus.DOWNLOADED
                model.local_path = str(local_path)
                model.download_progress = 1.0
            self._models[model_id] = model

    # ----------------------------------------------------------
    # 查询接口
    # ----------------------------------------------------------

    def list_models(self) -> list[ModelInfo]:
        """列出所有注册的模型及其状态"""
        return list(self._models.values())

    def get_model(self, model_id: str) -> Optional[ModelInfo]:
        """获取单个模型信息"""
        return self._models.get(model_id)

    def get_gpu_info(self) -> GPUInfo:
        """获取 GPU 信息"""
        return detect_gpu()

    def get_active_model(self) -> Optional[str]:
        """获取当前占用 GPU 的模型 ID"""
        return self._active_model_id

    def set_active_model(self, model_id: Optional[str]) -> None:
        """设置当前占用 GPU 的模型（由服务层调用）"""
        self._active_model_id = model_id
        if model_id and model_id in self._models:
            self._models[model_id].status = ModelStatus.LOADED
        # 将之前的活跃模型标记为已下载（已卸载）
        for mid, info in self._models.items():
            if mid != model_id and info.status == ModelStatus.LOADED:
                info.status = ModelStatus.DOWNLOADED

    # ----------------------------------------------------------
    # 下载接口
    # ----------------------------------------------------------

    async def download_model(self, model_id: str) -> None:
        """下载模型到本地缓存。

        使用 huggingface_hub 的 snapshot_download，支持断点续传。
        """
        model = self._models.get(model_id)
        if model is None:
            raise ValueError(f"未知模型: {model_id}")

        if model.status == ModelStatus.DOWNLOADING:
            logger.info("模型 %s 正在下载中，跳过", model_id)
            return

        if model.status in (ModelStatus.DOWNLOADED, ModelStatus.LOADED):
            logger.info("模型 %s 已下载，跳过", model_id)
            return

        model.status = ModelStatus.DOWNLOADING
        model.download_progress = 0.0
        model.error_message = ""

        try:
            local_path = self.cache_dir / model_id
            local_path.mkdir(parents=True, exist_ok=True)

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, self._download_sync, model_id, model.hf_repo_id, str(local_path)
            )

            model.status = ModelStatus.DOWNLOADED
            model.download_progress = 1.0
            model.local_path = str(local_path)
            logger.info("模型下载完成: %s -> %s", model_id, local_path)

        except Exception as e:
            model.status = ModelStatus.ERROR
            model.error_message = str(e)
            logger.error("模型下载失败 %s: %s", model_id, e)
            raise

    def _download_sync(self, model_id: str, repo_id: str, local_dir: str) -> None:
        """同步下载模型（在线程池中执行）"""
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            raise RuntimeError(
                "huggingface_hub 未安装，请运行: pip install huggingface_hub"
            )

        model = self._models[model_id]

        def progress_callback(current: int, total: int) -> None:
            if total > 0:
                model.download_progress = current / total

        # snapshot_download 支持断点续传，会自动跳过已下载的文件
        snapshot_download(
            repo_id=repo_id,
            local_dir=local_dir,
            local_dir_use_symlinks=False,
        )

    async def delete_model(self, model_id: str) -> bool:
        """删除本地缓存的模型文件"""
        model = self._models.get(model_id)
        if model is None:
            return False

        if model.status in (ModelStatus.LOADED, ModelStatus.LOADING):
            raise RuntimeError("模型正在使用中，请先卸载")

        if model.status == ModelStatus.DOWNLOADING:
            raise RuntimeError("模型正在下载中，请等待完成")

        local_path = self.cache_dir / model_id
        if local_path.exists():
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, shutil.rmtree, str(local_path))

        model.status = ModelStatus.NOT_DOWNLOADED
        model.download_progress = 0.0
        model.local_path = ""
        logger.info("模型已删除: %s", model_id)
        return True

    def get_cache_size_gb(self) -> float:
        """获取模型缓存总大小 (GB)"""
        total = 0
        for path in self.cache_dir.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        return round(total / (1024 ** 3), 2)

    def ensure_downloaded(self, model_id: str) -> str:
        """确保模型已下载，返回本地路径。未下载则抛异常。"""
        model = self._models.get(model_id)
        if model is None:
            raise ValueError(f"未知模型: {model_id}")
        if model.status == ModelStatus.NOT_DOWNLOADED:
            raise RuntimeError(
                f"模型 {model.name} 尚未下载，请先在设置页面下载模型"
            )
        if model.status == ModelStatus.DOWNLOADING:
            raise RuntimeError(f"模型 {model.name} 正在下载中，请等待完成")
        if model.status == ModelStatus.ERROR:
            raise RuntimeError(f"模型 {model.name} 下载出错: {model.error_message}")
        return model.local_path or str(self.cache_dir / model_id)


# ============================================================
# 全局单例
# ============================================================

_manager_instance: Optional[ModelManager] = None


def get_model_manager() -> ModelManager:
    """获取全局 ModelManager 单例"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = ModelManager()
    return _manager_instance
