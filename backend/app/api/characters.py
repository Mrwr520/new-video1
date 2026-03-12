"""角色管理 API 路由"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.database import get_connection
from app.models.character import Character, CharacterUpdate

router = APIRouter(prefix="/api/projects", tags=["characters"])


@router.get("/{project_id}/characters", response_model=list[Character])
async def list_characters(project_id: str):
    """获取项目的所有角色"""
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="项目不存在")

        cursor = await conn.execute(
            "SELECT * FROM characters WHERE project_id = ? ORDER BY name",
            (project_id,),
        )
        rows = await cursor.fetchall()
        return [_row_to_character(r) for r in rows]
    finally:
        await conn.close()


@router.post("/{project_id}/characters", response_model=Character, status_code=201)
async def create_character(project_id: str, req: CharacterUpdate):
    """手动添加角色（LLM 失败时的降级方案）"""
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="项目不存在")

        char_id = f"char-{uuid.uuid4().hex[:8]}"
        name = req.name or "未命名角色"
        await conn.execute(
            """INSERT INTO characters (id, project_id, name, appearance, personality, background, image_prompt)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (char_id, project_id, name, req.appearance or "", req.personality or "",
             req.background or "", req.image_prompt or ""),
        )
        await conn.commit()

        cursor = await conn.execute("SELECT * FROM characters WHERE id = ?", (char_id,))
        row = await cursor.fetchone()
        return _row_to_character(row)
    finally:
        await conn.close()


@router.put("/{project_id}/characters/{char_id}", response_model=Character)
async def update_character(project_id: str, char_id: str, req: CharacterUpdate):
    """更新角色信息"""
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT * FROM characters WHERE id = ? AND project_id = ?",
            (char_id, project_id),
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="角色不存在")

        updates = {}
        if req.name is not None:
            updates["name"] = req.name
        if req.appearance is not None:
            updates["appearance"] = req.appearance
        if req.personality is not None:
            updates["personality"] = req.personality
        if req.background is not None:
            updates["background"] = req.background
        if req.image_prompt is not None:
            updates["image_prompt"] = req.image_prompt

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            values = list(updates.values()) + [char_id, project_id]
            await conn.execute(
                f"UPDATE characters SET {set_clause} WHERE id = ? AND project_id = ?",
                values,
            )
            await conn.commit()

        cursor = await conn.execute("SELECT * FROM characters WHERE id = ?", (char_id,))
        row = await cursor.fetchone()
        return _row_to_character(row)
    finally:
        await conn.close()


@router.delete("/{project_id}/characters/{char_id}", status_code=204)
async def delete_character(project_id: str, char_id: str):
    """删除角色"""
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT id FROM characters WHERE id = ? AND project_id = ?",
            (char_id, project_id),
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="角色不存在")

        await conn.execute(
            "DELETE FROM characters WHERE id = ? AND project_id = ?",
            (char_id, project_id),
        )
        await conn.commit()
    finally:
        await conn.close()


@router.post("/{project_id}/confirm-characters", status_code=200)
async def confirm_characters(project_id: str):
    """确认角色信息，标记所有角色为已确认"""
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="项目不存在")

        cursor = await conn.execute(
            "SELECT COUNT(*) as cnt FROM characters WHERE project_id = ?",
            (project_id,),
        )
        row = await cursor.fetchone()
        if row["cnt"] == 0:
            raise HTTPException(status_code=400, detail="没有角色可确认")

        await conn.execute(
            "UPDATE characters SET confirmed = TRUE WHERE project_id = ?",
            (project_id,),
        )
        now = datetime.now(timezone.utc).isoformat()
        await conn.execute(
            "UPDATE projects SET current_step = 'characters_confirmed', updated_at = ? WHERE id = ?",
            (now, project_id),
        )
        await conn.commit()
        return {"message": "角色已确认", "count": row["cnt"]}
    finally:
        await conn.close()


def _row_to_character(row) -> Character:
    return Character(
        id=row["id"],
        name=row["name"],
        appearance=row["appearance"] or "",
        personality=row["personality"] or "",
        background=row["background"] or "",
        image_prompt=row["image_prompt"] or "",
    )
