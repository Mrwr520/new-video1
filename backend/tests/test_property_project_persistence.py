"""
属性测试：项目持久化往返一致性

Feature: ai-video-generator, Property 12: 项目持久化往返一致性
**Validates: Requirements 8.2, 8.3**

对任意项目数据（名称、模板 ID），通过 API 创建后再读取，
应当得到与创建时等价的项目状态。
"""

import asyncio

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from httpx import ASGITransport, AsyncClient

from app.database import init_db, set_db_path
from app.main import app


# --- 策略定义 ---

# 项目名称：1~200 个可打印字符（排除纯空白，因为 Pydantic min_length=1 会拒绝空串）
project_name_st = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "S", "Z")),
    min_size=1,
    max_size=200,
).filter(lambda s: s.strip())

# 模板 ID：非空字符串，模拟真实模板标识
template_id_st = st.text(
    alphabet=st.characters(categories=("L", "N")),
    min_size=1,
    max_size=50,
)


# --- 辅助函数 ---

def run_async(coro):
    """在新事件循环中运行异步协程"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _round_trip(name: str, template_id: str):
    """创建项目后读取，返回 (创建响应, 读取响应)"""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        set_db_path(db_path)
        await init_db()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 创建项目
            create_resp = await client.post("/api/projects", json={
                "name": name,
                "template_id": template_id,
            })
            assert create_resp.status_code == 201, (
                f"创建失败: {create_resp.status_code} {create_resp.text}"
            )
            created = create_resp.json()

            # 读取项目
            get_resp = await client.get(f"/api/projects/{created['id']}")
            assert get_resp.status_code == 200, (
                f"读取失败: {get_resp.status_code} {get_resp.text}"
            )
            fetched = get_resp.json()

    return created, fetched


# --- 属性测试 ---

@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(name=project_name_st, template_id=template_id_st)
def test_property_12_project_persistence_round_trip(name, template_id):
    """
    Property 12: 项目持久化往返一致性

    对任意项目名称和模板 ID，创建项目后再通过 GET 读取，
    返回的数据应与创建时的响应完全一致。

    **Validates: Requirements 8.2, 8.3**
    """
    created, fetched = run_async(_round_trip(name, template_id))

    # 核心断言：创建后读取得到等价数据
    assert fetched["id"] == created["id"], "项目 ID 不一致"
    assert fetched["name"] == created["name"], "项目名称不一致"
    assert fetched["name"] == name, "项目名称与输入不一致"
    assert fetched["template_id"] == created["template_id"], "模板 ID 不一致"
    assert fetched["template_id"] == template_id, "模板 ID 与输入不一致"
    assert fetched["status"] == created["status"], "项目状态不一致"
    assert fetched["status"] == "created", "新项目状态应为 created"
    assert fetched["created_at"] == created["created_at"], "创建时间不一致"
    assert fetched["updated_at"] == created["updated_at"], "更新时间不一致"
