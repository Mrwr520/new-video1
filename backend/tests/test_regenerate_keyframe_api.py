"""关键帧重新生成 API 集成测试

测试 POST /api/projects/{id}/scenes/{sid}/regenerate-keyframe 端点。
Requirements: 4.3, 4.4, 4.5
"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_regenerate_keyframe_success(client):
    """成功重新生成关键帧，返回更新后的分镜（含 keyframe_path）"""
    # 创建项目和分镜
    res = await client.post("/api/projects", json={"name": "P", "template_id": "anime"})
    pid = res.json()["id"]

    res = await client.post(f"/api/projects/{pid}/scenes", json={
        "scene_description": "城市远景", "dialogue": "开始", "camera_direction": "远景"
    })
    sid = res.json()["id"]

    # Mock 图像生成服务
    with patch("app.api.scenes.ImageGeneratorService") as MockService:
        mock_instance = AsyncMock()
        mock_instance.regenerate_keyframe.return_value = f"/tmp/projects/{pid}/keyframes/scene_{sid}.png"
        mock_instance.close = AsyncMock()
        MockService.return_value = mock_instance

        res = await client.post(f"/api/projects/{pid}/scenes/{sid}/regenerate-keyframe")

    assert res.status_code == 200
    data = res.json()
    assert data["id"] == sid
    assert data["keyframe_path"] is not None
    assert "keyframes" in data["keyframe_path"]
    mock_instance.regenerate_keyframe.assert_called_once()


@pytest.mark.asyncio
async def test_regenerate_keyframe_project_not_found(client):
    """项目不存在时返回 404"""
    res = await client.post("/api/projects/nonexistent/scenes/s1/regenerate-keyframe")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_regenerate_keyframe_scene_not_found(client):
    """分镜不存在时返回 404"""
    res = await client.post("/api/projects", json={"name": "P", "template_id": "anime"})
    pid = res.json()["id"]

    res = await client.post(f"/api/projects/{pid}/scenes/nonexistent/regenerate-keyframe")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_regenerate_keyframe_image_gen_failure(client):
    """图像生成失败时返回 502 并包含错误信息（Req 4.5）"""
    res = await client.post("/api/projects", json={"name": "P", "template_id": "anime"})
    pid = res.json()["id"]

    res = await client.post(f"/api/projects/{pid}/scenes", json={
        "scene_description": "A", "dialogue": "B", "camera_direction": "C"
    })
    sid = res.json()["id"]

    with patch("app.api.scenes.ImageGeneratorService") as MockService:
        from app.services.image_service import ImageGenError
        mock_instance = AsyncMock()
        mock_instance.regenerate_keyframe.side_effect = ImageGenError(
            "API 超时", code="IMAGE_GEN_TIMEOUT", retryable=True
        )
        mock_instance.close = AsyncMock()
        MockService.return_value = mock_instance

        res = await client.post(f"/api/projects/{pid}/scenes/{sid}/regenerate-keyframe")

    assert res.status_code == 502
    detail = res.json()["detail"]
    assert detail["code"] == "IMAGE_GEN_TIMEOUT"
    assert detail["retryable"] is True


@pytest.mark.asyncio
async def test_regenerate_keyframe_updates_db(client):
    """重新生成后 keyframe_path 在数据库中更新"""
    res = await client.post("/api/projects", json={"name": "P", "template_id": "anime"})
    pid = res.json()["id"]

    res = await client.post(f"/api/projects/{pid}/scenes", json={
        "scene_description": "A", "dialogue": "B", "camera_direction": "C"
    })
    sid = res.json()["id"]

    # 初始状态无关键帧
    res = await client.get(f"/api/projects/{pid}/scenes")
    assert res.json()[0]["keyframe_path"] is None

    with patch("app.api.scenes.ImageGeneratorService") as MockService:
        mock_instance = AsyncMock()
        mock_instance.regenerate_keyframe.return_value = "/tmp/keyframe.png"
        mock_instance.close = AsyncMock()
        MockService.return_value = mock_instance

        await client.post(f"/api/projects/{pid}/scenes/{sid}/regenerate-keyframe")

    # 验证 GET 也能看到更新后的 keyframe_path
    res = await client.get(f"/api/projects/{pid}/scenes")
    assert res.json()[0]["keyframe_path"] == "/tmp/keyframe.png"


@pytest.mark.asyncio
async def test_regenerate_keyframe_with_characters(client):
    """重新生成时传入项目角色列表"""
    res = await client.post("/api/projects", json={"name": "P", "template_id": "anime"})
    pid = res.json()["id"]

    # 添加角色
    await client.post(f"/api/projects/{pid}/characters", json={
        "name": "张三", "appearance": "黑发", "personality": "沉稳", "background": "军人"
    })

    res = await client.post(f"/api/projects/{pid}/scenes", json={
        "scene_description": "A", "dialogue": "B", "camera_direction": "C"
    })
    sid = res.json()["id"]

    with patch("app.api.scenes.ImageGeneratorService") as MockService:
        mock_instance = AsyncMock()
        mock_instance.regenerate_keyframe.return_value = "/tmp/keyframe.png"
        mock_instance.close = AsyncMock()
        MockService.return_value = mock_instance

        res = await client.post(f"/api/projects/{pid}/scenes/{sid}/regenerate-keyframe")

    assert res.status_code == 200
    # 验证调用时传入了角色列表
    call_kwargs = mock_instance.regenerate_keyframe.call_args
    characters = call_kwargs.kwargs.get("characters") or call_kwargs[1].get("characters") or call_kwargs[0][1]
    assert len(characters) == 1
    assert characters[0].name == "张三"
