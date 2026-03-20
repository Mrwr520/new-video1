"""剧本迭代优化系统的数据库模型

定义 optimization_sessions、script_versions 和 search_cache 表的 SQL schema，
以及数据库操作的辅助函数。
"""

# 数据库表创建 SQL
OPTIMIZATION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS optimization_sessions (
    id TEXT PRIMARY KEY,
    initial_prompt TEXT NOT NULL,
    target_score REAL NOT NULL,
    max_iterations INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'running'
);

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

CREATE TABLE IF NOT EXISTS search_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_hash TEXT UNIQUE NOT NULL,
    search_type TEXT NOT NULL,
    results TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);
"""

# 索引创建 SQL
OPTIMIZATION_INDEXES_SQL = """
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
