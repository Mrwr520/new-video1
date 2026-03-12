"""分镜场景数据模型

定义分镜脚本的 Pydantic 模型，用于 LLM 生成结果和 API 响应。
"""

from typing import Optional

from pydantic import BaseModel, Field


class StoryboardScene(BaseModel):
    """分镜场景"""
    id: str = Field(..., description="场景唯一标识")
    order: int = Field(..., description="场景顺序")
    scene_description: str = Field(..., description="场景描述")
    dialogue: str = Field(..., description="台词/旁白")
    camera_direction: str = Field(..., description="镜头指示")
    image_prompt: str = Field("", description="图像生成 prompt")
    motion_prompt: str = Field("", description="FramePack 运动 prompt")
    keyframe_path: Optional[str] = Field(None, description="关键帧图片路径")
    video_path: Optional[str] = Field(None, description="视频片段路径")
    audio_path: Optional[str] = Field(None, description="语音音频路径")


class SceneUpdate(BaseModel):
    """分镜更新请求"""
    scene_description: Optional[str] = Field(None, description="场景描述")
    dialogue: Optional[str] = Field(None, description="台词/旁白")
    camera_direction: Optional[str] = Field(None, description="镜头指示")
    image_prompt: Optional[str] = Field(None, description="图像生成 prompt")
    motion_prompt: Optional[str] = Field(None, description="运动 prompt")
