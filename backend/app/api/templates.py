"""模板 CRUD API 路由"""

from fastapi import APIRouter, HTTPException

from app.models.template import (
    ContentTemplateResponse,
    CreateTemplateRequest,
    UpdateTemplateRequest,
    TemplateListResponse,
)
from app.services.template_service import ContentTemplate, TemplateService

router = APIRouter(prefix="/api/templates", tags=["templates"])

# 模板服务单例
_template_service = TemplateService()


def get_template_service() -> TemplateService:
    """获取模板服务实例（便于测试替换）"""
    return _template_service


def set_template_service(service: TemplateService) -> None:
    """替换模板服务实例（用于测试）"""
    global _template_service
    _template_service = service


def _to_response(tpl: ContentTemplate) -> ContentTemplateResponse:
    """将 ContentTemplate 转换为 API 响应模型"""
    return ContentTemplateResponse(
        id=tpl.id,
        name=tpl.name,
        type=tpl.type,
        character_extraction_prompt=tpl.character_extraction_prompt,
        storyboard_prompt=tpl.storyboard_prompt,
        image_style=tpl.image_style,
        motion_style=tpl.motion_style,
        voice_config=tpl.voice_config,
        subtitle_style=tpl.subtitle_style,
        is_builtin=tpl.is_builtin,
    )


@router.get("", response_model=TemplateListResponse)
async def list_templates():
    """列出所有模板"""
    svc = get_template_service()
    templates = svc.list_templates()
    return TemplateListResponse(
        templates=[_to_response(t) for t in templates],
        total=len(templates),
    )


@router.get("/{template_id}", response_model=ContentTemplateResponse)
async def get_template(template_id: str):
    """根据 ID 获取模板"""
    svc = get_template_service()
    tpl = svc.get_template(template_id)
    if tpl is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    return _to_response(tpl)


@router.post("", response_model=ContentTemplateResponse, status_code=201)
async def create_template(req: CreateTemplateRequest):
    """创建自定义模板"""
    svc = get_template_service()
    data = req.model_dump(exclude_none=True)
    tpl = svc.create_custom_template(data)
    return _to_response(tpl)


@router.put("/{template_id}", response_model=ContentTemplateResponse)
async def update_template(template_id: str, req: UpdateTemplateRequest):
    """更新模板"""
    svc = get_template_service()
    data = req.model_dump(exclude_none=True)
    tpl = svc.update_template(template_id, data)
    if tpl is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    return _to_response(tpl)
