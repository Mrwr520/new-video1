"""模型管理 API

提供模型列表、状态查询、下载触发、删除等接口。
前端模型管理页面通过这些 API 展示模型状态和下载进度。
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from app.services.model_manager import get_model_manager, ModelStatus

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


@router.get("/models")
async def list_models() -> dict:
    """列出所有模型及其状态"""
    manager = get_model_manager()
    models = manager.list_models()
    return {
        "models": [m.to_dict() for m in models],
        "cache_size_gb": manager.get_cache_size_gb(),
        "active_model": manager.get_active_model(),
    }


@router.get("/models/{model_id}")
async def get_model(model_id: str) -> dict:
    """获取单个模型信息"""
    manager = get_model_manager()
    model = manager.get_model(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail=f"未知模型: {model_id}")
    return model.to_dict()


@router.post("/models/{model_id}/download")
async def download_model(model_id: str) -> dict:
    """触发模型下载（非阻塞，后台执行）"""
    manager = get_model_manager()
    model = manager.get_model(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail=f"未知模型: {model_id}")

    if model.status == ModelStatus.DOWNLOADING:
        return {"message": "模型正在下载中", "status": model.status.value}

    if model.status in (ModelStatus.DOWNLOADED, ModelStatus.LOADED):
        return {"message": "模型已下载", "status": model.status.value}

    # 后台启动下载，立即返回
    async def _bg_download():
        try:
            await manager.download_model(model_id)
        except Exception as e:
            logger.error("后台下载模型失败 %s: %s", model_id, e)

    import asyncio
    asyncio.create_task(_bg_download())

    return {"message": "下载已开始", "status": "downloading"}


@router.delete("/models/{model_id}")
async def delete_model(model_id: str) -> dict:
    """删除本地缓存的模型"""
    manager = get_model_manager()
    try:
        deleted = await manager.delete_model(model_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"模型不存在: {model_id}")
        return {"message": "模型已删除"}
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/gpu")
async def get_gpu_info() -> dict:
    """获取 GPU 信息"""
    manager = get_model_manager()
    return manager.get_gpu_info().to_dict()
