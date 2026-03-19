"""测试 FramePack 视频生成

验证 HunyuanVideo-I2V 模型是否能正常生成视频。
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))


async def test_framepack_service():
    """测试 FramePack 视频生成服务"""
    print("=" * 60)
    print("测试 FramePack 视频生成服务")
    print("=" * 60)
    
    from app.services.framepack_service import FramePackService
    from app.services.model_manager import get_model_manager
    
    # 检查模型状态
    manager = get_model_manager()
    hunyuan = manager.get_model("hunyuan-video")
    
    if not hunyuan or hunyuan.status != "downloaded":
        print("\n⚠️  HunyuanVideo 模型未下载")
        print(f"   状态: {hunyuan.status if hunyuan else 'unknown'}")
        print("   请先在前端'模型管理'页面下载模型")
        return False
    
    print(f"\n✓ HunyuanVideo 模型已下载")
    print(f"  路径: {hunyuan.local_path}")
    
    # 检查依赖
    deps = FramePackService.check_dependencies()
    print(f"\n依赖检查:")
    print(f"  PyTorch: {'✓' if deps['torch_available'] else '✗'}")
    print(f"  Diffusers: {'✓' if deps['framepack_available'] else '✗'}")
    print(f"  CUDA: {'✓' if deps['cuda_available'] else '✗'}")
    
    if not all(deps.values()):
        print("\n⚠️  依赖不完整，无法继续测试")
        return False
    
    # 检查测试图片
    test_image = Path("backend/projects/test/keyframes/scene_test-001.png")
    if not test_image.exists():
        print(f"\n⚠️  测试图片不存在: {test_image}")
        print("   请先运行 test_local_model.py 生成测试图片")
        return False
    
    print(f"\n✓ 测试图片存在: {test_image}")
    
    # 测试三种模式
    modes = ["fast", "stable", "dynamic"]
    
    for mode in modes:
        print(f"\n{'=' * 60}")
        print(f"测试模式: {mode.upper()}")
        print(f"{'=' * 60}")
        
        service = FramePackService(
            gpu_device=0,
            mode=mode,
        )
        
        try:
            print(f"\n正在加载 HunyuanVideo 模型...")
            await service.load_model()
            print(f"✓ 模型加载成功 (模式: {mode})")
            
            print(f"\n正在生成测试视频...")
            print(f"  模式: {mode}")
            print(f"  时长: 3 秒")
            print(f"  帧率: 24 FPS")
            
            video_path = await service.generate_video(
                image_path=str(test_image),
                prompt="camera slowly zooms in, smooth movement",
                duration=3.0,  # 使用较短时长加快测试
                fps=24,
                mode=mode,
            )
            
            print(f"\n✓ 视频生成成功: {video_path}")
            print(f"  文件存在: {Path(video_path).exists()}")
            
            if Path(video_path).exists():
                size_mb = Path(video_path).stat().st_size / (1024 * 1024)
                print(f"  文件大小: {size_mb:.2f} MB")
            
        except Exception as e:
            print(f"\n✗ 错误: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            print(f"\n正在卸载模型...")
            await service.unload_model()
            print(f"✓ 模型已卸载")
    
    return True


async def main():
    """主测试流程"""
    print("开始测试 FramePack 视频生成...\n")
    
    success = await test_framepack_service()
    
    print("\n" + "=" * 60)
    if success:
        print("✓ 所有测试通过！视频生成功能正常。")
        print("\n生成模式说明:")
        print("  - fast: 30 steps, 速度优先")
        print("  - stable: 50 steps, 平滑运动（推荐）")
        print("  - dynamic: 50 steps, 更多运动")
    else:
        print("✗ 测试失败，请检查错误信息。")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
