"""版本管理器单元测试

使用内存 SQLite 数据库测试 VersionManager 的所有方法。
"""

import pytest
import pytest_asyncio
import aiosqlite

from app.models.script_optimization import OPTIMIZATION_SCHEMA_SQL
from app.schemas.script_optimization import (
    DimensionScores,
    EvaluationResult,
    Hotspot,
    ScriptVersion,
    Technique,
)
from app.services.version_manager import VersionManager


def _make_evaluation(total_score: float = 7.5) -> EvaluationResult:
    """创建测试用评审结果。"""
    return EvaluationResult(
        total_score=total_score,
        dimension_scores=DimensionScores(
            content_quality=8.0,
            structure=7.0,
            creativity=7.5,
            hotspot_relevance=6.5,
            technique_application=7.0,
        ),
        suggestions=["改进结构", "增加创意"],
    )


def _make_hotspots() -> list[Hotspot]:
    return [
        Hotspot(
            title="热点1",
            description="描述1",
            source="来源1",
            relevance_score=0.9,
        )
    ]


def _make_techniques() -> list[Technique]:
    return [
        Technique(
            name="技巧1",
            description="描述1",
            example="示例1",
            category="类别1",
            source="来源1",
        )
    ]


@pytest_asyncio.fixture
async def db():
    """创建内存数据库并初始化 schema。"""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.executescript(OPTIMIZATION_SCHEMA_SQL)
    # 插入一个 session 供外键引用
    await conn.execute(
        """
        INSERT INTO optimization_sessions (id, initial_prompt, target_score, max_iterations, status)
        VALUES ('sess-1', 'test prompt', 8.0, 20, 'running')
        """,
    )
    await conn.commit()
    yield conn
    await conn.close()


@pytest_asyncio.fixture
async def vm(db: aiosqlite.Connection) -> VersionManager:
    return VersionManager(db)


@pytest.mark.asyncio
async def test_save_version_returns_script_version(vm: VersionManager):
    """save_version 应返回包含完整信息的 ScriptVersion。"""
    evaluation = _make_evaluation(7.5)
    version = await vm.save_version(
        session_id="sess-1",
        iteration=0,
        script="初始剧本内容",
        evaluation=evaluation,
        hotspots=_make_hotspots(),
        techniques=_make_techniques(),
    )

    assert isinstance(version, ScriptVersion)
    assert version.session_id == "sess-1"
    assert version.iteration == 0
    assert version.script == "初始剧本内容"
    assert version.evaluation.total_score == 7.5
    assert version.is_final is False
    assert len(version.hotspots) == 1
    assert len(version.techniques) == 1


@pytest.mark.asyncio
async def test_save_version_persists_to_db(vm: VersionManager, db: aiosqlite.Connection):
    """save_version 应将数据持久化到数据库。"""
    await vm.save_version(
        session_id="sess-1",
        iteration=0,
        script="剧本内容",
        evaluation=_make_evaluation(),
        hotspots=[],
        techniques=[],
    )

    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM script_versions WHERE session_id = 'sess-1'"
    )
    row = await cursor.fetchone()
    assert row["cnt"] == 1


@pytest.mark.asyncio
async def test_save_version_stores_scores_and_suggestions(vm: VersionManager):
    """save_version 应保存分数、评审意见和时间戳（需求 6.1）。"""
    evaluation = _make_evaluation(8.5)
    evaluation.suggestions = ["建议A", "建议B", "建议C"]

    version = await vm.save_version(
        session_id="sess-1",
        iteration=1,
        script="优化后的剧本",
        evaluation=evaluation,
        hotspots=_make_hotspots(),
        techniques=_make_techniques(),
    )

    # 从数据库重新读取验证
    loaded = await vm.get_version("sess-1", 1)
    assert loaded is not None
    assert loaded.evaluation.total_score == 8.5
    assert loaded.evaluation.dimension_scores.content_quality == 8.0
    assert loaded.evaluation.suggestions == ["建议A", "建议B", "建议C"]
    assert loaded.timestamp is not None


@pytest.mark.asyncio
async def test_get_versions_returns_all_ordered(vm: VersionManager):
    """get_versions 应返回所有版本，按迭代次数排序（需求 6.2）。"""
    for i in range(5):
        await vm.save_version(
            session_id="sess-1",
            iteration=i,
            script=f"剧本版本 {i}",
            evaluation=_make_evaluation(5.0 + i),
            hotspots=[],
            techniques=[],
        )

    versions = await vm.get_versions("sess-1")
    assert len(versions) == 5
    assert [v.iteration for v in versions] == [0, 1, 2, 3, 4]
    assert all(v.session_id == "sess-1" for v in versions)


@pytest.mark.asyncio
async def test_get_versions_empty_session(vm: VersionManager):
    """get_versions 对不存在的会话应返回空列表。"""
    versions = await vm.get_versions("nonexistent")
    assert versions == []


@pytest.mark.asyncio
async def test_get_version_returns_specific(vm: VersionManager):
    """get_version 应返回特定版本的完整信息（需求 6.3）。"""
    await vm.save_version(
        session_id="sess-1",
        iteration=0,
        script="版本0",
        evaluation=_make_evaluation(6.0),
        hotspots=[],
        techniques=[],
    )
    await vm.save_version(
        session_id="sess-1",
        iteration=1,
        script="版本1",
        evaluation=_make_evaluation(7.5),
        hotspots=_make_hotspots(),
        techniques=_make_techniques(),
    )

    version = await vm.get_version("sess-1", 1)
    assert version is not None
    assert version.iteration == 1
    assert version.script == "版本1"
    assert version.evaluation.total_score == 7.5
    assert len(version.hotspots) == 1
    assert len(version.techniques) == 1


@pytest.mark.asyncio
async def test_get_version_not_found(vm: VersionManager):
    """get_version 对不存在的版本应返回 None。"""
    result = await vm.get_version("sess-1", 99)
    assert result is None


@pytest.mark.asyncio
async def test_mark_final_version(vm: VersionManager):
    """mark_final_version 应标记指定版本为最终版本（需求 6.4）。"""
    for i in range(3):
        await vm.save_version(
            session_id="sess-1",
            iteration=i,
            script=f"版本{i}",
            evaluation=_make_evaluation(6.0 + i),
            hotspots=[],
            techniques=[],
        )

    await vm.mark_final_version("sess-1", 2)

    versions = await vm.get_versions("sess-1")
    for v in versions:
        if v.iteration == 2:
            assert v.is_final is True
        else:
            assert v.is_final is False


@pytest.mark.asyncio
async def test_mark_final_version_clears_previous(vm: VersionManager):
    """mark_final_version 应清除之前的最终标记。"""
    for i in range(3):
        await vm.save_version(
            session_id="sess-1",
            iteration=i,
            script=f"版本{i}",
            evaluation=_make_evaluation(),
            hotspots=[],
            techniques=[],
        )

    # 先标记版本 1
    await vm.mark_final_version("sess-1", 1)
    v1 = await vm.get_version("sess-1", 1)
    assert v1 is not None and v1.is_final is True

    # 再标记版本 2，版本 1 应被清除
    await vm.mark_final_version("sess-1", 2)
    v1 = await vm.get_version("sess-1", 1)
    v2 = await vm.get_version("sess-1", 2)
    assert v1 is not None and v1.is_final is False
    assert v2 is not None and v2.is_final is True


@pytest.mark.asyncio
async def test_save_version_with_empty_hotspots_and_techniques(vm: VersionManager):
    """save_version 应正确处理空的热点和技巧列表。"""
    version = await vm.save_version(
        session_id="sess-1",
        iteration=0,
        script="简单剧本",
        evaluation=_make_evaluation(),
        hotspots=[],
        techniques=[],
    )

    loaded = await vm.get_version("sess-1", 0)
    assert loaded is not None
    assert loaded.hotspots == []
    assert loaded.techniques == []


@pytest.mark.asyncio
async def test_save_duplicate_iteration_raises(vm: VersionManager):
    """save_version 对同一会话的重复迭代应抛出错误（UNIQUE 约束）。"""
    await vm.save_version(
        session_id="sess-1",
        iteration=0,
        script="版本0",
        evaluation=_make_evaluation(),
        hotspots=[],
        techniques=[],
    )

    with pytest.raises(Exception):
        await vm.save_version(
            session_id="sess-1",
            iteration=0,
            script="重复版本0",
            evaluation=_make_evaluation(),
            hotspots=[],
            techniques=[],
        )
