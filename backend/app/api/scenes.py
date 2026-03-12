"""分镜管理 API 路由"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import get_connection
from app.models.character import Character
from app.models.scene import StoryboardScene, SceneUpdate
from app.services.image_service import ImageGeneratorService, ImageGenError
from app.services.framepack_service import FramePackService, FramePackError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["scenes"])


class ReorderRequest(BaseModel):
    scene_ids: list[str]


@router.get("/{project_id}/scenes", response_model=list[StoryboardScene])
async def list_scenes(project_id: str):
    conn = await get_connection()
    try:
        cursor = await conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="项目不存在")
        cursor = await conn.execute(
            "SELECT * FROM scenes WHERE project_id = ? ORDER BY scene_order", (project_id,),
        )
        return [_row_to_scene(r) for r in await cursor.fetchall()]
    finally:
        await conn.close()


@router.post("/{project_id}/scenes", response_model=StoryboardScene, status_code=201)
async def create_scene(project_id: str, req: SceneUpdate):
    conn = await get_connection()
    try:
        cursor = await conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="项目不存在")
        cursor = await conn.execute(
            "SELECT COALESCE(MAX(scene_order), 0) as max_order FROM scenes WHERE project_id = ?",
            (project_id,),
        )
        row = await cursor.fetchone()
        scene_id = f"scene-{uuid.uuid4().hex[:8]}"
        await conn.execute(
            """INSERT INTO scenes (id, project_id, scene_order, scene_description, dialogue,
               camera_direction, image_prompt, motion_prompt) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (scene_id, project_id, row["max_order"] + 1,
             req.scene_description or "", req.dialogue or "",
             req.camera_direction or "", req.image_prompt or "", req.motion_prompt or ""),
        )
        await conn.commit()
        cursor = await conn.execute("SELECT * FROM scenes WHERE id = ?", (scene_id,))
        return _row_to_scene(await cursor.fetchone())
    finally:
        await conn.close()


# IMPORTANT: reorder must be defined BEFORE {scene_id} routes to avoid path conflict
@router.put("/{project_id}/scenes/reorder")
async def reorder_scenes(project_id: str, req: ReorderRequest):
    conn = await get_connection()
    try:
        cursor = await conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="项目不存在")
        cursor = await conn.execute("SELECT id FROM scenes WHERE project_id = ?", (project_id,))
        existing_ids = {row["id"] for row in await cursor.fetchall()}
        if existing_ids != set(req.scene_ids):
            raise HTTPException(status_code=400, detail="分镜 ID 列表与项目不匹配")
        for idx, sid in enumerate(req.scene_ids):
            await conn.execute(
                "UPDATE scenes SET scene_order = ? WHERE id = ? AND project_id = ?",
                (idx + 1, sid, project_id),
            )
        await conn.commit()
        cursor = await conn.execute(
            "SELECT * FROM scenes WHERE project_id = ? ORDER BY scene_order", (project_id,),
        )
        return [_row_to_scene(r) for r in await cursor.fetchall()]
    finally:
        await conn.close()


@router.put("/{project_id}/scenes/{scene_id}", response_model=StoryboardScene)
async def update_scene(project_id: str, scene_id: str, req: SceneUpdate):
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT * FROM scenes WHERE id = ? AND project_id = ?", (scene_id, project_id),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="分镜不存在")
        updates = {}
        for field in ("scene_description", "dialogue", "camera_direction", "image_prompt", "motion_prompt"):
            val = getattr(req, field)
            if val is not None:
                updates[field] = val
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [scene_id, project_id]
            await conn.execute(f"UPDATE scenes SET {set_clause} WHERE id = ? AND project_id = ?", values)
            await conn.commit()
        cursor = await conn.execute("SELECT * FROM scenes WHERE id = ?", (scene_id,))
        return _row_to_scene(await cursor.fetchone())
    finally:
        await conn.close()


@router.delete("/{project_id}/scenes/{scene_id}", status_code=204)
async def delete_scene(project_id: str, scene_id: str):
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT id FROM scenes WHERE id = ? AND project_id = ?", (scene_id, project_id),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="分镜不存在")
        await conn.execute("DELETE FROM scenes WHERE id = ? AND project_id = ?", (scene_id, project_id))
        await conn.commit()
    finally:
        await conn.close()


@router.post("/{project_id}/confirm-storyboard", status_code=200)
async def confirm_storyboard(project_id: str):
    conn = await get_connection()
    try:
        cursor = await conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="项目不存在")
        cursor = await conn.execute(
            "SELECT COUNT(*) as cnt FROM scenes WHERE project_id = ?", (project_id,),
        )
        row = await cursor.fetchone()
        if row["cnt"] == 0:
            raise HTTPException(status_code=400, detail="没有分镜可确认")
        await conn.execute("UPDATE scenes SET confirmed = TRUE WHERE project_id = ?", (project_id,))
        now = datetime.now(timezone.utc).isoformat()
        await conn.execute(
            "UPDATE projects SET current_step = 'storyboard_confirmed', updated_at = ? WHERE id = ?",
            (now, project_id),
        )
        await conn.commit()
        return {"message": "分镜已确认", "count": row["cnt"]}
    finally:
        await conn.close()


@router.post("/{project_id}/scenes/{scene_id}/regenerate-keyframe")
async def regenerate_keyframe(project_id: str, scene_id: str):
    """重新生成指定分镜的关键帧图片。

    调用 ImageGeneratorService 重新生成关键帧，并将结果路径存入数据库。
    Requirements: 4.4, 4.5
    """
    conn = await get_connection()
    try:
        # 验证项目存在
        cursor = await conn.execute("SELECT id, template_id FROM projects WHERE id = ?", (project_id,))
        project_row = await cursor.fetchone()
        if not project_row:
            raise HTTPException(status_code=404, detail="项目不存在")

        # 验证分镜存在
        cursor = await conn.execute(
            "SELECT * FROM scenes WHERE id = ? AND project_id = ?", (scene_id, project_id),
        )
        scene_row = await cursor.fetchone()
        if not scene_row:
            raise HTTPException(status_code=404, detail="分镜不存在")

        # 构建 StoryboardScene 对象
        scene = _row_to_scene(scene_row)

        # 获取项目角色列表
        cursor = await conn.execute(
            "SELECT * FROM characters WHERE project_id = ?", (project_id,),
        )
        characters = [
            Character(
                id=r["id"], name=r["name"],
                appearance=r["appearance"] or "",
                personality=r["personality"] or "",
                background=r["background"] or "",
                image_prompt=r["image_prompt"] or "",
            )
            for r in await cursor.fetchall()
        ]

        # 获取模板风格配置
        style_config = _get_style_config(project_row["template_id"])

        # 调用图像生成服务
        service = ImageGeneratorService()
        try:
            keyframe_path = await service.regenerate_keyframe(
                scene=scene,
                characters=characters,
                style_config=style_config,
                project_id=project_id,
            )
        except ImageGenError as e:
            logger.error("关键帧重新生成失败: %s", e)
            raise HTTPException(
                status_code=502,
                detail={
                    "code": e.code,
                    "message": f"关键帧生成失败: {e}",
                    "retryable": e.retryable,
                },
            )
        finally:
            await service.close()

        # 更新数据库中的 keyframe_path
        await conn.execute(
            "UPDATE scenes SET keyframe_path = ? WHERE id = ? AND project_id = ?",
            (keyframe_path, scene_id, project_id),
        )
        await conn.commit()

        # 返回更新后的分镜
        cursor = await conn.execute("SELECT * FROM scenes WHERE id = ?", (scene_id,))
        return _row_to_scene(await cursor.fetchone())
    finally:
        await conn.close()


class RegenerateVideoRequest(BaseModel):
    """视频重新生成请求参数"""
    duration: float = 5.0
    fps: int = 30
    use_teacache: bool = True


@router.post("/{project_id}/scenes/{scene_id}/regenerate-video")
async def regenerate_video(project_id: str, scene_id: str, req: RegenerateVideoRequest = RegenerateVideoRequest()):
    """重新生成指定分镜的视频片段。

    调用 FramePackService 将关键帧图片转化为动态视频片段，并将结果路径存入数据库。
    Requirements: 5.3, 5.5
    """
    conn = await get_connection()
    try:
        # 验证项目存在
        cursor = await conn.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="项目不存在")

        # 验证分镜存在
        cursor = await conn.execute(
            "SELECT * FROM scenes WHERE id = ? AND project_id = ?", (scene_id, project_id),
        )
        scene_row = await cursor.fetchone()
        if not scene_row:
            raise HTTPException(status_code=404, detail="分镜不存在")

        # 检查关键帧是否存在
        keyframe_path = scene_row["keyframe_path"]
        if not keyframe_path:
            raise HTTPException(status_code=400, detail="请先生成关键帧图片")

        scene = _row_to_scene(scene_row)

        # 调用 FramePack 服务生成视频
        service = FramePackService()
        try:
            video_path = await service.generate_video(
                image_path=keyframe_path,
                prompt=scene.motion_prompt or scene.scene_description,
                duration=req.duration,
                fps=req.fps,
                use_teacache=req.use_teacache,
            )
        except FramePackError as e:
            logger.error("视频片段生成失败: %s", e)
            raise HTTPException(
                status_code=502,
                detail={
                    "code": e.code,
                    "message": f"视频生成失败: {e}",
                    "retryable": e.retryable,
                },
            )

        # 更新数据库中的 video_path
        await conn.execute(
            "UPDATE scenes SET video_path = ? WHERE id = ? AND project_id = ?",
            (video_path, scene_id, project_id),
        )
        await conn.commit()

        # 返回更新后的分镜
        cursor = await conn.execute("SELECT * FROM scenes WHERE id = ?", (scene_id,))
        return _row_to_scene(await cursor.fetchone())
    finally:
        await conn.close()


def _get_style_config(template_id: str) -> dict:
    """根据模板 ID 获取图像风格配置"""
    try:
        from app.services.template_service import TemplateService
        template_service = TemplateService()
        # 尝试直接匹配
        template = template_service.get_template(template_id)
        if template is None:
            # 尝试 builtin- 前缀匹配
            template = template_service.get_template(f"builtin-{template_id}")
        if template and hasattr(template, 'image_style'):
            return template.image_style
    except Exception:
        pass
    return {}


def _row_to_scene(row) -> StoryboardScene:
    return StoryboardScene(
        id=row["id"], order=row["scene_order"],
        scene_description=row["scene_description"] or "",
        dialogue=row["dialogue"] or "",
        camera_direction=row["camera_direction"] or "",
        image_prompt=row["image_prompt"] or "",
        motion_prompt=row["motion_prompt"] or "",
        keyframe_path=row["keyframe_path"],
        video_path=row["video_path"],
        audio_path=row["audio_path"],
    )
