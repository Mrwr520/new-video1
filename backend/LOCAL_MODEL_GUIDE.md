# 本地模型使用指南

## 当前状态

✅ **两个模型都已下载并可用**

- **SDXL Base**: 图像生成模型（已下载，100%）
- **HunyuanVideo**: 视频生成模型（已下载，100%）

模型位置: `C:\Users\XOS\.ai-video-generator\models\`

## 配置说明

### 图像生成模式

在 `backend/data/config.json` 中配置 `image_gen_mode`:

```json
{
  "image_gen_mode": "local", // 使用本地 SDXL 模型
  "gpu_device": 0 // 使用第一个 GPU
}
```

支持的模式：

- `"local"`: 使用本地 SDXL 模型（需要 GPU）
- `"api"`: 使用远程 API（OpenAI/Replicate 等）
- `"mock"`: 模拟生成（用于测试，不需要模型或 API）

### 视频生成

视频生成自动使用本地 HunyuanVideo 模型，无需额外配置。

## 测试验证

运行测试脚本验证模型是否正常工作：

```bash
cd backend
python test_local_model.py
```

测试内容：

1. 检查模型是否已下载
2. 验证模型文件完整性
3. 加载 SDXL 模型到 GPU
4. 生成测试图片
5. 卸载模型释放显存

## 使用流程

### 1. 生成关键帧（使用 SDXL）

```python
from app.services.local_image_service import LocalImageGeneratorService

service = LocalImageGeneratorService(gpu_device=0)
await service.load_model()  # 加载模型到 GPU

# 生成关键帧
keyframe_path = await service.generate_keyframe(
    scene=scene,
    characters=characters,
    style_config=template.image_style,
    project_id=project_id,
)

await service.unload_model()  # 卸载模型释放显存
```

### 2. 生成视频（使用 HunyuanVideo）

```python
from app.services.framepack_service import FramePackService

service = FramePackService(gpu_device=0)
await service.load_model()  # 加载模型到 GPU

# 生成视频
video_path = await service.generate_video(
    image_path=keyframe_path,
    prompt="camera slowly zooms in",
    duration=5.0,
    fps=30,
)

await service.unload_model()  # 卸载模型
```

## GPU 显存管理

系统自动协调两个模型的 GPU 使用：

1. **生成关键帧阶段**：
   - 加载 SDXL 模型
   - 生成所有关键帧
   - 卸载 SDXL 模型

2. **生成视频阶段**：
   - 加载 HunyuanVideo 模型
   - 生成所有视频片段
   - 卸载 HunyuanVideo 模型

两个模型不会同时占用 GPU，确保在 6GB 显存下也能正常运行。

## 性能优化

### SDXL 优化

- 使用 `torch.float16` 精度（节省显存）
- 启用 `enable_model_cpu_offload`（CPU 卸载）
- 可调整生成步数（`steps`）平衡质量和速度

### HunyuanVideo 优化

- 使用 `torch.float16` 精度
- 启用 `enable_model_cpu_offload`
- 可启用 TeaCache 加速（减少推理步数）

## 故障排除

### 1. 显存不足 (OOM)

**症状**: 报错 "CUDA out of memory"

**解决方案**:

- 降低图像分辨率（如 1024x576 → 768x432）
- 减少生成步数（如 30 → 20）
- 关闭其他占用 GPU 的程序
- 使用 `mock` 模式测试流程

### 2. 模型加载失败

**症状**: 报错 "模型加载失败"

**解决方案**:

- 检查模型文件是否完整：`python test_local_model.py`
- 重新下载模型（在前端"模型管理"页面）
- 检查 CUDA 和 PyTorch 是否正确安装

### 3. 生成速度慢

**优化建议**:

- 减少生成步数（quality vs speed）
- 使用较小的图像尺寸
- 启用 TeaCache（视频生成）
- 确保使用 GPU 而非 CPU

## 依赖要求

```bash
# 必需依赖
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
pip install diffusers transformers accelerate safetensors

# 可选依赖（用于测试）
pip install Pillow
```

## 测试结果

最新测试（成功）：

- ✅ 模型管理器正常
- ✅ SDXL 模型加载成功
- ✅ 图片生成成功（512x288, 20 steps, ~12 秒）
- ✅ 模型卸载正常

## 下一步

现在你可以：

1. 在前端创建项目
2. 输入文本内容
3. 系统会自动使用本地 SDXL 模型生成关键帧
4. 然后使用本地 HunyuanVideo 模型生成视频

完全离线运行，无需 API Key！
