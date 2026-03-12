"""FramePack 服务单元测试

由于 FramePack 依赖 PyTorch 和 GPU，测试通过 mock 模拟这些依赖。
测试覆盖：
- 依赖检查
- 模型加载/卸载
- 视频生成（含参数验证）
- TeaCache 加速选项
- GPU 信息查询
- 错误处理
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from app.services.framepack_service import (
    FramePackService,
    FramePackDependencyError,
    FramePackError,
    FramePackGenerationError,
    FramePackLoadError,
    FramePackOOMError,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def service(tmp_path):
    """创建 FramePackService 实例"""
    return FramePackService(gpu_device=0, projects_dir=tmp_path)


@pytest.fixture
def sample_image(tmp_path):
    """创建一个测试用的图片文件"""
    keyframes_dir = tmp_path / "keyframes"
    keyframes_dir.mkdir(parents=True, exist_ok=True)
    img_path = keyframes_dir / "scene_test123.png"
    # 写入最小的有效 PNG（1x1 像素）
    import struct
    import zlib

    def _minimal_png() -> bytes:
        signature = b"\x89PNG\r\n\x1a\n"

        def chunk(chunk_type: bytes, data: bytes) -> bytes:
            c = chunk_type + data
            crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
            return struct.pack(">I", len(data)) + c + crc

        ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        raw_row = b"\x00\xff\x00\x00"  # filter byte + RGB
        idat_data = zlib.compress(raw_row)
        return signature + chunk(b"IHDR", ihdr_data) + chunk(b"IDAT", idat_data) + chunk(b"IEND", b"")

    img_path.write_bytes(_minimal_png())
    return str(img_path)


# ============================================================
# 依赖检查测试
# ============================================================

class TestCheckDependencies:
    """测试依赖检查功能"""

    def test_check_dependencies_returns_dict(self):
        result = FramePackService.check_dependencies()
        assert isinstance(result, dict)
        assert "torch_available" in result
        assert "framepack_available" in result
        assert "cuda_available" in result

    @patch("app.services.framepack_service._torch_available", False)
    @patch("app.services.framepack_service._framepack_available", False)
    def test_check_dependencies_missing(self):
        result = FramePackService.check_dependencies()
        assert result["torch_available"] is False
        assert result["framepack_available"] is False
        assert result["cuda_available"] is False

    @patch("app.services.framepack_service._torch_available", True)
    @patch("app.services.framepack_service._framepack_available", True)
    def test_check_dependencies_with_torch_no_cuda(self):
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False
        with patch("app.services.framepack_service.torch", mock_torch):
            result = FramePackService.check_dependencies()
        assert result["torch_available"] is True
        assert result["framepack_available"] is True
        assert result["cuda_available"] is False


# ============================================================
# 模型加载/卸载测试
# ============================================================

class TestLoadModel:
    """测试模型加载"""

    @patch("app.services.framepack_service._torch_available", False)
    async def test_load_model_no_torch_raises(self, service):
        with pytest.raises(FramePackDependencyError) as exc_info:
            await service.load_model()
        assert "torch" in str(exc_info.value).lower()

    @patch("app.services.framepack_service._torch_available", True)
    @patch("app.services.framepack_service._framepack_available", False)
    async def test_load_model_no_framepack_raises(self, service):
        with pytest.raises(FramePackDependencyError) as exc_info:
            await service.load_model()
        assert "diffusers" in str(exc_info.value).lower()

    @patch("app.services.framepack_service._torch_available", True)
    @patch("app.services.framepack_service._framepack_available", True)
    async def test_load_model_success(self, service):
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.device_count.return_value = 1
        mock_torch.float16 = "float16"

        mock_pipeline = MagicMock()
        mock_pipeline_cls = MagicMock()
        mock_pipeline_cls.from_pretrained.return_value = mock_pipeline

        with (
            patch("app.services.framepack_service.torch", mock_torch),
            patch("app.services.framepack_service.HunyuanVideoPipeline", mock_pipeline_cls),
        ):
            await service.load_model()

        assert service.is_loaded is True
        mock_pipeline_cls.from_pretrained.assert_called_once()
        mock_pipeline.enable_model_cpu_offload.assert_called_once_with(gpu_id=0)

    @patch("app.services.framepack_service._torch_available", True)
    @patch("app.services.framepack_service._framepack_available", True)
    async def test_load_model_skip_if_already_loaded(self, service):
        service._loaded = True
        service.model = MagicMock()

        mock_pipeline_cls = MagicMock()
        with patch("app.services.framepack_service.HunyuanVideoPipeline", mock_pipeline_cls):
            await service.load_model()

        # Should not call from_pretrained again
        mock_pipeline_cls.from_pretrained.assert_not_called()

    @patch("app.services.framepack_service._torch_available", True)
    @patch("app.services.framepack_service._framepack_available", True)
    async def test_load_model_no_cuda_raises(self, service):
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False

        with patch("app.services.framepack_service.torch", mock_torch):
            with pytest.raises(FramePackLoadError, match="CUDA 不可用"):
                await service.load_model()

    @patch("app.services.framepack_service._torch_available", True)
    @patch("app.services.framepack_service._framepack_available", True)
    async def test_load_model_invalid_device_raises(self, service):
        service.gpu_device = 5

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.device_count.return_value = 1

        with patch("app.services.framepack_service.torch", mock_torch):
            with pytest.raises(FramePackLoadError, match="不存在"):
                await service.load_model()

    @patch("app.services.framepack_service._torch_available", True)
    @patch("app.services.framepack_service._framepack_available", True)
    async def test_load_model_oom_raises(self, service):
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.device_count.return_value = 1
        mock_torch.float16 = "float16"

        mock_pipeline_cls = MagicMock()
        mock_pipeline_cls.from_pretrained.side_effect = RuntimeError("CUDA out of memory")

        with (
            patch("app.services.framepack_service.torch", mock_torch),
            patch("app.services.framepack_service.HunyuanVideoPipeline", mock_pipeline_cls),
        ):
            with pytest.raises(FramePackOOMError):
                await service.load_model()


class TestUnloadModel:
    """测试模型卸载"""

    @patch("app.services.framepack_service._torch_available", True)
    async def test_unload_model_clears_state(self, service):
        service.model = MagicMock()
        service._loaded = True

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True

        with patch("app.services.framepack_service.torch", mock_torch):
            await service.unload_model()

        assert service.model is None
        assert service.is_loaded is False

    async def test_unload_model_when_not_loaded(self, service):
        """卸载未加载的模型不应报错"""
        await service.unload_model()
        assert service.model is None
        assert service.is_loaded is False


# ============================================================
# 视频生成测试
# ============================================================

class TestGenerateVideo:
    """测试视频生成功能"""

    @patch("app.services.framepack_service._torch_available", False)
    async def test_generate_video_no_deps_raises(self, service, sample_image):
        with pytest.raises(FramePackDependencyError):
            await service.generate_video(sample_image, "test prompt")

    @patch("app.services.framepack_service._torch_available", True)
    @patch("app.services.framepack_service._framepack_available", True)
    async def test_generate_video_model_not_loaded_raises(self, service, sample_image):
        with pytest.raises(FramePackError, match="模型未加载"):
            await service.generate_video(sample_image, "test prompt")

    @patch("app.services.framepack_service._torch_available", True)
    @patch("app.services.framepack_service._framepack_available", True)
    async def test_generate_video_image_not_found_raises(self, service):
        service._loaded = True
        service.model = MagicMock()

        with pytest.raises(FileNotFoundError, match="不存在"):
            await service.generate_video("/nonexistent/image.png", "test prompt")

    @patch("app.services.framepack_service._torch_available", True)
    @patch("app.services.framepack_service._framepack_available", True)
    async def test_generate_video_invalid_duration_raises(self, service, sample_image):
        service._loaded = True
        service.model = MagicMock()

        with pytest.raises(ValueError, match="duration"):
            await service.generate_video(sample_image, "test", duration=0)

        with pytest.raises(ValueError, match="duration"):
            await service.generate_video(sample_image, "test", duration=-1.0)

    @patch("app.services.framepack_service._torch_available", True)
    @patch("app.services.framepack_service._framepack_available", True)
    async def test_generate_video_invalid_fps_raises(self, service, sample_image):
        service._loaded = True
        service.model = MagicMock()

        with pytest.raises(ValueError, match="fps"):
            await service.generate_video(sample_image, "test", fps=0)

    @patch("app.services.framepack_service._torch_available", True)
    @patch("app.services.framepack_service._framepack_available", True)
    async def test_generate_video_success(self, service, sample_image, tmp_path):
        service._loaded = True

        # Mock the model call
        mock_output = MagicMock()
        mock_output.frames = [[MagicMock()]]  # frames[0] is a list of frame tensors
        mock_model = MagicMock(return_value=mock_output)
        service.model = mock_model

        # Mock PIL and export_to_video
        mock_image = MagicMock()
        mock_image_cls = MagicMock()
        mock_image_cls.open.return_value.convert.return_value = mock_image

        mock_export = MagicMock()

        with (
            patch("app.services.framepack_service.asyncio.get_event_loop") as mock_loop_fn,
        ):
            # We need to run _generate_video_sync directly since run_in_executor
            # is tricky to mock. Instead, mock the sync method.
            videos_dir = tmp_path / "videos"
            videos_dir.mkdir(parents=True, exist_ok=True)
            expected_output = str(videos_dir / "scene_test123.mp4")

            with patch.object(service, "_generate_video_sync", return_value=expected_output):
                mock_loop = MagicMock()
                future = asyncio.Future()
                future.set_result(expected_output)
                mock_loop.run_in_executor.return_value = future
                mock_loop_fn.return_value = mock_loop

                result = await service.generate_video(
                    sample_image, "camera slowly zooms in", duration=3.0, fps=24
                )

        assert result == expected_output

    @patch("app.services.framepack_service._torch_available", True)
    @patch("app.services.framepack_service._framepack_available", True)
    async def test_generate_video_teacache_option(self, service, sample_image, tmp_path):
        """验证 TeaCache 参数被正确传递"""
        service._loaded = True
        service.model = MagicMock()  # model must be set for is_loaded

        videos_dir = tmp_path / "videos"
        videos_dir.mkdir(parents=True, exist_ok=True)
        expected_output = str(videos_dir / "scene_test123.mp4")

        with patch.object(service, "_generate_video_sync", return_value=expected_output) as mock_sync:
            with patch("app.services.framepack_service.asyncio.get_event_loop") as mock_loop_fn:
                mock_loop = MagicMock()
                future = asyncio.Future()
                future.set_result(expected_output)
                mock_loop.run_in_executor.return_value = future
                mock_loop_fn.return_value = mock_loop

                await service.generate_video(
                    sample_image, "test", use_teacache=False
                )

                # Verify _generate_video_sync was called with use_teacache=False
                call_args = mock_loop.run_in_executor.call_args
                # run_in_executor(None, func, image_path, prompt, num_frames, fps, use_teacache)
                positional = call_args[0]
                assert positional[2] == sample_image  # image_path
                assert positional[6] is False  # use_teacache

    @patch("app.services.framepack_service._torch_available", True)
    @patch("app.services.framepack_service._framepack_available", True)
    async def test_generate_video_oom_raises(self, service, sample_image):
        service._loaded = True
        service.model = MagicMock()

        with patch.object(
            service, "_generate_video_sync",
            side_effect=RuntimeError("CUDA out of memory"),
        ):
            with patch("app.services.framepack_service.asyncio.get_event_loop") as mock_loop_fn:
                mock_loop = MagicMock()
                future = asyncio.Future()
                future.set_exception(RuntimeError("CUDA out of memory"))
                mock_loop.run_in_executor.return_value = future
                mock_loop_fn.return_value = mock_loop

                with pytest.raises(FramePackOOMError):
                    await service.generate_video(sample_image, "test")


class TestGenerateVideoSync:
    """测试同步视频生成逻辑（通过 sys.modules mock 本地 import）"""

    def test_teacache_enabled_reduces_steps(self, service, sample_image, tmp_path):
        """TeaCache 启用时 num_inference_steps 应为 20"""
        import sys

        mock_output = MagicMock()
        mock_output.frames = [[MagicMock()]]
        service.model = MagicMock(return_value=mock_output)

        # Mock PIL.Image via sys.modules
        mock_pil = MagicMock()
        mock_pil_image = MagicMock()
        mock_pil.open.return_value.convert.return_value = mock_pil_image

        mock_diffusers_utils = MagicMock()

        with patch.dict(sys.modules, {
            "PIL": MagicMock(Image=mock_pil),
            "PIL.Image": mock_pil,
            "diffusers.utils": mock_diffusers_utils,
        }):
            result = service._generate_video_sync(
                sample_image, "test prompt", num_frames=150, fps=30, use_teacache=True,
            )

        # Verify model was called with num_inference_steps=20 (TeaCache)
        call_kwargs = service.model.call_args
        assert call_kwargs[1]["num_inference_steps"] == 20

    def test_teacache_disabled_keeps_default_steps(self, service, sample_image, tmp_path):
        """TeaCache 禁用时 num_inference_steps 应为 30"""
        import sys

        mock_output = MagicMock()
        mock_output.frames = [[MagicMock()]]
        service.model = MagicMock(return_value=mock_output)

        mock_pil = MagicMock()
        mock_pil.open.return_value.convert.return_value = MagicMock()

        mock_diffusers_utils = MagicMock()

        with patch.dict(sys.modules, {
            "PIL": MagicMock(Image=mock_pil),
            "PIL.Image": mock_pil,
            "diffusers.utils": mock_diffusers_utils,
        }):
            result = service._generate_video_sync(
                sample_image, "test prompt", num_frames=150, fps=30, use_teacache=False,
            )

        call_kwargs = service.model.call_args
        assert call_kwargs[1]["num_inference_steps"] == 30

    def test_output_path_uses_videos_dir(self, service, sample_image, tmp_path):
        """输出路径应在 videos/ 子目录下"""
        import sys

        mock_output = MagicMock()
        mock_output.frames = [[MagicMock()]]
        service.model = MagicMock(return_value=mock_output)

        mock_pil = MagicMock()
        mock_pil.open.return_value.convert.return_value = MagicMock()

        mock_diffusers_utils = MagicMock()

        with patch.dict(sys.modules, {
            "PIL": MagicMock(Image=mock_pil),
            "PIL.Image": mock_pil,
            "diffusers.utils": mock_diffusers_utils,
        }):
            result = service._generate_video_sync(
                sample_image, "test", num_frames=30, fps=30, use_teacache=True,
            )

        assert "videos" in result
        assert result.endswith(".mp4")


# ============================================================
# GPU 信息查询测试
# ============================================================

class TestGetGpuInfo:
    """测试 GPU 信息查询"""

    @patch("app.services.framepack_service._torch_available", False)
    def test_gpu_info_no_torch(self, service):
        result = service.get_gpu_info()
        assert result["available"] is False
        assert "PyTorch" in result["error"]

    @patch("app.services.framepack_service._torch_available", True)
    def test_gpu_info_no_cuda(self, service):
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False

        with patch("app.services.framepack_service.torch", mock_torch):
            result = service.get_gpu_info()

        assert result["available"] is False
        assert "CUDA" in result["error"]

    @patch("app.services.framepack_service._torch_available", True)
    def test_gpu_info_with_cuda(self, service):
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.device_count.return_value = 1
        mock_torch.version.cuda = "12.1"

        # Mock device properties
        mock_props = MagicMock()
        mock_props.name = "NVIDIA GeForce RTX 3060"
        mock_props.total_mem = 6 * (1024 ** 3)  # 6 GB
        mock_props.major = 8
        mock_props.minor = 6
        mock_torch.cuda.get_device_properties.return_value = mock_props
        mock_torch.cuda.memory_allocated.return_value = 1 * (1024 ** 3)  # 1 GB
        mock_torch.cuda.memory_reserved.return_value = 2 * (1024 ** 3)  # 2 GB

        with patch("app.services.framepack_service.torch", mock_torch):
            result = service.get_gpu_info()

        assert result["available"] is True
        assert result["device_count"] == 1
        assert result["current_device"] == 0
        assert result["cuda_version"] == "12.1"
        assert result["model_loaded"] is False
        assert len(result["devices"]) == 1

        device = result["devices"][0]
        assert device["name"] == "NVIDIA GeForce RTX 3060"
        assert device["total_memory_gb"] == 6.0
        assert device["allocated_memory_gb"] == 1.0
        assert device["reserved_memory_gb"] == 2.0
        assert device["free_memory_gb"] == 4.0
        assert device["compute_capability"] == "8.6"

    @patch("app.services.framepack_service._torch_available", True)
    def test_gpu_info_current_device_fallback(self, service):
        """当 gpu_device 超出范围时应回退到 0"""
        service.gpu_device = 99

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.device_count.return_value = 2
        mock_torch.version.cuda = "12.1"

        mock_props = MagicMock()
        mock_props.name = "GPU"
        mock_props.total_mem = 8 * (1024 ** 3)
        mock_props.major = 8
        mock_props.minor = 0
        mock_torch.cuda.get_device_properties.return_value = mock_props
        mock_torch.cuda.memory_allocated.return_value = 0
        mock_torch.cuda.memory_reserved.return_value = 0

        with patch("app.services.framepack_service.torch", mock_torch):
            result = service.get_gpu_info()

        assert result["current_device"] == 0  # fallback

    @patch("app.services.framepack_service._torch_available", True)
    def test_gpu_info_exception_handling(self, service):
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.device_count.side_effect = RuntimeError("GPU error")

        with patch("app.services.framepack_service.torch", mock_torch):
            result = service.get_gpu_info()

        assert result["available"] is False
        assert "GPU error" in result["error"]


# ============================================================
# 异常类测试
# ============================================================

class TestExceptions:
    """测试异常类"""

    def test_framepack_error(self):
        err = FramePackError("test error", code="TEST", retryable=True)
        assert str(err) == "test error"
        assert err.code == "TEST"
        assert err.retryable is True

    @patch("app.services.framepack_service._torch_available", False)
    @patch("app.services.framepack_service._framepack_available", False)
    def test_dependency_error_message(self):
        err = FramePackDependencyError()
        assert "torch" in str(err).lower()
        assert "diffusers" in str(err).lower()
        assert err.code == "FRAMEPACK_DEPENDENCY_ERROR"
        assert err.retryable is False

    def test_load_error(self):
        err = FramePackLoadError("custom message")
        assert str(err) == "custom message"
        assert err.code == "FRAMEPACK_LOAD_ERROR"
        assert err.retryable is True

    def test_oom_error(self):
        err = FramePackOOMError()
        assert "显存" in str(err)
        assert err.code == "FRAMEPACK_OOM"
        assert err.retryable is True

    def test_generation_error(self):
        err = FramePackGenerationError()
        assert err.code == "FRAMEPACK_GENERATION_ERROR"
        assert err.retryable is True


# ============================================================
# 初始化和属性测试
# ============================================================

class TestServiceInit:
    """测试服务初始化"""

    def test_default_init(self):
        svc = FramePackService()
        assert svc.gpu_device == 0
        assert svc.model is None
        assert svc.is_loaded is False
        assert svc.model_id == FramePackService.DEFAULT_MODEL_ID

    def test_custom_init(self, tmp_path):
        svc = FramePackService(
            gpu_device=1,
            model_id="custom/model",
            projects_dir=tmp_path,
        )
        assert svc.gpu_device == 1
        assert svc.model_id == "custom/model"
        assert svc.projects_dir == tmp_path

    def test_is_loaded_property(self, service):
        assert service.is_loaded is False

        service._loaded = True
        service.model = None
        assert service.is_loaded is False  # model is None

        service.model = MagicMock()
        assert service.is_loaded is True
