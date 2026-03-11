"""项目 CRUD API 端点测试"""

import json
from pathlib import Path

import pytest

from app.database import get_db_path


@pytest.mark.asyncio
async def test_create_project(client):
    """测试创建项目返回正确数据"""
    response = await client.post("/api/projects", json={
        "name": "测试项目",
        "template_id": "anime",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "测试项目"
    assert data["template_id"] == "anime"
    assert data["status"] == "created"
    assert data["id"]  # UUID 非空
    assert data["created_at"]
    assert data["updated_at"]


@pytest.mark.asyncio
async def test_create_project_initializes_directory(client):
    """测试创建项目时初始化目录结构"""
    response = await client.post("/api/projects", json={
        "name": "目录测试",
        "template_id": "science",
    })
    project_id = response.json()["id"]
    project_dir = get_db_path().parent / "projects" / project_id

    assert project_dir.exists()
    assert (project_dir / "keyframes").is_dir()
    assert (project_dir / "videos").is_dir()
    assert (project_dir / "audio").is_dir()
    assert (project_dir / "output").is_dir()

    # 验证 metadata.json
    metadata_path = project_dir / "metadata.json"
    assert metadata_path.exists()
    with open(metadata_path, encoding="utf-8") as f:
        metadata = json.load(f)
    assert metadata["id"] == project_id
    assert metadata["name"] == "目录测试"
    assert metadata["template_id"] == "science"


@pytest.mark.asyncio
async def test_create_project_invalid_name_empty(client):
    """测试创建项目时名称为空应返回 422"""
    response = await client.post("/api/projects", json={
        "name": "",
        "template_id": "anime",
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_project_missing_fields(client):
    """测试创建项目时缺少必填字段应返回 422"""
    response = await client.post("/api/projects", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_projects_empty(client):
    """测试空项目列表"""
    response = await client.get("/api/projects")
    assert response.status_code == 200
    data = response.json()
    assert data["projects"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_projects_multiple(client):
    """测试多个项目的列表返回"""
    # 创建两个项目
    await client.post("/api/projects", json={
        "name": "项目A", "template_id": "anime",
    })
    await client.post("/api/projects", json={
        "name": "项目B", "template_id": "science",
    })

    response = await client.get("/api/projects")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["projects"]) == 2
    # 按创建时间倒序，最新的在前
    names = [p["name"] for p in data["projects"]]
    assert "项目A" in names
    assert "项目B" in names


@pytest.mark.asyncio
async def test_get_project_detail(client):
    """测试获取项目详情"""
    create_resp = await client.post("/api/projects", json={
        "name": "详情测试", "template_id": "math",
    })
    project_id = create_resp.json()["id"]

    response = await client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == project_id
    assert data["name"] == "详情测试"
    assert data["template_id"] == "math"
    assert data["status"] == "created"


@pytest.mark.asyncio
async def test_get_project_not_found(client):
    """测试获取不存在的项目返回 404"""
    response = await client.get("/api/projects/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_project(client):
    """测试删除项目"""
    create_resp = await client.post("/api/projects", json={
        "name": "待删除", "template_id": "anime",
    })
    project_id = create_resp.json()["id"]

    # 确认项目存在
    get_resp = await client.get(f"/api/projects/{project_id}")
    assert get_resp.status_code == 200

    # 删除项目
    del_resp = await client.delete(f"/api/projects/{project_id}")
    assert del_resp.status_code == 204

    # 确认项目已删除
    get_resp = await client.get(f"/api/projects/{project_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_project_removes_files(client):
    """测试删除项目时同时删除文件目录"""
    create_resp = await client.post("/api/projects", json={
        "name": "文件删除测试", "template_id": "anime",
    })
    project_id = create_resp.json()["id"]
    project_dir = get_db_path().parent / "projects" / project_id
    assert project_dir.exists()

    await client.delete(f"/api/projects/{project_id}")
    assert not project_dir.exists()


@pytest.mark.asyncio
async def test_delete_project_not_found(client):
    """测试删除不存在的项目返回 404"""
    response = await client.delete("/api/projects/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_project_unique_ids(client):
    """测试每次创建项目生成唯一 ID"""
    resp1 = await client.post("/api/projects", json={
        "name": "项目1", "template_id": "anime",
    })
    resp2 = await client.post("/api/projects", json={
        "name": "项目2", "template_id": "anime",
    })
    assert resp1.json()["id"] != resp2.json()["id"]
