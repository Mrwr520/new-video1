"""内容模板相关的 Pydantic 数据模型"""

from typing import Optional

from pydantic import BaseModel, Field


class ImageStyle(BaseModel):
    """图像风格参数"""
    style_preset: str = Field(..., description="风格预设名称")
    negative_prompt: str = Field("", description="负面提示词")
    width: int = Field(1024, description="图像宽度")
    height: int = Field(576, description="图像高度")
    guidance_scale: float = Field(7.5, description="引导系数")
    extra: dict = Field(default_factory=dict, description="额外参数")


class MotionStyle(BaseModel):
    """运动风格参数"""
    motion_intensity: float = Field(0.5, ge=0.0, le=1.0, description="运动幅度 0-1")
    fps: int = Field(30, description="帧率")
    duration: float = Field(5.0, description="片段时长（秒）")
    transition_type: str = Field("fade", description="转场类型")


class VoiceConfig(BaseModel):
    """语音配置"""
    engine: str = Field("edge-tts", description="TTS 引擎")
    default_voice: str = Field("zh-CN-XiaoxiaoNeural", description="默认语音")
    speed: float = Field(1.0, description="语速")
    pitch: float = Field(0.0, description="音调偏移")


class SubtitleStyle(BaseModel):
    """字幕样式"""
    font_size: int = Field(24, description="字体大小")
    font_color: str = Field("#FFFFFF", description="字体颜色")
    bg_color: str = Field("#000000AA", description="背景颜色")
    position: str = Field("bottom", description="位置: bottom/top/center")


class ContentTemplateResponse(BaseModel):
    """模板响应模型"""
    id: str
    name: str
    type: str
    character_extraction_prompt: str
    storyboard_prompt: str
    image_style: dict
    motion_style: dict
    voice_config: dict
    subtitle_style: dict
    is_builtin: bool = True


class CreateTemplateRequest(BaseModel):
    """创建自定义模板请求"""
    name: str = Field(..., min_length=1, max_length=100, description="模板名称")
    type: str = Field(..., description="模板类型")
    character_extraction_prompt: Optional[str] = Field(None, description="角色提取 prompt")
    storyboard_prompt: Optional[str] = Field(None, description="分镜生成 prompt")
    image_style: Optional[dict] = Field(None, description="图像风格参数")
    motion_style: Optional[dict] = Field(None, description="运动风格参数")
    voice_config: Optional[dict] = Field(None, description="语音配置")
    subtitle_style: Optional[dict] = Field(None, description="字幕样式")


class UpdateTemplateRequest(BaseModel):
    """更新模板请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="模板名称")
    character_extraction_prompt: Optional[str] = Field(None, description="角色提取 prompt")
    storyboard_prompt: Optional[str] = Field(None, description="分镜生成 prompt")
    image_style: Optional[dict] = Field(None, description="图像风格参数")
    motion_style: Optional[dict] = Field(None, description="运动风格参数")
    voice_config: Optional[dict] = Field(None, description="语音配置")
    subtitle_style: Optional[dict] = Field(None, description="字幕样式")


class TemplateListResponse(BaseModel):
    """模板列表响应"""
    templates: list[ContentTemplateResponse]
    total: int
