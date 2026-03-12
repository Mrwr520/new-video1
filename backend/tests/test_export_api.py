"""导出 API 端点测试

测试 POST /api/projects/{id}/export 和 GET /api/projects/{id}/files/{path} 端点。

Requirements:
    7.4: 合成完成后提供完整视频的预览播放功能
    7.5: 输出 MP4 格式的视频文件，分辨率不低于 1080p
    7.7: 合成失败时显示错误详情并提供重试选项
"""

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from app.database import get_connection, get_db_path
from app.services.ffmpeg_service import (
    FFmpegCompositionError,
    FFmpegNotFoundError,
)


async def _create_project(client, name="测试项目", template_id="builtin-anime"):
    """辅助函数：创建测试项目"""
    res = await client.post("/api/projects", json={"name": name, "template_id": template_id})
    assert res.status_code == 201
    return res.json()


async def _add_scene_with_video(client, project_id, order=1, video_path="/fake/video.mp4",
                                 audio_path=None, dialogue="测试台词"):
    """辅助函数：向项目添加带视频路径的分镜"""
    conn = await get_connection()
    try:
        scene_id = f"scene-{uuid.uuid4().hex[:8]}"
        await conn.execute(
            """INSERT INTO scenes (id, project_id, scene_order, scene_description, dialogue,
               camera_direction, video_path, audio_path, duration)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (scene_id, project_id, order, f"场景{order}", dialogue,
             "中景", video_path, audio_path, 5.0),
        )
        await conn.commit()
        return scene_id
    finally:
        await conn.close()


async def _add_scene_without_video(client, project_id, order=1):
    """辅助函数：向项目添加没有视频的分镜"""
    conn = await get_connection()
    try:
        scene_id = f"scene-{uuid.uuid4().hex[:8]}"
        await conn.execute(
            """INSERT INTO scenes (id, project_id, scene_order, scene_description, dialogue,
               camera_direction) VALUES (?, ?, ?, ?, ?, ?)""",
            (scene_id, project_id, order, f"场景{order}", "台词", "中景"),
        )
        await conn.commit()
        return scene_id
    finally:
        await conn.close()


# ============================================================
# POST /api/projects/{id}/export 测试
# ============================================================

class TestExportEndpoint:
    """测试导出视频端点"""

    @pytest.mark.asyncio
    async def test_export_project_not_found(self, client):
        """项目不存在时返回 404"""
        res = await client.post("/api/projects/nonexistent/export")
        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_export_no_scenes(self, client):
        """项目没有分镜时返回 400"""
        project = await _create_project(client)
        res = await client.post(f"/api/projects/{project['id']}/export")
        assert res.status_code == 400
        assert "没有分镜" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_export_no_video_clips(self, client):
        """分镜没有视频片段时返回 400"""
        project = await _create_project(client)
        await _add_scene_without_video(client, project["id"])
        res = await client.post(f"/api/projects/{project['id']}/export")
        assert res.status_code == 400
        assert "没有已生成的视频片段" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_export_success(self, client):
        """成功导出视频"""
        project = await _create_project(client)
        await _add_scene_with_video(client, project["id"], order=1)
        await _add_scene_with_video(client, project["id"], order=2, video_path="/fake/v2.mp4")

        with patch(
            "app.api.export.FFmpegCompositor"
        ) as MockCompositor:
            mock_instance = MockCompositor.return_value
            mock_instance.compose_final_video = AsyncMock(
                return_value="/output/final.mp4"
            )

            res = await client.post(f"/api/projects/{project['id']}/export")

        assert res.status_code == 200
        data = res.json()
        assert data["video_path"] == "/output/final.mp4"
        assert data["message"] == "视频导出成功"

        # 验证 compose_final_video 被正确调用
        mock_instance.compose_final_video.assert_called_once()
        call_args = mock_instance.compose_final_video.call_args
        assert call_args.kwargs["project_id"] == project["id"]
        assert len(call_args.kwargs["scenes"]) == 2

    @pytest.mark.asyncio
    async def test_export_with_custom_config(self, client):
        """使用自定义输出配置导出"""
        project = await _create_project(client)
        await _add_scene_with_video(client, project["id"])

        with patch(
            "app.api.export.FFmpegCompositor"
        ) as MockCompositor:
            mock_instance = MockCompositor.return_value
            mock_instance.compose_final_video = AsyncMock(
                return_value="/output/final.mp4"
            )

            res = await client.post(
                f"/api/projects/{project['id']}/export",
                json={
                    "resolution_width": 3840,
                    "resolution_height": 2160,
                    "fps": 60,
                    "codec": "h265",
                    "bitrate": "16M",
                },
            )

        assert res.status_code == 200
        call_args = mock_instance.compose_final_video.call_args
        config = call_args.kwargs["output_config"]
        assert config.resolution == (3840, 2160)
        assert config.fps == 60
        assert config.codec == "h265"
        assert config.bitrate == "16M"

    @pytest.mark.asyncio
    async def test_export_ffmpeg_not_found(self, client):
        """FFmpeg 未安装时返回 502"""
        project = await _create_project(client)
        await _add_scene_with_video(client, project["id"])

        with patch(
            "app.api.export.FFmpegCompositor"
        ) as MockCompositor:
            mock_instance = MockCompositor.return_value
            mock_instance.compose_final_video = AsyncMock(
                side_effect=FFmpegNotFoundError()
            )

            res = await client.post(f"/api/projects/{project['id']}/export")

        assert res.status_code == 502
        detail = res.json()["detail"]
        assert detail["code"] == "FFMPEG_NOT_FOUND"
        assert detail["retryable"] is False

    @pytest.mark.asyncio
    async def test_export_ffmpeg_composition_error(self, client):
        """FFmpeg 合成失败时返回 502 并包含错误详情"""
        project = await _create_project(client)
        await _add_scene_with_video(client, project["id"])

        with patch(
            "app.api.export.FFmpegCompositor"
        ) as MockCompositor:
            mock_instance = MockCompositor.return_value
            mock_instance.compose_final_video = AsyncMock(
                side_effect=FFmpegCompositionError("编码失败", "codec error detail")
            )

            res = await client.post(f"/api/projects/{project['id']}/export")

        assert res.status_code == 502
        detail = res.json()["detail"]
        assert detail["code"] == "FFMPEG_COMPOSITION_ERROR"
        assert detail["retryable"] is True
        assert "detail" in detail

    @pytest.mark.asyncio
    async def test_export_updates_project_status(self, client):
        """导出成功后更新项目状态"""
        project = await _create_project(client)
        await _add_scene_with_video(client, project["id"])

        with patch(
            "app.api.export.FFmpegCompositor"
        ) as MockCompositor:
            mock_instance = MockCompositor.return_value
            mock_instance.compose_final_video = AsyncMock(
                return_value="/output/final.mp4"
            )

            await client.post(f"/api/projects/{project['id']}/export")

        # 验证项目状态已更新
        res = await client.get(f"/api/projects/{project['id']}")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "completed"
        assert data["current_step"] == "exported"

    @pytest.mark.asyncio
    async def test_export_builds_composition_scenes_correctly(self, client):
        """验证 CompositionScene 列表构建正确"""
        project = await _create_project(client)
        await _add_scene_with_video(
            client, project["id"], order=1,
            video_path="/v1.mp4", audio_path="/a1.wav", dialogue="台词一"
        )
        await _add_scene_with_video(
            client, project["id"], order=2,
            video_path="/v2.mp4", audio_path=None, dialogue="台词二"
        )

        with patch(
            "app.api.export.FFmpegCompositor"
        ) as MockCompositor:
            mock_instance = MockCompositor.return_value
            mock_instance.compose_final_video = AsyncMock(
                return_value="/output/final.mp4"
            )

            await client.post(f"/api/projects/{project['id']}/export")

        call_args = mock_instance.compose_final_video.call_args
        scenes = call_args.kwargs["scenes"]
        assert len(scenes) == 2

        # 第一个场景
        assert scenes[0].video_path == "/v1.mp4"
        assert scenes[0].audio_path == "/a1.wav"
        assert scenes[0].subtitle_text == "台词一"
        assert scenes[0].start_time == 0.0

        # 第二个场景
        assert scenes[1].video_path == "/v2.mp4"
        assert scenes[1].audio_path is None
        assert scenes[1].subtitle_text == "台词二"
        assert scenes[1].start_time == 5.0  # cumulative


# ============================================================
# GET /api/projects/{id}/files/{path} 测试
# ============================================================

class TestFileServingEndpoint:
    """测试文件服务端点"""

    @pytest.mark.asyncio
    async def test_file_project_not_found(self, client):
        """项目不存在时返回 404"""
        res = await client.get("/api/projects/nonexistent/files/output/final.mp4")
        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_file_not_found(self, client):
        """文件不存在时返回 404"""
        project = await _create_project(client)
        res = await client.get(f"/api/projects/{project['id']}/files/output/nonexistent.mp4")
        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_serve_existing_file(self, client):
        """成功返回存在的文件"""
        project = await _create_project(client)
        project_id = project["id"]

        # 创建测试文件
        projects_root = get_db_path().parent / "projects"
        test_file = projects_root / project_id / "output" / "test.txt"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("hello", encoding="utf-8")

        res = await client.get(f"/api/projects/{project_id}/files/output/test.txt")
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_serve_mp4_file_content_type(self, client):
        """MP4 文件返回正确的 content-type"""
        project = await _create_project(client)
        project_id = project["id"]

        projects_root = get_db_path().parent / "projects"
        test_file = projects_root / project_id / "output" / "final.mp4"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_bytes(b"\x00" * 10)

        res = await client.get(f"/api/projects/{project_id}/files/output/final.mp4")
        assert res.status_code == 200
        assert "video/mp4" in res.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, client):
        """路径遍历攻击被阻止"""
        project = await _create_project(client)
        project_id = project["id"]

        # 尝试路径遍历
        res = await client.get(f"/api/projects/{project_id}/files/../../etc/passwd")
        assert res.status_code in (403, 404)
