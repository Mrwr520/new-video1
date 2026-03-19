"""环境检测与依赖安装 API

提供 Python 依赖检查、GPU 检测（通过 nvidia-smi）、一键安装功能。
即使 PyTorch 未安装也能通过 nvidia-smi 检测 GPU 硬件。
"""

import asyncio
import json
import logging
import re
import subprocess
import sys
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/environment")

# 全局安装状态
_install_status = {"running": False, "log": [], "success": None, "message": ""}


class PackageStatus(BaseModel):
    name: str
    display_name: str
    installed: bool
    version: Optional[str] = None
    required: bool = True
    description: str = ""


class NvidiaSmiGPU(BaseModel):
    index: int
    name: str
    driver_version: str
    total_memory_mb: int
    free_memory_mb: int
    used_memory_mb: int
    cuda_version: str


class EnvironmentCheckResponse(BaseModel):
    python_version: str
    python_path: str
    gpu_detected: bool = False
    gpu_info: Optional[list[NvidiaSmiGPU]] = None
    gpu_error: Optional[str] = None
    nvidia_driver_version: Optional[str] = None
    cuda_version_from_driver: Optional[str] = None
    packages: list[PackageStatus] = []
    all_installed: bool = False
    recommended_torch_index_url: Optional[str] = None


class InstallRequest(BaseModel):
    packages: list[str] = Field(default_factory=list)
    cuda_version: Optional[str] = Field(default=None)


class InstallStatusResponse(BaseModel):
    running: bool
    log: list[str]
    success: Optional[bool] = None
    message: str = ""


REQUIRED_PACKAGES = [
    {"name": "torch", "display_name": "PyTorch", "description": "深度学习框架", "required": True},
    {"name": "torchvision", "display_name": "TorchVision", "description": "视觉库", "required": True},
    {"name": "torchaudio", "display_name": "TorchAudio", "description": "音频库", "required": True},
    {"name": "diffusers", "display_name": "Diffusers", "description": "扩散模型库", "required": True},
    {"name": "transformers", "display_name": "Transformers", "description": "模型库", "required": True},
    {"name": "accelerate", "display_name": "Accelerate", "description": "加速库", "required": True},
    {"name": "huggingface_hub", "display_name": "HF Hub", "description": "模型下载", "required": True},
    {"name": "safetensors", "display_name": "SafeTensors", "description": "权重格式", "required": False},
    {"name": "PIL", "display_name": "Pillow", "description": "图像处理", "required": True, "pip_name": "Pillow"},
]


def _check_package(name: str) -> tuple[bool, Optional[str]]:
    try:
        if name == "PIL":
            import importlib
            mod = importlib.import_module("PIL")
            return True, getattr(mod, "__version__", None)
        mod = __import__(name)
        return True, getattr(mod, "__version__", None)
    except ImportError:
        return False, None


def _detect_gpu_via_nvidia_smi():
    """通过 nvidia-smi 检测 GPU，不依赖 PyTorch"""
    try:
        result = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=index,name,driver_version,memory.total,memory.free,memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return False, None, None, None, f"nvidia-smi 错误: {result.stderr.strip()}"

        gpus = []
        driver_ver = None
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 6:
                continue
            driver_ver = parts[2]
            gpus.append({
                "index": int(parts[0]), "name": parts[1],
                "driver_version": parts[2],
                "total_memory_mb": int(float(parts[3])),
                "free_memory_mb": int(float(parts[4])),
                "used_memory_mb": int(float(parts[5])),
            })

        cuda_ver = None
        try:
            r2 = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=10)
            m = re.search(r"CUDA Version:\s*([\d.]+)", r2.stdout)
            if m:
                cuda_ver = m.group(1)
        except Exception:
            pass

        for g in gpus:
            g["cuda_version"] = cuda_ver or ""

        return True, gpus, driver_ver, cuda_ver, None
    except FileNotFoundError:
        return False, None, None, None, "未找到 nvidia-smi，请安装 NVIDIA 驱动"
    except subprocess.TimeoutExpired:
        return False, None, None, None, "nvidia-smi 超时"
    except Exception as e:
        return False, None, None, None, f"GPU 检测失败: {e}"


def _recommend_torch_index_url(cuda_ver_str: Optional[str]) -> Optional[str]:
    if not cuda_ver_str:
        return None
    try:
        parts = cuda_ver_str.split(".")
        major, minor = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        v = major * 10 + minor
        if v >= 126:
            return "https://download.pytorch.org/whl/cu126"
        if v >= 124:
            return "https://download.pytorch.org/whl/cu124"
        if v >= 121:
            return "https://download.pytorch.org/whl/cu121"
        return "https://download.pytorch.org/whl/cu118"
    except Exception:
        return None


def _pip_name(pkg_def: dict) -> str:
    return pkg_def.get("pip_name", pkg_def["name"])


async def _run_pip_install(args: list[str], log: list[str]) -> bool:
    """运行 pip install 命令，实时追加日志"""
    cmd = [sys.executable, "-m", "pip", "install"] + args
    log.append(f"$ {' '.join(cmd)}")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                log.append(text)
        await proc.wait()
        if proc.returncode != 0:
            log.append(f"[错误] pip 返回码: {proc.returncode}")
            return False
        return True
    except Exception as e:
        log.append(f"[错误] {e}")
        return False


# ============================================================
# API 端点
# ============================================================

@router.get("/check", response_model=EnvironmentCheckResponse)
async def check_environment() -> EnvironmentCheckResponse:
    """检测 Python 环境：GPU、已安装包、推荐安装源"""
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    detected, gpu_list, driver_ver, cuda_ver, gpu_err = _detect_gpu_via_nvidia_smi()

    gpu_info = [NvidiaSmiGPU(**g) for g in gpu_list] if gpu_list else None

    packages = []
    all_ok = True
    for pkg_def in REQUIRED_PACKAGES:
        installed, version = _check_package(pkg_def["name"])
        packages.append(PackageStatus(
            name=_pip_name(pkg_def),
            display_name=pkg_def["display_name"],
            installed=installed, version=version,
            required=pkg_def.get("required", True),
            description=pkg_def["description"],
        ))
        if pkg_def.get("required", True) and not installed:
            all_ok = False

    return EnvironmentCheckResponse(
        python_version=py_ver,
        python_path=sys.executable,
        gpu_detected=detected,
        gpu_info=gpu_info,
        gpu_error=gpu_err,
        nvidia_driver_version=driver_ver,
        cuda_version_from_driver=cuda_ver,
        packages=packages,
        all_installed=all_ok,
        recommended_torch_index_url=_recommend_torch_index_url(cuda_ver),
    )


@router.post("/install")
async def install_packages(req: InstallRequest):
    """安装缺失依赖，后台执行，通过 /install-status 查询进度"""
    global _install_status
    if _install_status["running"]:
        return {"error": "安装正在进行中，请等待完成"}

    _install_status = {"running": True, "log": [], "success": None, "message": "开始安装..."}

    # 确定要安装的包
    if req.packages:
        to_install_other = [p for p in req.packages if p not in ("torch", "torchvision", "torchaudio")]
        to_install_torch = [p for p in req.packages if p in ("torch", "torchvision", "torchaudio")]
    else:
        to_install_torch = []
        to_install_other = []
        for pkg_def in REQUIRED_PACKAGES:
            installed, _ = _check_package(pkg_def["name"])
            if not installed:
                pname = _pip_name(pkg_def)
                if pname in ("torch", "torchvision", "torchaudio"):
                    to_install_torch.append(pname)
                else:
                    to_install_other.append(pname)

    if not to_install_torch and not to_install_other:
        _install_status = {"running": False, "log": ["所有依赖已安装"], "success": True, "message": "无需安装"}
        return {"message": "所有依赖已安装"}

    # 后台任务
    async def do_install():
        global _install_status
        log = _install_status["log"]
        ok = True

        if to_install_torch:
            index_url = None
            if req.cuda_version:
                if req.cuda_version == "cpu":
                    index_url = "https://download.pytorch.org/whl/cpu"
                else:
                    index_url = f"https://download.pytorch.org/whl/{req.cuda_version}"
            else:
                _, _, _, cuda_ver, _ = _detect_gpu_via_nvidia_smi()
                index_url = _recommend_torch_index_url(cuda_ver)

            log.append(f">>> 安装 PyTorch: {', '.join(to_install_torch)}")
            args = to_install_torch[:]
            if index_url:
                args += ["--index-url", index_url]
            if not await _run_pip_install(args, log):
                ok = False

        if to_install_other and ok:
            log.append(f">>> 安装其他依赖: {', '.join(to_install_other)}")
            if not await _run_pip_install(to_install_other, log):
                ok = False

        _install_status["running"] = False
        _install_status["success"] = ok
        _install_status["message"] = "安装完成" if ok else "安装过程中出现错误"

    asyncio.create_task(do_install())
    return {"message": "安装已开始", "packages_torch": to_install_torch, "packages_other": to_install_other}


@router.get("/install-status", response_model=InstallStatusResponse)
async def get_install_status() -> InstallStatusResponse:
    """查询安装进度"""
    return InstallStatusResponse(**_install_status)
