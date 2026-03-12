"""分镜管理 API 集成测试"""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_create_and_list_scenes(client):
    """创建分镜并列表查询"""
    res = await client.post("/api/projects", json={"name": "P", "template_id": "anime"})
    pid = res.json()["id"]

    res = await client.get(f"/api/projects/{pid}/scenes")
    assert res.status_code == 200
    assert res.json() == []

    res = await client.post(f"/api/projects/{pid}/scenes", json={
        "scene_description": "城市远景", "dialogue": "故事开始", "camera_direction": "远景"
    })
    assert res.status_code == 201
    scene = res.json()
    assert scene["scene_description"] == "城市远景"
    assert scene["order"] == 1

    # 第二个分镜 order 应为 2
    res = await client.post(f"/api/projects/{pid}/scenes", json={
        "scene_description": "室内", "dialogue": "你好", "camera_direction": "近景"
    })
    assert res.json()["order"] == 2

    res = await client.get(f"/api/projects/{pid}/scenes")
    assert len(res.json()) == 2


@pytest.mark.asyncio
async def test_update_scene(client):
    """更新分镜"""
    res = await client.post("/api/projects", json={"name": "P", "template_id": "anime"})
    pid = res.json()["id"]

    res = await client.post(f"/api/projects/{pid}/scenes", json={
        "scene_description": "A", "dialogue": "B", "camera_direction": "C"
    })
    sid = res.json()["id"]

    res = await client.put(f"/api/projects/{pid}/scenes/{sid}", json={"dialogue": "新台词"})
    assert res.status_code == 200
    assert res.json()["dialogue"] == "新台词"
    assert res.json()["scene_description"] == "A"  # 未修改


@pytest.mark.asyncio
async def test_reorder_scenes(client):
    """重排分镜"""
    res = await client.post("/api/projects", json={"name": "P", "template_id": "anime"})
    pid = res.json()["id"]

    ids = []
    for desc in ["A", "B", "C"]:
        res = await client.post(f"/api/projects/{pid}/scenes", json={
            "scene_description": desc, "dialogue": "d", "camera_direction": "c"
        })
        ids.append(res.json()["id"])

    # 反转顺序
    res = await client.put(f"/api/projects/{pid}/scenes/reorder", json={
        "scene_ids": list(reversed(ids))
    })
    assert res.status_code == 200
    result = res.json()
    assert result[0]["scene_description"] == "C"
    assert result[1]["scene_description"] == "B"
    assert result[2]["scene_description"] == "A"
    assert result[0]["order"] == 1
    assert result[2]["order"] == 3


@pytest.mark.asyncio
async def test_reorder_mismatched_ids(client):
    """重排时 ID 不匹配应返回 400"""
    res = await client.post("/api/projects", json={"name": "P", "template_id": "anime"})
    pid = res.json()["id"]

    await client.post(f"/api/projects/{pid}/scenes", json={
        "scene_description": "A", "dialogue": "d", "camera_direction": "c"
    })

    res = await client.put(f"/api/projects/{pid}/scenes/reorder", json={
        "scene_ids": ["nonexistent-id"]
    })
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_confirm_storyboard(client):
    """确认分镜"""
    res = await client.post("/api/projects", json={"name": "P", "template_id": "anime"})
    pid = res.json()["id"]

    # 没有分镜时确认应失败
    res = await client.post(f"/api/projects/{pid}/confirm-storyboard")
    assert res.status_code == 400

    await client.post(f"/api/projects/{pid}/scenes", json={
        "scene_description": "A", "dialogue": "d", "camera_direction": "c"
    })
    res = await client.post(f"/api/projects/{pid}/confirm-storyboard")
    assert res.status_code == 200
    assert res.json()["count"] == 1


@pytest.mark.asyncio
async def test_delete_scene(client):
    """删除分镜"""
    res = await client.post("/api/projects", json={"name": "P", "template_id": "anime"})
    pid = res.json()["id"]

    res = await client.post(f"/api/projects/{pid}/scenes", json={
        "scene_description": "A", "dialogue": "d", "camera_direction": "c"
    })
    sid = res.json()["id"]

    res = await client.delete(f"/api/projects/{pid}/scenes/{sid}")
    assert res.status_code == 204

    res = await client.get(f"/api/projects/{pid}/scenes")
    assert len(res.json()) == 0


@pytest.mark.asyncio
async def test_scene_includes_video_path(client):
    """分镜响应应包含 video_path 字段"""
    res = await client.post("/api/projects", json={"name": "P", "template_id": "anime"})
    pid = res.json()["id"]

    res = await client.post(f"/api/projects/{pid}/scenes", json={
        "scene_description": "A", "dialogue": "B", "camera_direction": "C"
    })
    scene = res.json()
    assert "video_path" in scene
    assert scene["video_path"] is None


@pytest.mark.asyncio
async def test_regenerate_video_project_not_found(client):
    """项目不存在时返回 404"""
    res = await client.post("/api/projects/nonexistent/scenes/s1/regenerate-video")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_regenerate_video_scene_not_found(client):
    """分镜不存在时返回 404"""
    res = await client.post("/api/projects", json={"name": "P", "template_id": "anime"})
    pid = res.json()["id"]

    res = await client.post(f"/api/projects/{pid}/scenes/nonexistent/regenerate-video")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_regenerate_video_no_keyframe(client):
    """没有关键帧时返回 400"""
    res = await client.post("/api/projects", json={"name": "P", "template_id": "anime"})
    pid = res.json()["id"]

    res = await client.post(f"/api/projects/{pid}/scenes", json={
        "scene_description": "A", "dialogue": "B", "camera_direction": "C"
    })
    sid = res.json()["id"]

    res = await client.post(f"/api/projects/{pid}/scenes/{sid}/regenerate-video")
    assert res.status_code == 400
    assert "关键帧" in res.json()["detail"]


@pytest.mark.asyncio
async def test_regenerate_video_success(client):
    """成功生成视频片段"""
    res = await client.post("/api/projects", json={"name": "P", "template_id": "anime"})
    pid = res.json()["id"]

    res = await client.post(f"/api/projects/{pid}/scenes", json={
        "scene_description": "城市远景", "dialogue": "开始", "camera_direction": "远景"
    })
    sid = res.json()["id"]

    # 先手动设置 keyframe_path
    from app.database import get_connection
    conn = await get_connection()
    await conn.execute(
        "UPDATE scenes SET keyframe_path = ? WHERE id = ?",
        ("/fake/keyframe.png", sid),
    )
    await conn.commit()
    await conn.close()

    # Mock FramePackService.generate_video
    with patch("app.api.scenes.FramePackService") as MockService:
        instance = MockService.return_value
        instance.generate_video = AsyncMock(return_value="/fake/videos/scene.mp4")

        res = await client.post(f"/api/projects/{pid}/scenes/{sid}/regenerate-video")
        assert res.status_code == 200
        data = res.json()
        assert data["video_path"] == "/fake/videos/scene.mp4"
        assert data["id"] == sid

        # 验证调用参数
        instance.generate_video.assert_called_once()
        call_kwargs = instance.generate_video.call_args
        assert call_kwargs.kwargs["image_path"] == "/fake/keyframe.png"


@pytest.mark.asyncio
async def test_regenerate_video_with_custom_params(client):
    """使用自定义参数生成视频"""
    res = await client.post("/api/projects", json={"name": "P", "template_id": "anime"})
    pid = res.json()["id"]

    res = await client.post(f"/api/projects/{pid}/scenes", json={
        "scene_description": "A", "dialogue": "B", "camera_direction": "C",
        "motion_prompt": "camera slowly pans left"
    })
    sid = res.json()["id"]

    from app.database import get_connection
    conn = await get_connection()
    await conn.execute(
        "UPDATE scenes SET keyframe_path = ? WHERE id = ?",
        ("/fake/keyframe.png", sid),
    )
    await conn.commit()
    await conn.close()

    with patch("app.api.scenes.FramePackService") as MockService:
        instance = MockService.return_value
        instance.generate_video = AsyncMock(return_value="/fake/videos/scene.mp4")

        res = await client.post(
            f"/api/projects/{pid}/scenes/{sid}/regenerate-video",
            json={"duration": 3.0, "fps": 24, "use_teacache": False},
        )
        assert res.status_code == 200

        call_kwargs = instance.generate_video.call_args.kwargs
        assert call_kwargs["duration"] == 3.0
        assert call_kwargs["fps"] == 24
        assert call_kwargs["use_teacache"] is False
        assert call_kwargs["prompt"] == "camera slowly pans left"


@pytest.mark.asyncio
async def test_regenerate_video_framepack_error(client):
    """FramePack 失败时返回 502 并包含错误详情"""
    res = await client.post("/api/projects", json={"name": "P", "template_id": "anime"})
    pid = res.json()["id"]

    res = await client.post(f"/api/projects/{pid}/scenes", json={
        "scene_description": "A", "dialogue": "B", "camera_direction": "C"
    })
    sid = res.json()["id"]

    from app.database import get_connection
    conn = await get_connection()
    await conn.execute(
        "UPDATE scenes SET keyframe_path = ? WHERE id = ?",
        ("/fake/keyframe.png", sid),
    )
    await conn.commit()
    await conn.close()

    from app.services.framepack_service import FramePackOOMError
    with patch("app.api.scenes.FramePackService") as MockService:
        instance = MockService.return_value
        instance.generate_video = AsyncMock(side_effect=FramePackOOMError())

        res = await client.post(f"/api/projects/{pid}/scenes/{sid}/regenerate-video")
        assert res.status_code == 502
        detail = res.json()["detail"]
        assert detail["code"] == "FRAMEPACK_OOM"
        assert detail["retryable"] is True
