"""FFmpeg 合成器服务测试

测试 FFmpegCompositor 的命令构建、SRT 字幕生成和合成流程。
FFmpeg 子进程调用通过 mock 进行测试。

Requirements:
    7.1: 视频片段按分镜顺序拼接
    7.2: 音视频同步合成
    7.3: 字幕生成（SRT 格式）和嵌入
    7.5: MP4 导出（1080p、h264 编码）
    7.6: 转场效果
"""

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ffmpeg_service import (
    CompositionScene,
    FFmpegCommandBuilder,
    FFmpegCompositor,
    FFmpegCompositionError,
    FFmpegNotFoundError,
    OutputConfig,
    SubtitleEntry,
    format_srt_timestamp,
    generate_srt_content,
    generate_subtitles_from_scenes,
    write_srt_file,
)


# ============================================================
# SRT 时间戳格式化测试
# ============================================================

class TestFormatSrtTimestamp:
    """测试 SRT 时间戳格式化"""

    def test_zero_seconds(self):
        assert format_srt_timestamp(0.0) == "00:00:00,000"

    def test_simple_seconds(self):
        assert format_srt_timestamp(1.0) == "00:00:01,000"

    def test_with_milliseconds(self):
        assert format_srt_timestamp(1.5) == "00:00:01,500"

    def test_minutes(self):
        assert format_srt_timestamp(65.0) == "00:01:05,000"

    def test_hours(self):
        assert format_srt_timestamp(3661.5) == "01:01:01,500"

    def test_negative_clamped_to_zero(self):
        assert format_srt_timestamp(-5.0) == "00:00:00,000"

    def test_fractional_milliseconds(self):
        result = format_srt_timestamp(1.234)
        assert result == "00:00:01,234"

    def test_large_value(self):
        result = format_srt_timestamp(7200.0)
        assert result == "02:00:00,000"


# ============================================================
# SRT 内容生成测试
# ============================================================

class TestGenerateSrtContent:
    """测试 SRT 字幕内容生成"""

    def test_empty_entries(self):
        assert generate_srt_content([]) == ""

    def test_single_entry(self):
        entries = [SubtitleEntry(index=1, start_time=0.0, end_time=5.0, text="你好世界")]
        result = generate_srt_content(entries)
        lines = result.split("\n")
        assert lines[0] == "1"
        assert lines[1] == "00:00:00,000 --> 00:00:05,000"
        assert lines[2] == "你好世界"
        assert lines[3] == ""  # blank separator

    def test_multiple_entries(self):
        entries = [
            SubtitleEntry(index=1, start_time=0.0, end_time=3.0, text="第一句"),
            SubtitleEntry(index=2, start_time=3.0, end_time=6.0, text="第二句"),
            SubtitleEntry(index=3, start_time=6.0, end_time=10.0, text="第三句"),
        ]
        result = generate_srt_content(entries)
        assert "1\n00:00:00,000 --> 00:00:03,000\n第一句" in result
        assert "2\n00:00:03,000 --> 00:00:06,000\n第二句" in result
        assert "3\n00:00:06,000 --> 00:00:10,000\n第三句" in result

    def test_entries_preserve_order(self):
        entries = [
            SubtitleEntry(index=1, start_time=0.0, end_time=2.0, text="A"),
            SubtitleEntry(index=2, start_time=2.0, end_time=4.0, text="B"),
        ]
        result = generate_srt_content(entries)
        pos_a = result.index("A")
        pos_b = result.index("B")
        assert pos_a < pos_b


# ============================================================
# 从场景生成字幕测试
# ============================================================

class TestGenerateSubtitlesFromScenes:
    """测试从合成场景生成字幕条目"""

    def test_empty_scenes(self):
        assert generate_subtitles_from_scenes([]) == []

    def test_scenes_without_subtitles(self):
        scenes = [
            CompositionScene(video_path="/v1.mp4", subtitle_text=None, start_time=0, duration=5),
            CompositionScene(video_path="/v2.mp4", subtitle_text="", start_time=5, duration=5),
        ]
        assert generate_subtitles_from_scenes(scenes) == []

    def test_scenes_with_subtitles(self):
        scenes = [
            CompositionScene(video_path="/v1.mp4", subtitle_text="你好", start_time=0, duration=3),
            CompositionScene(video_path="/v2.mp4", subtitle_text="世界", start_time=3, duration=4),
        ]
        entries = generate_subtitles_from_scenes(scenes)
        assert len(entries) == 2
        assert entries[0].index == 1
        assert entries[0].text == "你好"
        assert entries[0].start_time == 0.0
        assert entries[0].end_time == 3.0
        assert entries[1].index == 2
        assert entries[1].text == "世界"
        assert entries[1].start_time == 3.0
        assert entries[1].end_time == 7.0

    def test_mixed_scenes_with_and_without_subtitles(self):
        scenes = [
            CompositionScene(video_path="/v1.mp4", subtitle_text="有字幕", start_time=0, duration=3),
            CompositionScene(video_path="/v2.mp4", subtitle_text=None, start_time=3, duration=3),
            CompositionScene(video_path="/v3.mp4", subtitle_text="也有字幕", start_time=6, duration=4),
        ]
        entries = generate_subtitles_from_scenes(scenes)
        assert len(entries) == 2
        assert entries[0].index == 1
        assert entries[0].text == "有字幕"
        assert entries[1].index == 2
        assert entries[1].text == "也有字幕"

    def test_whitespace_only_subtitle_skipped(self):
        scenes = [
            CompositionScene(video_path="/v1.mp4", subtitle_text="   ", start_time=0, duration=3),
        ]
        assert generate_subtitles_from_scenes(scenes) == []


# ============================================================
# SRT 文件写入测试
# ============================================================

class TestWriteSrtFile:
    """测试 SRT 文件写入"""

    def test_write_srt_file(self, tmp_path):
        entries = [
            SubtitleEntry(index=1, start_time=0.0, end_time=5.0, text="测试字幕"),
        ]
        output_path = str(tmp_path / "test.srt")
        result = write_srt_file(entries, output_path)
        assert result == output_path
        assert os.path.exists(output_path)

        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "测试字幕" in content
        assert "00:00:00,000 --> 00:00:05,000" in content

    def test_write_creates_parent_dirs(self, tmp_path):
        output_path = str(tmp_path / "sub" / "dir" / "test.srt")
        entries = [SubtitleEntry(index=1, start_time=0, end_time=1, text="hi")]
        write_srt_file(entries, output_path)
        assert os.path.exists(output_path)

    def test_write_empty_entries(self, tmp_path):
        output_path = str(tmp_path / "empty.srt")
        write_srt_file([], output_path)
        with open(output_path, "r", encoding="utf-8") as f:
            assert f.read() == ""


# ============================================================
# FFmpeg 命令构建器测试
# ============================================================

class TestFFmpegCommandBuilder:
    """测试 FFmpeg 命令构建"""

    def setup_method(self):
        self.builder = FFmpegCommandBuilder()
        self.config = OutputConfig(
            resolution=(1920, 1080), fps=30, codec="h264", format="mp4", bitrate="8M"
        )

    # --- 拼接命令 ---

    def test_concat_single_clip(self):
        cmd = self.builder.build_concat_command(["/clip1.mp4"], "/out.mp4", self.config)
        assert cmd[0] == "ffmpeg"
        assert "-y" in cmd
        assert "-i" in cmd
        assert "/clip1.mp4" in cmd
        assert "scale=1920:1080" in " ".join(cmd)
        assert "libx264" in cmd
        assert "/out.mp4" in cmd

    def test_concat_multiple_clips(self):
        cmd = self.builder.build_concat_command(
            ["/c1.mp4", "/c2.mp4", "/c3.mp4"], "/out.mp4", self.config
        )
        assert cmd.count("-i") == 3
        assert "-filter_complex" in cmd
        filter_idx = cmd.index("-filter_complex")
        filter_str = cmd[filter_idx + 1]
        assert "concat=n=3:v=1:a=0" in filter_str
        assert "[outv]" in filter_str

    def test_concat_uses_correct_codec(self):
        config = OutputConfig(codec="h265")
        cmd = self.builder.build_concat_command(["/c.mp4"], "/out.mp4", config)
        assert "h265" in cmd

    def test_concat_uses_h264_for_h264_codec(self):
        cmd = self.builder.build_concat_command(["/c.mp4"], "/out.mp4", self.config)
        assert "libx264" in cmd

    # --- 音视频合并命令 ---

    def test_audio_merge_command(self):
        cmd = self.builder.build_audio_merge_command("/v.mp4", "/a.wav", "/out.mp4")
        assert cmd[0] == "ffmpeg"
        assert "/v.mp4" in cmd
        assert "/a.wav" in cmd
        assert "-shortest" in cmd
        assert "aac" in cmd

    # --- 带音频的完整合成命令 ---

    def test_compose_with_audio_single_scene(self):
        scenes = [
            CompositionScene(video_path="/v1.mp4", audio_path="/a1.wav", duration=5.0),
        ]
        cmd = self.builder.build_compose_with_audio_command(scenes, "/out.mp4", self.config)
        assert cmd[0] == "ffmpeg"
        assert "/v1.mp4" in cmd
        assert "/a1.wav" in cmd
        assert "-filter_complex" in cmd
        assert "/out.mp4" in cmd

    def test_compose_with_audio_multiple_scenes(self):
        scenes = [
            CompositionScene(video_path="/v1.mp4", audio_path="/a1.wav", duration=3.0),
            CompositionScene(video_path="/v2.mp4", audio_path="/a2.wav", duration=4.0),
        ]
        cmd = self.builder.build_compose_with_audio_command(scenes, "/out.mp4", self.config)
        filter_idx = cmd.index("-filter_complex")
        filter_str = cmd[filter_idx + 1]
        assert "concat=n=2:v=1:a=0" in filter_str
        assert "concat=n=2:v=0:a=1" in filter_str

    def test_compose_mixed_audio_scenes(self):
        """测试部分场景有音频、部分没有"""
        scenes = [
            CompositionScene(video_path="/v1.mp4", audio_path="/a1.wav", duration=3.0),
            CompositionScene(video_path="/v2.mp4", audio_path=None, duration=4.0),
        ]
        cmd = self.builder.build_compose_with_audio_command(scenes, "/out.mp4", self.config)
        filter_idx = cmd.index("-filter_complex")
        filter_str = cmd[filter_idx + 1]
        # 应该有静音源用于无音频的场景
        assert "anullsrc" in filter_str

    def test_compose_no_audio_scenes(self):
        """所有场景都没有音频"""
        scenes = [
            CompositionScene(video_path="/v1.mp4", audio_path=None, duration=3.0),
            CompositionScene(video_path="/v2.mp4", audio_path=None, duration=4.0),
        ]
        cmd = self.builder.build_compose_with_audio_command(scenes, "/out.mp4", self.config)
        # 不应该有 [outa] 映射
        assert "[outa]" not in cmd

    # --- 字幕嵌入命令 ---

    def test_subtitle_embed_command(self):
        cmd = self.builder.build_subtitle_embed_command("/v.mp4", "/s.srt", "/out.mp4")
        assert cmd[0] == "ffmpeg"
        assert "/v.mp4" in cmd
        assert "subtitles=" in " ".join(cmd)
        assert "/out.mp4" in cmd

    # --- 转场命令 ---

    def test_transition_single_clip(self):
        cmd = self.builder.build_transition_command(["/c1.mp4"], "/out.mp4")
        assert cmd[0] == "ffmpeg"
        # 单个片段不需要 xfade
        assert "xfade" not in " ".join(cmd)

    def test_transition_two_clips(self):
        cmd = self.builder.build_transition_command(
            ["/c1.mp4", "/c2.mp4"], "/out.mp4", "fade", 0.5
        )
        cmd_str = " ".join(cmd)
        assert "xfade" in cmd_str
        assert "transition=fade" in cmd_str
        assert "duration=0.5" in cmd_str

    def test_transition_three_clips(self):
        cmd = self.builder.build_transition_command(
            ["/c1.mp4", "/c2.mp4", "/c3.mp4"], "/out.mp4", "wipeleft", 1.0
        )
        cmd_str = " ".join(cmd)
        assert "xfade" in cmd_str
        assert "transition=wipeleft" in cmd_str
        # Should have two xfade operations for 3 clips
        assert cmd_str.count("xfade") == 2

    def test_transition_custom_config(self):
        config = OutputConfig(resolution=(3840, 2160), fps=60, bitrate="16M")
        cmd = self.builder.build_transition_command(
            ["/c1.mp4", "/c2.mp4"], "/out.mp4", "fade", 0.5, config
        )
        cmd_str = " ".join(cmd)
        assert "3840" in cmd_str
        assert "2160" in cmd_str

    # --- 输出配置 ---

    def test_output_config_1080p(self):
        """验证默认配置为 1080p"""
        config = OutputConfig()
        assert config.resolution == (1920, 1080)
        assert config.fps == 30
        assert config.codec == "h264"
        assert config.format == "mp4"
        assert config.bitrate == "8M"

    def test_concat_command_includes_resolution(self):
        cmd = self.builder.build_concat_command(["/c.mp4"], "/out.mp4", self.config)
        cmd_str = " ".join(cmd)
        assert "1920" in cmd_str
        assert "1080" in cmd_str

    def test_concat_command_includes_pixel_format(self):
        cmd = self.builder.build_concat_command(["/c.mp4"], "/out.mp4", self.config)
        assert "yuv420p" in cmd


# ============================================================
# FFmpegCompositor 集成测试（mock subprocess）
# ============================================================

class TestFFmpegCompositor:
    """测试 FFmpegCompositor 主类（mock FFmpeg 调用）"""

    def setup_method(self):
        self.compositor = FFmpegCompositor(projects_dir=Path("/tmp/test_projects"))

    @pytest.mark.asyncio
    async def test_compose_empty_scenes_raises(self):
        with pytest.raises(ValueError, match="不能为空"):
            await self.compositor.compose_final_video("proj1", [], OutputConfig())

    @pytest.mark.asyncio
    async def test_compose_video_only(self, tmp_path):
        """测试仅视频拼接（无音频、无字幕）"""
        compositor = FFmpegCompositor(projects_dir=tmp_path)
        scenes = [
            CompositionScene(video_path="/v1.mp4", duration=5.0),
            CompositionScene(video_path="/v2.mp4", duration=3.0),
        ]

        with patch.object(compositor, "_run_ffmpeg", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "", "")
            result = await compositor.compose_final_video("proj1", scenes)

        assert result.endswith("final.mp4")
        mock_run.assert_called_once()
        # 验证命令包含正确的输入文件
        cmd = mock_run.call_args[0][0]
        assert "/v1.mp4" in cmd
        assert "/v2.mp4" in cmd

    @pytest.mark.asyncio
    async def test_compose_with_audio(self, tmp_path):
        """测试带音频同步的合成"""
        compositor = FFmpegCompositor(projects_dir=tmp_path)
        scenes = [
            CompositionScene(video_path="/v1.mp4", audio_path="/a1.wav", duration=5.0),
            CompositionScene(video_path="/v2.mp4", audio_path="/a2.wav", duration=3.0),
        ]

        with patch.object(compositor, "_run_ffmpeg", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "", "")
            result = await compositor.compose_final_video("proj1", scenes)

        assert result.endswith("final.mp4")
        cmd = mock_run.call_args[0][0]
        assert "/a1.wav" in cmd
        assert "/a2.wav" in cmd

    @pytest.mark.asyncio
    async def test_compose_with_subtitles(self, tmp_path):
        """测试带字幕的合成"""
        compositor = FFmpegCompositor(projects_dir=tmp_path)
        scenes = [
            CompositionScene(
                video_path="/v1.mp4", subtitle_text="你好", start_time=0, duration=3
            ),
            CompositionScene(
                video_path="/v2.mp4", subtitle_text="世界", start_time=3, duration=4
            ),
        ]

        with patch.object(compositor, "_run_ffmpeg", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "", "")
            result = await compositor.compose_final_video("proj1", scenes)

        assert result.endswith("final.mp4")
        # 应该调用两次：一次拼接，一次嵌入字幕
        assert mock_run.call_count == 2

        # 验证 SRT 文件已生成
        srt_path = tmp_path / "proj1" / "output" / "subtitles.srt"
        assert srt_path.exists()
        srt_content = srt_path.read_text(encoding="utf-8")
        assert "你好" in srt_content
        assert "世界" in srt_content

    @pytest.mark.asyncio
    async def test_compose_with_audio_and_subtitles(self, tmp_path):
        """测试完整合成（视频 + 音频 + 字幕）"""
        compositor = FFmpegCompositor(projects_dir=tmp_path)
        scenes = [
            CompositionScene(
                video_path="/v1.mp4", audio_path="/a1.wav",
                subtitle_text="台词一", start_time=0, duration=5
            ),
        ]

        with patch.object(compositor, "_run_ffmpeg", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "", "")
            result = await compositor.compose_final_video("proj1", scenes)

        assert result.endswith("final.mp4")
        assert mock_run.call_count == 2  # compose + subtitle embed

    @pytest.mark.asyncio
    async def test_add_subtitles(self, tmp_path):
        """测试单独添加字幕"""
        compositor = FFmpegCompositor(projects_dir=tmp_path)
        subtitles = [
            SubtitleEntry(index=1, start_time=0, end_time=5, text="字幕"),
        ]

        video_path = str(tmp_path / "video.mp4")
        with patch.object(compositor, "_run_ffmpeg", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "", "")
            result = await compositor.add_subtitles(video_path, subtitles)

        assert "subtitled" in result
        mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_subtitles_empty_list(self, tmp_path):
        """空字幕列表直接返回原视频"""
        compositor = FFmpegCompositor(projects_dir=tmp_path)
        result = await compositor.add_subtitles("/video.mp4", [])
        assert result == "/video.mp4"

    @pytest.mark.asyncio
    async def test_add_transitions(self, tmp_path):
        """测试添加转场效果"""
        compositor = FFmpegCompositor(projects_dir=tmp_path)
        clips = [str(tmp_path / "c1.mp4"), str(tmp_path / "c2.mp4")]

        with patch.object(compositor, "_run_ffmpeg", new_callable=AsyncMock) as mock_run, \
             patch.object(compositor, "_get_clip_duration", new_callable=AsyncMock) as mock_dur:
            mock_run.return_value = (0, "", "")
            mock_dur.return_value = 5.0
            result = await compositor.add_transitions(clips, "fade", 0.5)

        assert result.endswith(".mp4")
        mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_transitions_single_clip(self, tmp_path):
        """单个片段直接返回"""
        compositor = FFmpegCompositor(projects_dir=tmp_path)
        result = await compositor.add_transitions(["/c1.mp4"])
        assert result == "/c1.mp4"

    @pytest.mark.asyncio
    async def test_add_transitions_empty_raises(self, tmp_path):
        compositor = FFmpegCompositor(projects_dir=tmp_path)
        with pytest.raises(ValueError, match="不能为空"):
            await compositor.add_transitions([])

    @pytest.mark.asyncio
    async def test_ffmpeg_not_found(self, tmp_path):
        """测试 FFmpeg 未安装的错误处理"""
        compositor = FFmpegCompositor(
            projects_dir=tmp_path, ffmpeg_path="/nonexistent/ffmpeg"
        )
        scenes = [CompositionScene(video_path="/v1.mp4", duration=5.0)]

        with pytest.raises(FFmpegNotFoundError):
            await compositor.compose_final_video("proj1", scenes)

    @pytest.mark.asyncio
    async def test_ffmpeg_command_failure(self, tmp_path):
        """测试 FFmpeg 命令执行失败"""
        compositor = FFmpegCompositor(projects_dir=tmp_path)
        scenes = [CompositionScene(video_path="/v1.mp4", duration=5.0)]

        with patch.object(compositor, "_run_ffmpeg", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = FFmpegCompositionError("合成失败")
            with pytest.raises(FFmpegCompositionError):
                await compositor.compose_final_video("proj1", scenes)

    @pytest.mark.asyncio
    async def test_compose_creates_output_directory(self, tmp_path):
        """测试合成时自动创建输出目录"""
        compositor = FFmpegCompositor(projects_dir=tmp_path)
        scenes = [CompositionScene(video_path="/v1.mp4", duration=5.0)]

        with patch.object(compositor, "_run_ffmpeg", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "", "")
            await compositor.compose_final_video("new_project", scenes)

        assert (tmp_path / "new_project" / "output").exists()


# ============================================================
# 数据类测试
# ============================================================

class TestDataClasses:
    """测试数据类默认值和构造"""

    def test_composition_scene_defaults(self):
        scene = CompositionScene(video_path="/v.mp4")
        assert scene.video_path == "/v.mp4"
        assert scene.audio_path is None
        assert scene.subtitle_text is None
        assert scene.start_time == 0.0
        assert scene.duration == 5.0

    def test_composition_scene_full(self):
        scene = CompositionScene(
            video_path="/v.mp4",
            audio_path="/a.wav",
            subtitle_text="hello",
            start_time=10.0,
            duration=3.0,
        )
        assert scene.audio_path == "/a.wav"
        assert scene.subtitle_text == "hello"
        assert scene.start_time == 10.0
        assert scene.duration == 3.0

    def test_output_config_defaults(self):
        config = OutputConfig()
        assert config.resolution == (1920, 1080)
        assert config.fps == 30
        assert config.codec == "h264"
        assert config.format == "mp4"
        assert config.bitrate == "8M"

    def test_output_config_custom(self):
        config = OutputConfig(resolution=(3840, 2160), fps=60, bitrate="16M")
        assert config.resolution == (3840, 2160)
        assert config.fps == 60

    def test_subtitle_entry(self):
        entry = SubtitleEntry(index=1, start_time=0.0, end_time=5.0, text="test")
        assert entry.index == 1
        assert entry.text == "test"


# ============================================================
# 异常类测试
# ============================================================

class TestExceptions:
    """测试异常类"""

    def test_ffmpeg_error(self):
        err = FFmpegCompositionError("失败", "详情")
        assert str(err) == "失败"
        assert err.code == "FFMPEG_COMPOSITION_ERROR"
        assert err.detail == "详情"
        assert err.retryable is True

    def test_ffmpeg_not_found(self):
        err = FFmpegNotFoundError()
        assert err.code == "FFMPEG_NOT_FOUND"
        assert err.retryable is False
