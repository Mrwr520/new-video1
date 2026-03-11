"""API 路由定义"""

from fastapi import APIRouter

from app.api.projects import router as projects_router

router = APIRouter(prefix="/api")


@router.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "ok"}


# 注册子路由（projects 路由自带 /api/projects 前缀，直接挂载到 app）
# 注意：projects_router 需要在 main.py 中单独注册，因为它已有 /api/projects 前缀
