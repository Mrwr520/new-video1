# FramePack 视频生成指南

## 概述

FramePack 是基于腾讯 HunyuanVideo-I2V 的视频生成服务，将静态关键帧转化为动态视频。

## 技术规格

### 官方推荐配置

基于 [HunyuanVideo-I2V 官方文档](https://github.com/Tencent-Hunyuan/HunyuanVideo-I2V)：

- **分辨率**: 720p (1280x720)
- **帧率**: 24 FPS（官方推荐）
- **时长**: 最长 5 秒（129 帧）
- **推理步数**: 50 steps（质量优先）
- **显存需求**: 最低 6GB（使用 CPU offload）

### 生成模式

系统提供三种生成模式：

| 模式        | 步数 | 特点               | 适用场景           |
| ----------- | ---- | ------------------ | ------------------ |
| **stable**  | 50   | 平滑运动，稳定输出 | 大多数场景（推荐） |
| **dynamic** | 50   | 更多运动，动态效果 | 动作场景、快速运动 |
| **fast**    | 30   | 速度优先，质量略降 | 快速预览、测试     |

## 配置方法

### 1. 在配置文件中设置

编辑 `backend/data/config.json`:

```json
{
  "video_gen_mode": "stable", // stable, dynamic, fast
  "gpu_device": 0
}
```

### 2. 在代码中使用

```python
from app.services.framepack_service import FramePackService

# 创建服务实例
service = FramePackService(
    gpu_device=0,
    mode="stable",  # 选择生成模式
)

# 加载模型
await service.load_model()

# 生成视频
video_path = await service.generate_video(
    image_path="path/to/keyframe.png",
    prompt="camera slowly zooms in",
    duration=5.0,  # 最长 5 秒
    fps=24,        # 推荐 24 FPS
    mode="stable", # 可覆盖初始化时的模式
)

# 卸载模型
await service.unload_model()
```

## Prompt 编写技巧

### 运动描述 Prompt

基于社区最佳实践，有效的运动描述包括：

#### 1. 镜头运动

```
- "camera slowly zooms in"（镜头缓慢推进）
- "camera pans left to right"（镜头左右摇移）
- "camera tilts up"（镜头向上倾斜）
- "static camera, no movement"（静态镜头）
- "camera orbits around subject"（镜头环绕主体）
```

#### 2. 主体运动

```
- "character walks forward"（角色向前走）
- "hair flowing in the wind"（头发随风飘动）
- "water rippling gently"（水面轻轻波动）
- "leaves falling slowly"（树叶缓慢飘落）
- "clouds drifting across sky"（云朵飘过天空）
```

#### 3. 组合描述

```
- "camera slowly zooms in while character turns head"
- "static shot with gentle wind movement"
- "camera pans right as sun sets"
```

### Prompt 最佳实践

1. **简洁明确**: 使用简单的英文描述
2. **一个主要运动**: 避免过于复杂的多重运动
3. **速度描述**: 加入 slowly, gently, quickly 等速度词
4. **平滑过渡**: 使用 smooth, gentle, gradual 等词

## 性能优化

### 显存优化

系统已自动启用以下优化：

1. **torch.float16**: 半精度浮点，节省 50% 显存
2. **CPU Offload**: 将部分模型组件卸载到 CPU
3. **VAE Slicing**: 分块处理 VAE，进一步节省显存

### 速度优化

如果生成速度慢，可以：

1. **使用 fast 模式**: 30 steps 而非 50 steps
2. **减少时长**: 3 秒而非 5 秒
3. **降低分辨率**: 540p 而非 720p（需修改图片尺寸）

### 质量优化

获得最佳质量：

1. **使用 stable 模式**: 50 steps，平滑运动
2. **输入高质量关键帧**: 清晰、无噪点的图片
3. **合适的 prompt**: 明确的运动描述
4. **图片尺寸**: 宽高都是 16 的倍数

## 故障排除

### 1. 显存不足 (OOM)

**症状**: 报错 "CUDA out of memory"

**解决方案**:

```python
# 方案 1: 使用 fast 模式
service = FramePackService(mode="fast")

# 方案 2: 减少时长
video_path = await service.generate_video(
    duration=3.0,  # 从 5 秒减少到 3 秒
    ...
)

# 方案 3: 关闭其他 GPU 程序
# 方案 4: 降低图片分辨率
```

### 2. 生成速度慢

**正常速度参考**:

- fast 模式 (30 steps): ~2-3 分钟/视频
- stable 模式 (50 steps): ~4-5 分钟/视频
- dynamic 模式 (50 steps): ~4-5 分钟/视频

**如果明显慢于上述时间**:

- 检查 GPU 利用率
- 确认使用了 CUDA 而非 CPU
- 检查是否有其他程序占用 GPU

### 3. 视频质量差

**可能原因**:

- 输入图片质量低
- prompt 描述不清晰
- 使用了 fast 模式

**改进方法**:

- 使用高质量关键帧
- 优化 prompt 描述
- 切换到 stable 模式

### 4. 运动不自然

**可能原因**:

- prompt 描述过于复杂
- 模式选择不当

**改进方法**:

- 简化 prompt，一次只描述一个主要运动
- 尝试不同模式（stable vs dynamic）
- 调整运动速度描述词

## 测试验证

运行测试脚本验证视频生成功能：

```bash
cd backend
python test_video_generation.py
```

测试内容：

1. 检查 HunyuanVideo 模型是否已下载
2. 验证依赖是否完整
3. 测试三种生成模式（fast, stable, dynamic）
4. 生成测试视频并验证输出

## 与图像生成的协调

系统自动管理 GPU 显存：

1. **关键帧生成阶段**:
   - 加载 SDXL 模型
   - 生成所有关键帧
   - 卸载 SDXL 模型

2. **视频生成阶段**:
   - 加载 HunyuanVideo 模型
   - 生成所有视频片段
   - 卸载 HunyuanVideo 模型

两个模型不会同时占用 GPU，确保在 6GB 显存下也能正常运行。

## 参考资料

- [HunyuanVideo-I2V GitHub](https://github.com/Tencent-Hunyuan/HunyuanVideo-I2V)
- [HunyuanVideo 官方论文](https://arxiv.org/abs/2412.03603)
- [Diffusers 文档](https://huggingface.co/docs/diffusers)

## 社区资源

- [ComfyUI HunyuanVideo 工作流](https://www.runcomfy.com/comfyui-workflows/hunyuanvideo-i2v-workflow-in-comfyui-premium-image-to-video-generation)
- [HunyuanVideo 使用指南](https://stable-diffusion-art.com/hunyuan-video/)
