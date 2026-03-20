"""数据库连接和表结构管理"""

import aiosqlite
from pathlib import Path

from app.models.script_optimization import OPTIMIZATION_SCHEMA_SQL, OPTIMIZATION_INDEXES_SQL

# 默认数据库路径
DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "app.db"

# 数据库表创建 SQL
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    template_id TEXT NOT NULL,
    source_text TEXT,
    status TEXT DEFAULT 'created',
    current_step TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    appearance TEXT,
    personality TEXT,
    background TEXT,
    image_prompt TEXT,
    confirmed BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS scenes (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    scene_order INTEGER NOT NULL,
    scene_description TEXT,
    dialogue TEXT,
    camera_direction TEXT,
    image_prompt TEXT,
    motion_prompt TEXT,
    keyframe_path TEXT,
    video_path TEXT,
    audio_path TEXT,
    duration REAL,
    confirmed BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS pipeline_states (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    step TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    progress REAL DEFAULT 0.0,
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);
"""

# 全局数据库连接引用
_db_path: Path = DEFAULT_DB_PATH


def set_db_path(path: Path) -> None:
    """设置数据库文件路径（用于测试等场景）"""
    global _db_path
    _db_path = path


def get_db_path() -> Path:
    """获取当前数据库文件路径"""
    return _db_path


async def get_connection() -> aiosqlite.Connection:
    """获取数据库连接"""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    # 启用外键约束
    await conn.execute("PRAGMA foreign_keys = ON")
    return conn


async def init_db() -> None:
    """初始化数据库，创建所有表"""
    conn = await get_connection()
    try:
        await conn.executescript(SCHEMA_SQL)
        await conn.executescript(OPTIMIZATION_SCHEMA_SQL)
        await conn.executescript(OPTIMIZATION_INDEXES_SQL)
        await conn.commit()
    finally:
        await conn.close()
