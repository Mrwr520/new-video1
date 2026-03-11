"""数据库初始化和表结构测试"""

import pytest
import aiosqlite

from app.database import get_connection, init_db


@pytest.mark.asyncio
async def test_init_db_creates_tables(tmp_db):
    """测试数据库初始化创建所有必要的表"""
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]
        assert "projects" in tables
        assert "characters" in tables
        assert "scenes" in tables
        assert "pipeline_states" in tables
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_projects_table_schema(tmp_db):
    """测试 projects 表的列结构"""
    conn = await get_connection()
    try:
        cursor = await conn.execute("PRAGMA table_info(projects)")
        columns = {row[1]: row[2] for row in await cursor.fetchall()}
        assert "id" in columns
        assert "name" in columns
        assert "template_id" in columns
        assert "source_text" in columns
        assert "status" in columns
        assert "current_step" in columns
        assert "created_at" in columns
        assert "updated_at" in columns
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_characters_table_schema(tmp_db):
    """测试 characters 表的列结构"""
    conn = await get_connection()
    try:
        cursor = await conn.execute("PRAGMA table_info(characters)")
        columns = {row[1]: row[2] for row in await cursor.fetchall()}
        assert "id" in columns
        assert "project_id" in columns
        assert "name" in columns
        assert "appearance" in columns
        assert "personality" in columns
        assert "confirmed" in columns
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_scenes_table_schema(tmp_db):
    """测试 scenes 表的列结构"""
    conn = await get_connection()
    try:
        cursor = await conn.execute("PRAGMA table_info(scenes)")
        columns = {row[1]: row[2] for row in await cursor.fetchall()}
        assert "id" in columns
        assert "project_id" in columns
        assert "scene_order" in columns
        assert "scene_description" in columns
        assert "dialogue" in columns
        assert "camera_direction" in columns
        assert "keyframe_path" in columns
        assert "video_path" in columns
        assert "audio_path" in columns
        assert "duration" in columns
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_pipeline_states_table_schema(tmp_db):
    """测试 pipeline_states 表的列结构"""
    conn = await get_connection()
    try:
        cursor = await conn.execute("PRAGMA table_info(pipeline_states)")
        columns = {row[1]: row[2] for row in await cursor.fetchall()}
        assert "id" in columns
        assert "project_id" in columns
        assert "step" in columns
        assert "status" in columns
        assert "progress" in columns
        assert "error_message" in columns
        assert "started_at" in columns
        assert "completed_at" in columns
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_foreign_key_enforcement(tmp_db):
    """测试外键约束生效"""
    conn = await get_connection()
    try:
        # 尝试插入引用不存在 project 的 character，应该失败
        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(
                "INSERT INTO characters (id, project_id, name) VALUES (?, ?, ?)",
                ("char-1", "nonexistent-project", "Test"),
            )
            await conn.commit()
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_init_db_idempotent(tmp_db):
    """测试多次初始化数据库不会报错"""
    # 第二次调用 init_db 不应抛出异常
    await init_db()
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]
        assert "projects" in tables
    finally:
        await conn.close()
