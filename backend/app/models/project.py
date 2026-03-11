"""项目相关的 Pydantic 数据模型"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CreateProjectRequest(BaseModel):
    """创建项目请求"""
    name: str = Field(..., min_length=1, max_length=200, description="项目名称")
    template_id: str = Field(..., min_length=1, description="内容模板 ID")


class ProjectResponse(BaseModel):
    """项目响应"""
    id: str
    name: str
    template_id: str
    source_text: Optional[str] = None
    status: str = "created"
    current_step: Optional[str] = None
    created_at: str
    updated_at: str


class ProjectListResponse(BaseModel):
    """项目列表响应"""
    projects: list[ProjectResponse]
    total: int


class SubmitTextRequest(BaseModel):
    """提交文本请求"""
    text: str = Field(..., description="文本内容")
    filename: Optional[str] = Field(None, description="原始文件名（用于判断文件类型）")


class TextValidationResponse(BaseModel):
    """文本校验响应"""
    status: str
    message: str
    char_count: int
