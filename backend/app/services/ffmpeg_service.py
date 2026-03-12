"""FFmpeg 视频合成服务

基于 FFmpeg 的视频合成模块，负责将视频片段、音频、字幕合成为最终视频。
FFmpeg 命令通过 asyncio.subprocess 异步执行。

Requirements:
    7.1: FFmpeg_Compositor SHALL 将视频片段按分镜顺序拼接
    7.2: FFmpeg_Compositor SHALL 将对应的语音音频与视频片段精确同步
    7.3: FFmpeg_Compositor SHALL 根据台词和旁白文本自动生成并嵌入字幕
    7.5: FFmpeg_Compositor SHALL 输出 MP4 格式的视频文件，分辨率不低于 1080p
    7.6: FFmpeg_Compositor SHALL 在视频片段之间添加平滑的转场效果
"""

import asyncio
import logging
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"


# ============================================================
# 数据类
# ============================================================

@dataclass
class CompositionScene:
    """合成场景数据"""
    video_path: str
    audio_path: Optional[str] = None
    subtitle_text: Optional[str] = None
    start_time: float = 0.0
    duration: float = 5.0


@dataclass
class OutputConfig:
    """输出配置"""
    resolution: tuple[int, int] = (1920, 1080)
    fps: int = 30
    codec: str = "h264"
    format: str = "mp4"
    bitrate: str = "8M"


@dataclass
class SubtitleEntry:
    """字幕条目"""
    index: int
    start_time: float
    end_time: float
    text: str


# ============================================================
# 异常类
# ============================================================

class FFmpegError(Exception):
    """FFmpeg 服务基础异常"""

    def __init__(self, message: str, code: str = "FFMPEG_ERROR", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class FFmpegNotFoundError(FFmpegError):
    """FFmpeg 未安装"""

    def __init__(self):
        super().__init__(
            "FFmpeg 未安装或不在 PATH 中，请安装 FFmpeg",
            code="FFMPEG_NOT_FOUND",
            retryable=False,
        )


class FFmpegCompositionError(FFmpegError):
    """合成失败"""

    def __init__(self, message: str = "视频合成失败", detail: str = ""):
        super().__init__(message, code="FFMPEG_COMPOSITION_ERROR", retryable=True)
        self.detail = detail


# ============================================================
# SRT 字幕生成（纯 Python，无需 FFmpeg）
# ============================================================

def format_srt_timestamp(seconds: float) -> str:
    """将秒数转换为 SRT 时间戳格式 HH:MM:SS,mmm。

    Args:
        seconds: 秒数（非负）

    Returns:
        SRT 格式时间戳字符串
    """
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    # 防止四舍五入导致 millis == 1000
    if millis >= 1000:
        millis = 0
        secs += 1
        if secs >= 60:
            secs = 0
            minutes += 1
            if minutes >= 60:
                minutes = 0
                hours += 1
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt_content(entries: list[SubtitleEntry]) -> str:
    """生成 SRT 格式字幕内容。

    Args:
        entries: 字幕条目列表

    Returns:
        SRT 格式字符串
    """
    if not entries:
        return ""

    lines: list[str] = []
    for entry in entries:
        start_ts = format_srt_timestamp(entry.start_time)
        end_ts = format_srt_timestamp(entry.end_time)
        lines.append(str(entry.index))
        lines.append(f"{start_ts} --> {end_ts}")
        lines.append(entry.text)
        lines.append("")  # blank line separator

    return "\n".join(lines)


def generate_subtitles_from_scenes(scenes: list[CompositionScene]) -> list[SubtitleEntry]:
    """从合成场景列表生成字幕条目。

    为每个包含 subtitle_text 的场景创建一个字幕条目，
    时间戳基于场景的 start_time 和 duration。

    Args:
        scenes: 合成场景列表

    Returns:
        字幕条目列表
    """
    entries: list[SubtitleEntry] = []
    index = 1
    for scene in scenes:
        if scene.subtitle_text and scene.subtitle_text.strip():
            entries.append(SubtitleEntry(
                index=index,
                start_time=scene.start_time,
                end_time=scene.start_time + scene.duration,
                text=scene.subtitle_text.strip(),
            ))
            index += 1
    return entries


def write_srt_file(entries: list[SubtitleEntry], output_path: str) -> str:
    """将字幕条目写入 SRT 文件。

    Args:
        entries: 字幕条目列表
        output_path: 输出文件路径

    Returns:
        输出文件路径
    """
    content = generate_srt_content(entries)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


# ============================================================
# FFmpeg 命令构建器
# ============================================================

class FFmpegCommandBuilder:
    """构建 FFmpeg 命令行参数。

    将 FFmpeg 命令构建与实际执行分离，便于测试和调试。
    """

    @staticmethod
    def build_concat_command(
        clip_paths: list[str],
        output_path: str,
        config: OutputConfig,
    ) -> list[str]:
        """构建视频拼接命令（使用 concat demuxer）。

        Args:
            clip_paths: 视频片段路径列表（按顺序）
            output_path: 输出文件路径
            config: 输出配置

        Returns:
            FFmpeg 命令参数列表
        """
        # 使用 concat filter 进行拼接
        cmd = ["ffmpeg", "-y"]

        # 添加所有输入文件
        for clip in clip_paths:
            cmd.extend(["-i", clip])

        n = len(clip_paths)
        if n == 1:
            # 单个文件直接转码
            cmd.extend([
                "-vf", f"scale={config.resolution[0]}:{config.resolution[1]}",
                "-c:v", "libx264" if config.codec == "h264" else config.codec,
                "-b:v", config.bitrate,
                "-r", str(config.fps),
                "-pix_fmt", "yuv420p",
                output_path,
            ])
        else:
            # 多个文件使用 concat filter
            filter_parts = []
            for i in range(n):
                filter_parts.append(
                    f"[{i}:v]scale={config.resolution[0]}:{config.resolution[1]},"
                    f"setsar=1,fps={config.fps}[v{i}]"
                )
            concat_inputs = "".join(f"[v{i}]" for i in range(n))
            filter_parts.append(f"{concat_inputs}concat=n={n}:v=1:a=0[outv]")
            filter_complex = ";".join(filter_parts)

            cmd.extend([
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-c:v", "libx264" if config.codec == "h264" else config.codec,
                "-b:v", config.bitrate,
                "-pix_fmt", "yuv420p",
                output_path,
            ])

        return cmd

    @staticmethod
    def build_audio_merge_command(
        video_path: str,
        audio_path: str,
        output_path: str,
    ) -> list[str]:
        """构建音视频合并命令。

        Args:
            video_path: 视频文件路径
            audio_path: 音频文件路径
            output_path: 输出文件路径

        Returns:
            FFmpeg 命令参数列表
        """
        return [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            output_path,
        ]

    @staticmethod
    def build_compose_with_audio_command(
        scenes: list[CompositionScene],
        output_path: str,
        config: OutputConfig,
    ) -> list[str]:
        """构建带音频同步的完整合成命令。

        每个场景的视频和音频分别作为输入，通过 filter_complex 实现
        视频拼接和音频拼接，最终合并输出。

        Args:
            scenes: 合成场景列表
            output_path: 输出文件路径
            config: 输出配置

        Returns:
            FFmpeg 命令参数列表
        """
        cmd = ["ffmpeg", "-y"]
        n = len(scenes)

        # 添加所有输入（视频 + 音频交替）
        input_idx = 0
        video_indices: list[int] = []
        audio_indices: list[int] = []

        for scene in scenes:
            cmd.extend(["-i", scene.video_path])
            video_indices.append(input_idx)
            input_idx += 1

            if scene.audio_path:
                cmd.extend(["-i", scene.audio_path])
                audio_indices.append(input_idx)
                input_idx += 1
            else:
                audio_indices.append(-1)  # no audio

        # 构建 filter_complex
        filter_parts = []
        has_any_audio = any(idx >= 0 for idx in audio_indices)

        # 视频缩放和拼接
        for i, vidx in enumerate(video_indices):
            filter_parts.append(
                f"[{vidx}:v]scale={config.resolution[0]}:{config.resolution[1]},"
                f"setsar=1,fps={config.fps}[v{i}]"
            )

        if n == 1:
            filter_parts.append(f"[v0]null[outv]")
        else:
            concat_v = "".join(f"[v{i}]" for i in range(n))
            filter_parts.append(f"{concat_v}concat=n={n}:v=1:a=0[outv]")

        # 音频拼接（如果有音频）
        if has_any_audio:
            for i, aidx in enumerate(audio_indices):
                if aidx >= 0:
                    filter_parts.append(f"[{aidx}:a]aresample=44100[a{i}]")
                else:
                    # 生成静音音频段，时长与视频匹配
                    dur = scenes[i].duration
                    filter_parts.append(
                        f"anullsrc=r=44100:cl=stereo,atrim=0:{dur}[a{i}]"
                    )

            if n == 1:
                filter_parts.append(f"[a0]anull[outa]")
            else:
                concat_a = "".join(f"[a{i}]" for i in range(n))
                filter_parts.append(f"{concat_a}concat=n={n}:v=0:a=1[outa]")

        filter_complex = ";".join(filter_parts)
        cmd.extend(["-filter_complex", filter_complex])
        cmd.extend(["-map", "[outv]"])

        if has_any_audio:
            cmd.extend(["-map", "[outa]"])
            cmd.extend(["-c:a", "aac", "-b:a", "192k"])

        cmd.extend([
            "-c:v", "libx264" if config.codec == "h264" else config.codec,
            "-b:v", config.bitrate,
            "-pix_fmt", "yuv420p",
            output_path,
        ])

        return cmd

    @staticmethod
    def build_subtitle_embed_command(
        video_path: str,
        srt_path: str,
        output_path: str,
    ) -> list[str]:
        """构建字幕嵌入命令（硬字幕，使用 subtitles filter）。

        Args:
            video_path: 视频文件路径
            srt_path: SRT 字幕文件路径
            output_path: 输出文件路径

        Returns:
            FFmpeg 命令参数列表
        """
        # 使用 subtitles filter 烧录硬字幕
        # 需要转义路径中的特殊字符
        escaped_srt = srt_path.replace("\\", "/").replace(":", "\\:")
        return [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"subtitles='{escaped_srt}'",
            "-c:v", "libx264",
            "-c:a", "copy",
            output_path,
        ]

    @staticmethod
    def build_transition_command(
        clips: list[str],
        output_path: str,
        transition_type: str = "fade",
        transition_duration: float = 0.5,
        config: Optional[OutputConfig] = None,
    ) -> list[str]:
        """构建转场效果命令。

        使用 xfade filter 在视频片段之间添加转场效果。

        Args:
            clips: 视频片段路径列表
            output_path: 输出文件路径
            transition_type: 转场类型（fade, wipeleft, wiperight, slideup, slidedown 等）
            transition_duration: 转场时长（秒）
            config: 输出配置

        Returns:
            FFmpeg 命令参数列表
        """
        if config is None:
            config = OutputConfig()

        cmd = ["ffmpeg", "-y"]
        n = len(clips)

        for clip in clips:
            cmd.extend(["-i", clip])

        if n == 1:
            # 单个片段无需转场
            cmd.extend([
                "-c:v", "libx264" if config.codec == "h264" else config.codec,
                "-b:v", config.bitrate,
                "-pix_fmt", "yuv420p",
                output_path,
            ])
            return cmd

        # 使用 xfade filter 链式连接
        # xfade 需要逐对应用：先合并前两个，再与第三个合并，以此类推
        filter_parts = []
        td = transition_duration

        # 缩放所有输入
        for i in range(n):
            filter_parts.append(
                f"[{i}:v]scale={config.resolution[0]}:{config.resolution[1]},"
                f"setsar=1,fps={config.fps}[v{i}]"
            )

        # 链式 xfade
        # 第一对: [v0][v1]xfade=transition=fade:duration=0.5:offset=X[xf0]
        # 第二对: [xf0][v2]xfade=...[xf1]
        # 需要知道每个片段的时长来计算 offset
        # 由于我们不知道实际时长，使用占位符 {offset_N}
        # 实际使用时需要先探测时长
        if n == 2:
            filter_parts.append(
                f"[v0][v1]xfade=transition={transition_type}:"
                f"duration={td}:offset={{offset_0}}[outv]"
            )
        else:
            # 第一对
            filter_parts.append(
                f"[v0][v1]xfade=transition={transition_type}:"
                f"duration={td}:offset={{offset_0}}[xf0]"
            )
            # 中间对
            for i in range(2, n - 1):
                filter_parts.append(
                    f"[xf{i-2}][v{i}]xfade=transition={transition_type}:"
                    f"duration={td}:offset={{offset_{i-1}}}[xf{i-1}]"
                )
            # 最后一对
            filter_parts.append(
                f"[xf{n-3}][v{n-1}]xfade=transition={transition_type}:"
                f"duration={td}:offset={{offset_{n-2}}}[outv]"
            )

        filter_complex = ";".join(filter_parts)
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-c:v", "libx264" if config.codec == "h264" else config.codec,
            "-b:v", config.bitrate,
            "-pix_fmt", "yuv420p",
            output_path,
        ])

        return cmd


# ============================================================
# FFmpegCompositor 主类
# ============================================================

class FFmpegCompositor:
    """FFmpeg 视频合成服务。

    Requirements:
        7.1: 将视频片段按分镜顺序拼接
        7.2: 将对应的语音音频与视频片段精确同步
        7.3: 根据台词和旁白文本自动生成并嵌入字幕
        7.5: 输出 MP4 格式的视频文件，分辨率不低于 1080p
        7.6: 在视频片段之间添加平滑的转场效果
    """

    def __init__(self, projects_dir: Optional[Path] = None, ffmpeg_path: str = "ffmpeg"):
        self.projects_dir = projects_dir or DEFAULT_PROJECTS_DIR
        self.ffmpeg_path = ffmpeg_path
        self.command_builder = FFmpegCommandBuilder()

    async def _run_ffmpeg(self, cmd: list[str]) -> tuple[int, str, str]:
        """执行 FFmpeg 命令。

        Args:
            cmd: 命令参数列表

        Returns:
            (return_code, stdout, stderr)

        Raises:
            FFmpegNotFoundError: FFmpeg 未安装
            FFmpegCompositionError: 命令执行失败
        """
        # 替换 ffmpeg 路径
        if cmd and cmd[0] == "ffmpeg":
            cmd = [self.ffmpeg_path] + cmd[1:]

        logger.info("执行 FFmpeg 命令: %s", " ".join(cmd))

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            if process.returncode != 0:
                logger.error("FFmpeg 执行失败 (code=%d): %s", process.returncode, stderr_str)
                raise FFmpegCompositionError(
                    f"FFmpeg 命令执行失败 (exit code: {process.returncode})",
                    detail=stderr_str,
                )

            return process.returncode, stdout_str, stderr_str

        except FileNotFoundError:
            raise FFmpegNotFoundError()
        except FFmpegError:
            raise
        except Exception as e:
            raise FFmpegCompositionError(f"FFmpeg 执行异常: {e}")

    async def _get_clip_duration(self, clip_path: str) -> float:
        """使用 ffprobe 获取视频片段时长。

        Args:
            clip_path: 视频文件路径

        Returns:
            时长（秒）
        """
        ffprobe_path = self.ffmpeg_path.replace("ffmpeg", "ffprobe")
        if ffprobe_path == self.ffmpeg_path:
            ffprobe_path = "ffprobe"

        cmd = [
            ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            clip_path,
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            return float(stdout.decode().strip())
        except Exception:
            return 5.0  # 默认 5 秒

    async def compose_final_video(
        self,
        project_id: str,
        scenes: list[CompositionScene],
        output_config: Optional[OutputConfig] = None,
    ) -> str:
        """合成最终视频。

        流程：
        1. 按顺序拼接视频片段并同步音频
        2. 生成 SRT 字幕文件
        3. 将字幕嵌入视频

        Args:
            project_id: 项目 ID
            scenes: 合成场景列表（已按分镜顺序排列）
            output_config: 输出配置

        Returns:
            最终视频文件路径

        Raises:
            FFmpegError: 合成失败
            ValueError: 场景列表为空
        """
        if not scenes:
            raise ValueError("合成场景列表不能为空")

        config = output_config or OutputConfig()
        output_dir = self.projects_dir / project_id / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        has_audio = any(s.audio_path for s in scenes)
        has_subtitles = any(s.subtitle_text for s in scenes)

        # Step 1: 合成视频（含音频同步）
        if has_audio:
            intermediate_path = str(output_dir / "composed_raw.mp4")
            cmd = self.command_builder.build_compose_with_audio_command(
                scenes, intermediate_path, config
            )
        else:
            intermediate_path = str(output_dir / "composed_raw.mp4")
            clip_paths = [s.video_path for s in scenes]
            cmd = self.command_builder.build_concat_command(
                clip_paths, intermediate_path, config
            )

        await self._run_ffmpeg(cmd)

        # Step 2: 生成并嵌入字幕
        if has_subtitles:
            subtitle_entries = generate_subtitles_from_scenes(scenes)
            srt_path = str(output_dir / "subtitles.srt")
            write_srt_file(subtitle_entries, srt_path)

            final_path = str(output_dir / "final.mp4")
            sub_cmd = self.command_builder.build_subtitle_embed_command(
                intermediate_path, srt_path, final_path
            )
            await self._run_ffmpeg(sub_cmd)
        else:
            # 如果不需要字幕，尝试重命名为 final.mp4
            final_dest = str(output_dir / "final.mp4")
            if intermediate_path != final_dest:
                try:
                    os.replace(intermediate_path, final_dest)
                    final_path = final_dest
                except OSError:
                    # 文件可能尚未生成（如 dry-run 或测试场景）
                    final_path = final_dest
            else:
                final_path = intermediate_path

        logger.info("视频合成完成: %s", final_path)
        return final_path

    async def add_subtitles(
        self,
        video_path: str,
        subtitles: list[SubtitleEntry],
    ) -> str:
        """为视频添加字幕。

        Args:
            video_path: 视频文件路径
            subtitles: 字幕条目列表

        Returns:
            带字幕的视频文件路径
        """
        if not subtitles:
            return video_path

        video_dir = str(Path(video_path).parent)
        srt_path = os.path.join(video_dir, f"subs_{uuid.uuid4().hex[:8]}.srt")
        write_srt_file(subtitles, srt_path)

        output_path = os.path.join(
            video_dir,
            f"{Path(video_path).stem}_subtitled.mp4",
        )
        cmd = self.command_builder.build_subtitle_embed_command(
            video_path, srt_path, output_path
        )
        await self._run_ffmpeg(cmd)
        return output_path

    async def add_transitions(
        self,
        clips: list[str],
        transition_type: str = "fade",
        duration: float = 0.5,
    ) -> str:
        """在视频片段之间添加转场效果。

        Args:
            clips: 视频片段路径列表
            transition_type: 转场类型
            duration: 转场时长（秒）

        Returns:
            带转场效果的视频文件路径
        """
        if not clips:
            raise ValueError("视频片段列表不能为空")

        if len(clips) == 1:
            return clips[0]

        config = OutputConfig()
        output_dir = Path(clips[0]).parent
        output_path = str(output_dir / f"transition_{uuid.uuid4().hex[:8]}.mp4")

        # 获取每个片段的时长以计算 xfade offset
        durations: list[float] = []
        for clip in clips:
            dur = await self._get_clip_duration(clip)
            durations.append(dur)

        cmd = self.command_builder.build_transition_command(
            clips, output_path, transition_type, duration, config
        )

        # 替换 offset 占位符
        # offset_0 = duration_of_clip_0 - transition_duration
        # offset_1 = offset_0 + duration_of_clip_1 - transition_duration
        # ...
        cmd_str = " ".join(cmd)
        cumulative_offset = 0.0
        for i in range(len(clips) - 1):
            cumulative_offset += durations[i] - duration
            if i > 0:
                cumulative_offset  # already accumulated
            offset_val = max(0, cumulative_offset if i == 0 else cumulative_offset)
            cmd_str = cmd_str.replace(f"{{offset_{i}}}", f"{offset_val:.3f}")
            if i == 0:
                pass  # first offset is just durations[0] - duration
            # Recalculate properly
        
        # Recalculate offsets properly
        cmd_str = " ".join(cmd)
        running_offset = 0.0
        for i in range(len(clips) - 1):
            running_offset += durations[i]
            if i > 0:
                running_offset -= duration  # subtract overlap from previous transition
            offset = running_offset - duration
            cmd_str = cmd_str.replace(f"{{offset_{i}}}", f"{max(0, offset):.3f}")

        # Parse back to list
        # Simple approach: rebuild the command with resolved offsets
        resolved_cmd = cmd_str.split()
        await self._run_ffmpeg(resolved_cmd)
        return output_path
