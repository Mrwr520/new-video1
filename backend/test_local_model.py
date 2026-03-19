"""测试本地 SDXL 模型加载

验证模型是否能正常加载和生成图片。
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))


async def test_model_manager():
    """测试模型管理器"""
    print("=" * 60)
    print("测试 1: 模型管理器")
    print("=" * 60)
    
    from app.services.model_manager import get_model_manager
    
    manager = get_model_manager()
    
    # 列出所有模型
    models = manager.list_models()
    print(f"\n注册的模型数量: {len(models)}")
    
    for model in models:
        print(f"\n模型: {model.name}")
        print(f"  ID: {model.id}")
        print(f"  状态: {model.status}")
        print(f"  本地路径: {model.local_path}")
        print(f"  下载进度: {model.download_progress * 100:.1f}%")
    
    # 检查 SDXL 模型
    sdxl = manager.get_model("sdxl-base")
    if sdxl:
        print(f"\nSDXL 模型状态: {sdxl.status}")
        if sdxl.local_path:
            path = Path(sdxl.local_path)
            print(f"  路径存在: {path.exists()}")
            if path.exists():
                files = list(path.iterdir())
                print(f"  文件数量: {len(files)}")
                print(f"  关键文件:")
                for key_file in ["model_index.json", "scheduler", "unet", "vae"]:
                    exists = (path / key_file).exists()
                    print(f"    {key_file}: {'✓' if exists else '✗'}")
    
    return sdxl


async def test_local_image_service():
    """测试本地图像生成服务"""
    print("\n" + "=" * 60)
    print("测试 2: 本地图像生成服务")
    print("=" * 60)
    
    from app.services.local_image_service import LocalImageGeneratorService
    
    # 检查依赖
    deps = LocalImageGeneratorService.check_dependencies()
    print(f"\n依赖检查:")
    print(f"  PyTorch: {'✓' if deps['torch_available'] else '✗'}")
    print(f"  Diffusers: {'✓' if deps['diffusers_available'] else '✗'}")
    print(f"  CUDA: {'✓' if deps['cuda_available'] else '✗'}")
    
    if not all(deps.values()):
        print("\n⚠️  依赖不完整，无法继续测试")
        return False
    
    # 创建服务实例
    service = LocalImageGeneratorService(gpu_device=0)
    
    try:
        print("\n正在加载 SDXL 模型...")
        await service.load_model()
        print("✓ 模型加载成功！")
        
        print(f"模型已加载: {service.is_loaded}")
        
        # 测试生成（简单 prompt）
        print("\n正在生成测试图片...")
        from app.models.scene import StoryboardScene
        
        test_scene = StoryboardScene(
            id="test-001",
            order=1,
            scene_description="一个美丽的日落场景",
            dialogue="",
            camera_direction="远景",
            image_prompt="beautiful sunset over mountains, golden hour, cinematic",
            motion_prompt="",
        )
        
        output_path = await service.generate_keyframe(
            scene=test_scene,
            characters=[],
            style_config={
                "width": 512,  # 使用较小尺寸加快测试
                "height": 288,
                "guidance_scale": 7.5,
                "extra": {"steps": 20},  # 减少步数加快测试
            },
            project_id="test",
        )
        
        print(f"✓ 图片生成成功: {output_path}")
        print(f"  文件存在: {Path(output_path).exists()}")
        
        return True
        
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        print("\n正在卸载模型...")
        await service.unload_model()
        print("✓ 模型已卸载")


async def main():
    """主测试流程"""
    print("开始测试本地 SDXL 模型...\n")
    
    # 测试 1: 模型管理器
    sdxl = await test_model_manager()
    
    if not sdxl or sdxl.status != "downloaded":
        print("\n⚠️  SDXL 模型未下载或状态异常，无法继续测试")
        return
    
    # 测试 2: 本地图像生成服务
    success = await test_local_image_service()
    
    print("\n" + "=" * 60)
    if success:
        print("✓ 所有测试通过！本地模型可以正常使用。")
    else:
        print("✗ 测试失败，请检查错误信息。")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
