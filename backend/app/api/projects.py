"""项目 CRUD API 路由"""

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.database import get_connection, get_db_path
from app.models.project import (
    CreateProjectRequest,
    ProjectListResponse,
    ProjectResponse,
    SubmitTextRequest,
    TextValidationResponse,
)
from app.services.text_service import parse_file_content, validate_text, ValidationStatus

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _get_projects_root() -> Path:
    """获取项目文件存储根目录（与数据库同级）"""
    return get_db_path().parent / "projects"


def _get_project_dir(project_id: str) -> Path:
    """获取单个项目的目录路径"""
    return _get_projects_root() / project_id


def _init_project_dirs(project_id: str) -> Path:
    """初始化项目目录结构，返回项目目录路径"""
    project_dir = _get_project_dir(project_id)
    for sub in ("keyframes", "videos", "audio", "output"):
        (project_dir / sub).mkdir(parents=True, exist_ok=True)
    return project_dir


def _write_metadata(project_dir: Path, metadata: dict) -> None:
    """写入项目元数据 JSON 文件"""
    with open(project_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


def _row_to_response(row) -> ProjectResponse:
    """将数据库行转换为响应模型"""
    return ProjectResponse(
        id=row["id"],
        name=row["name"],
        template_id=row["template_id"],
        source_text=row["source_text"],
        status=row["status"],
        current_step=row["current_step"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(req: CreateProjectRequest):
    """创建新项目，初始化目录结构"""
    project_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    conn = await get_connection()
    try:
        await conn.execute(
            """INSERT INTO projects (id, name, template_id, status, created_at, updated_at)
               VALUES (?, ?, ?, 'created', ?, ?)""",
            (project_id, req.name, req.template_id, now, now),
        )
        await conn.commit()

        # 初始化项目目录结构
        project_dir = _init_project_dirs(project_id)

        # 写入元数据文件
        _write_metadata(project_dir, {
            "id": project_id,
            "name": req.name,
            "template_id": req.template_id,
            "status": "created",
            "created_at": now,
            "updated_at": now,
        })

        # 读取刚插入的记录
        cursor = await conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        )
        row = await cursor.fetchone()
        return _row_to_response(row)
    finally:
        await conn.close()


@router.get("", response_model=ProjectListResponse)
async def list_projects():
    """获取项目列表"""
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT * FROM projects ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        projects = [_row_to_response(row) for row in rows]
        return ProjectListResponse(projects=projects, total=len(projects))
    finally:
        await conn.close()


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str):
    """获取项目详情（含状态恢复）"""
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="项目不存在")
        return _row_to_response(row)
    finally:
        await conn.close()


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str):
    """删除项目及其所有文件"""
    conn = await get_connection()
    try:
        # 先检查项目是否存在
        cursor = await conn.execute(
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="项目不存在")

        # 删除数据库记录（外键级联删除关联数据）
        await conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        await conn.commit()

        # 删除项目目录
        project_dir = _get_project_dir(project_id)
        if project_dir.exists():
            shutil.rmtree(project_dir)
    finally:
        await conn.close()


@router.post("/{project_id}/text", response_model=TextValidationResponse)
async def submit_text(project_id: str, req: SubmitTextRequest):
    """提交文本内容，进行校验后存储到项目中"""
    conn = await get_connection()
    try:
        # 检查项目是否存在
        cursor = await conn.execute(
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="项目不存在")

        # 如果提供了文件名，先解析文件内容
        text = req.text
        if req.filename:
            text = parse_file_content(text, req.filename)

        # 校验文本
        result = validate_text(text)
        if result.status == ValidationStatus.INVALID:
            return TextValidationResponse(
                status=result.status.value,
                message=result.message,
                char_count=result.char_count,
            )

        # 校验通过，存储文本
        now = datetime.now(timezone.utc).isoformat()
        await conn.execute(
            "UPDATE projects SET source_text = ?, status = 'text_submitted', updated_at = ? WHERE id = ?",
            (text, now, project_id),
        )
        await conn.commit()

        # 更新元数据文件
        project_dir = _get_project_dir(project_id)
        metadata_path = project_dir / "metadata.json"
        if metadata_path.exists():
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            metadata["source_text"] = text
            metadata["status"] = "text_submitted"
            metadata["updated_at"] = now
            _write_metadata(project_dir, metadata)

        return TextValidationResponse(
            status=result.status.value,
            message=result.message,
            char_count=result.char_count,
        )
    finally:
        await conn.close()
