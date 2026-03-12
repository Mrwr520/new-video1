"""角色管理 API 集成测试"""

import pytest


@pytest.mark.asyncio
async def test_create_and_list_characters(client):
    """创建角色并列表查询"""
    # 先创建项目
    res = await client.post("/api/projects", json={"name": "测试项目", "template_id": "anime"})
    project_id = res.json()["id"]

    # 列表应为空
    res = await client.get(f"/api/projects/{project_id}/characters")
    assert res.status_code == 200
    assert res.json() == []

    # 添加角色
    res = await client.post(f"/api/projects/{project_id}/characters", json={
        "name": "张三", "appearance": "黑发", "personality": "冷静"
    })
    assert res.status_code == 201
    char = res.json()
    assert char["name"] == "张三"
    assert char["appearance"] == "黑发"
    assert char["id"].startswith("char-")

    # 列表应有 1 个
    res = await client.get(f"/api/projects/{project_id}/characters")
    assert len(res.json()) == 1


@pytest.mark.asyncio
async def test_update_character(client):
    """更新角色信息"""
    res = await client.post("/api/projects", json={"name": "P", "template_id": "anime"})
    pid = res.json()["id"]

    res = await client.post(f"/api/projects/{pid}/characters", json={"name": "A"})
    cid = res.json()["id"]

    # 部分更新
    res = await client.put(f"/api/projects/{pid}/characters/{cid}", json={"appearance": "金发碧眼"})
    assert res.status_code == 200
    assert res.json()["appearance"] == "金发碧眼"
    assert res.json()["name"] == "A"  # 未修改字段保持不变


@pytest.mark.asyncio
async def test_delete_character(client):
    """删除角色"""
    res = await client.post("/api/projects", json={"name": "P", "template_id": "anime"})
    pid = res.json()["id"]

    res = await client.post(f"/api/projects/{pid}/characters", json={"name": "X"})
    cid = res.json()["id"]

    res = await client.delete(f"/api/projects/{pid}/characters/{cid}")
    assert res.status_code == 204

    res = await client.get(f"/api/projects/{pid}/characters")
    assert len(res.json()) == 0


@pytest.mark.asyncio
async def test_confirm_characters(client):
    """确认角色"""
    res = await client.post("/api/projects", json={"name": "P", "template_id": "anime"})
    pid = res.json()["id"]

    # 没有角色时确认也应成功（跳过角色步骤）
    res = await client.post(f"/api/projects/{pid}/confirm-characters")
    assert res.status_code == 200
    assert res.json()["count"] == 0

    # 添加角色后确认
    await client.post(f"/api/projects/{pid}/characters", json={"name": "A"})
    await client.post(f"/api/projects/{pid}/characters", json={"name": "B"})

    res = await client.post(f"/api/projects/{pid}/confirm-characters")
    assert res.status_code == 200
    assert res.json()["count"] == 2


@pytest.mark.asyncio
async def test_character_not_found(client):
    """角色不存在时返回 404"""
    res = await client.post("/api/projects", json={"name": "P", "template_id": "anime"})
    pid = res.json()["id"]

    res = await client.put(f"/api/projects/{pid}/characters/nonexistent", json={"name": "X"})
    assert res.status_code == 404

    res = await client.delete(f"/api/projects/{pid}/characters/nonexistent")
    assert res.status_code == 404
