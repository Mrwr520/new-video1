"""迁移 001: 添加剧本迭代优化系统表

创建以下表：
- optimization_sessions: 优化会话表
- script_versions: 剧本版本表
- search_cache: 搜索缓存表（可选）

添加索引以优化常见查询模式。

需求：6.1
"""

import asyncio
import sys
from pathlib import Path

import aiosqlite

# 允许独立运行时导入 app 模块
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

MIGRATION_SQL = """
-- 优化会话表
CREATE TABLE IF NOT EXISTS optimization_sessions (
    id TEXT PRIMARY KEY,
    initial_prompt TEXT NOT NULL,
    target_score REAL NOT NULL,
    max_iterations INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'running'
);

-- 剧本版本表
CREATE TABLE IF NOT EXISTS script_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    iteration INTEGER NOT NULL,
    script TEXT NOT NULL,
    total_score REAL NOT NULL,
    dimension_scores TEXT NOT NULL,
    suggestions TEXT NOT NULL,
    hotspots TEXT,
    techniques TEXT,
    is_final BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES optimization_sessions(id),
    UNIQUE(session_id, iteration)
);

-- 搜索缓存表（可选，用于减少 API 调用）
CREATE TABLE IF NOT EXISTS search_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_hash TEXT UNIQUE NOT NULL,
    search_type TEXT NOT NULL,
    results TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);

-- 索引：按 session_id 查询版本
CREATE INDEX IF NOT EXISTS idx_script_versions_session_id
    ON script_versions(session_id);

-- 索引：按 session_id + iteration 查询特定版本
CREATE INDEX IF NOT EXISTS idx_script_versions_session_iteration
    ON script_versions(session_id, iteration);

-- 索引：查询最终版本
CREATE INDEX IF NOT EXISTS idx_script_versions_is_final
    ON script_versions(is_final);

-- 索引：按状态查询会话
CREATE INDEX IF NOT EXISTS idx_optimization_sessions_status
    ON optimization_sessions(status);

-- 索引：按创建时间排序会话
CREATE INDEX IF NOT EXISTS idx_optimization_sessions_created_at
    ON optimization_sessions(created_at);

-- 索引：搜索缓存按 query_hash 查找
CREATE INDEX IF NOT EXISTS idx_search_cache_query_hash
    ON search_cache(query_hash);

-- 索引：搜索缓存过期清理
CREATE INDEX IF NOT EXISTS idx_search_cache_expires_at
    ON search_cache(expires_at);
"""


async def run_migration(db_path: str | Path) -> None:
    """执行迁移脚本

    Args:
        db_path: 数据库文件路径
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = await aiosqlite.connect(str(db_path))
    try:
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.executescript(MIGRATION_SQL)
        await conn.commit()
        print(f"Migration 001 applied successfully to {db_path}")
    finally:
        await conn.close()


async def main() -> None:
    """独立运行迁移脚本的入口"""
    from app.database import get_db_path
    db_path = get_db_path()
    await run_migration(db_path)


if __name__ == "__main__":
    asyncio.run(main())
