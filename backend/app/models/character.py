"""角色数据模型

定义角色的 Pydantic 模型，用于 LLM 提取结果和 API 响应。
"""

from typing import Optional

from pydantic import BaseModel, Field


class Character(BaseModel):
    """角色信息"""
    id: str = Field(..., description="角色唯一标识")
    name: str = Field(..., description="角色名称")
    appearance: str = Field("", description="外貌描述")
    personality: str = Field("", description="性格特征")
    background: str = Field("", description="背景信息")
    image_prompt: str = Field("", description="用于图像生成的 prompt")


class CharacterUpdate(BaseModel):
    """角色更新请求"""
    name: Optional[str] = Field(None, min_length=1, description="角色名称")
    appearance: Optional[str] = Field(None, description="外貌描述")
    personality: Optional[str] = Field(None, description="性格特征")
    background: Optional[str] = Field(None, description="背景信息")
    image_prompt: Optional[str] = Field(None, description="图像生成 prompt")
