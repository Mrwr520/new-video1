"""Property 10 & 11: 视频合成排序与音视频同步正确性 / 字幕生成完整性

Feature: ai-video-generator, Property 10: 视频合成排序与音视频同步正确性
For any 分镜场景集合，合成器生成的 CompositionScene 列表应当按 scene_order 排序，
且每个 CompositionScene 的 audio_path 对应正确的场景音频文件。

Feature: ai-video-generator, Property 11: 字幕生成完整性
For any 包含台词/旁白的分镜列表，生成的字幕文件应当包含每个场景的所有台词文本，
且字幕时间戳与对应场景的时间范围一致。

**Validates: Requirements 7.1, 7.2, 7.3**
"""

from hypothesis import given, settings, assume, strategies as st

from app.services.ffmpeg_service import (
    CompositionScene,
    FFmpegCommandBuilder,
    OutputConfig,
    generate_subtitles_from_scenes,
    generate_srt_content,
    format_srt_timestamp,
)


# ============================================================
# Strategies
# ============================================================

# Positive duration in seconds (0.1 to 120s)
_duration = st.floats(min_value=0.1, max_value=120.0, allow_nan=False, allow_infinity=False)

# Non-negative start time
_start_time = st.floats(min_value=0.0, max_value=3600.0, allow_nan=False, allow_infinity=False)

# File path-like strings for video/audio
_video_path = st.integers(min_value=1, max_value=1000).map(lambda i: f"/videos/scene_{i}.mp4")
_audio_path = st.integers(min_value=1, max_value=1000).map(lambda i: f"/audio/scene_{i}.wav")

# Non-empty subtitle text
_subtitle_text = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=100,
).filter(lambda s: s.strip())


def _scene_with_order(order: int):
    """Build a strategy for a scene dict with a given scene_order, simulating DB scene data."""
    return st.fixed_dictionaries({
        "scene_order": st.just(order),
        "video_path": _video_path,
        "audio_path": st.one_of(st.none(), _audio_path),
        "subtitle_text": st.one_of(st.none(), _subtitle_text),
        "duration": _duration,
    })


def _ordered_scene_list():
    """Generate a list of scene dicts with unique sequential scene_order values."""
    return st.integers(min_value=1, max_value=20).flatmap(
        lambda n: st.tuples(
            *[_scene_with_order(i) for i in range(1, n + 1)]
        ).map(list)
    )


# Strategy for CompositionScene with subtitle text (for Property 11)
_composition_scene_with_subtitle = st.builds(
    CompositionScene,
    video_path=_video_path,
    audio_path=st.one_of(st.none(), _audio_path),
    subtitle_text=_subtitle_text,
    start_time=_start_time,
    duration=_duration,
)

# Strategy for CompositionScene that may or may not have subtitle
_composition_scene = st.builds(
    CompositionScene,
    video_path=_video_path,
    audio_path=st.one_of(st.none(), _audio_path),
    subtitle_text=st.one_of(st.none(), _subtitle_text),
    start_time=_start_time,
    duration=_duration,
)


# ============================================================
# Helper: simulate building CompositionScene list from DB scenes
# ============================================================

def build_composition_scenes(scene_dicts: list[dict]) -> list[CompositionScene]:
    """Simulate the pipeline logic that builds CompositionScene list from DB scene records.

    Sorts by scene_order and computes cumulative start_time.
    """
    sorted_scenes = sorted(scene_dicts, key=lambda s: s["scene_order"])
    result = []
    current_time = 0.0
    for s in sorted_scenes:
        result.append(CompositionScene(
            video_path=s["video_path"],
            audio_path=s["audio_path"],
            subtitle_text=s["subtitle_text"],
            start_time=current_time,
            duration=s["duration"],
        ))
        current_time += s["duration"]
    return result


# ============================================================
# Property 10: 视频合成排序与音视频同步正确性
# ============================================================

@settings(max_examples=100)
@given(scene_dicts=_ordered_scene_list())
def test_composition_scenes_ordered_by_scene_order(scene_dicts: list[dict]):
    """Property 10: CompositionScene 列表按 scene_order 排序。

    Feature: ai-video-generator, Property 10: 视频合成排序与音视频同步正确性
    **Validates: Requirements 7.1, 7.2**
    """
    # Shuffle to simulate unordered input
    import random
    shuffled = scene_dicts.copy()
    random.shuffle(shuffled)

    composition = build_composition_scenes(shuffled)

    # Verify ordering: start_time should be non-decreasing
    for i in range(1, len(composition)):
        assert composition[i].start_time >= composition[i - 1].start_time, (
            f"Scene at index {i} has start_time {composition[i].start_time} "
            f"< previous {composition[i - 1].start_time}"
        )

    # Verify the video paths match the sorted order
    sorted_dicts = sorted(scene_dicts, key=lambda s: s["scene_order"])
    for i, (comp, orig) in enumerate(zip(composition, sorted_dicts)):
        assert comp.video_path == orig["video_path"], (
            f"Scene {i}: expected video_path {orig['video_path']}, got {comp.video_path}"
        )


@settings(max_examples=100)
@given(scene_dicts=_ordered_scene_list())
def test_composition_audio_path_matches_scene(scene_dicts: list[dict]):
    """Property 10: 每个 CompositionScene 的 audio_path 对应正确的场景音频文件。

    Feature: ai-video-generator, Property 10: 视频合成排序与音视频同步正确性
    **Validates: Requirements 7.1, 7.2**
    """
    import random
    shuffled = scene_dicts.copy()
    random.shuffle(shuffled)

    composition = build_composition_scenes(shuffled)
    sorted_dicts = sorted(scene_dicts, key=lambda s: s["scene_order"])

    for i, (comp, orig) in enumerate(zip(composition, sorted_dicts)):
        assert comp.audio_path == orig["audio_path"], (
            f"Scene {i}: expected audio_path {orig['audio_path']}, got {comp.audio_path}"
        )


@settings(max_examples=100)
@given(scene_dicts=_ordered_scene_list())
def test_compose_command_preserves_scene_order(scene_dicts: list[dict]):
    """Property 10: FFmpeg 合成命令中视频输入顺序与 scene_order 一致。

    Feature: ai-video-generator, Property 10: 视频合成排序与音视频同步正确性
    **Validates: Requirements 7.1, 7.2**
    """
    import random
    shuffled = scene_dicts.copy()
    random.shuffle(shuffled)

    composition = build_composition_scenes(shuffled)
    config = OutputConfig()

    cmd = FFmpegCommandBuilder.build_compose_with_audio_command(
        composition, "/output/final.mp4", config
    )

    # Extract -i arguments in order
    input_files = []
    for idx, arg in enumerate(cmd):
        if arg == "-i" and idx + 1 < len(cmd):
            input_files.append(cmd[idx + 1])

    # The video paths should appear in scene_order
    sorted_dicts = sorted(scene_dicts, key=lambda s: s["scene_order"])
    expected_video_order = [s["video_path"] for s in sorted_dicts]

    # Filter input_files to only video paths (audio paths are interleaved)
    video_inputs = [f for f in input_files if f.endswith(".mp4")]
    assert video_inputs == expected_video_order, (
        f"Video input order {video_inputs} != expected {expected_video_order}"
    )


@settings(max_examples=100)
@given(scene_dicts=_ordered_scene_list())
def test_compose_command_audio_inputs_match_scenes(scene_dicts: list[dict]):
    """Property 10: FFmpeg 合成命令中音频输入与对应场景匹配。

    Feature: ai-video-generator, Property 10: 视频合成排序与音视频同步正确性
    **Validates: Requirements 7.1, 7.2**
    """
    import random
    shuffled = scene_dicts.copy()
    random.shuffle(shuffled)

    composition = build_composition_scenes(shuffled)
    config = OutputConfig()

    cmd = FFmpegCommandBuilder.build_compose_with_audio_command(
        composition, "/output/final.mp4", config
    )

    # Extract -i arguments in order
    input_files = []
    for idx, arg in enumerate(cmd):
        if arg == "-i" and idx + 1 < len(cmd):
            input_files.append(cmd[idx + 1])

    # For each scene with audio, the audio file should appear right after its video
    sorted_dicts = sorted(scene_dicts, key=lambda s: s["scene_order"])
    expected_inputs = []
    for s in sorted_dicts:
        expected_inputs.append(s["video_path"])
        if s["audio_path"] is not None:
            expected_inputs.append(s["audio_path"])

    assert input_files == expected_inputs, (
        f"Input file order {input_files} != expected {expected_inputs}"
    )


# ============================================================
# Property 11: 字幕生成完整性
# ============================================================

@settings(max_examples=100)
@given(
    scenes=st.lists(
        _composition_scene_with_subtitle,
        min_size=1,
        max_size=20,
    )
)
def test_subtitles_contain_all_dialogue_text(scenes: list[CompositionScene]):
    """Property 11: 生成的字幕包含每个场景的所有台词文本。

    Feature: ai-video-generator, Property 11: 字幕生成完整性
    **Validates: Requirements 7.3**
    """
    entries = generate_subtitles_from_scenes(scenes)

    # Every scene with non-empty subtitle_text should have a corresponding entry
    expected_texts = [
        s.subtitle_text.strip()
        for s in scenes
        if s.subtitle_text and s.subtitle_text.strip()
    ]

    actual_texts = [e.text for e in entries]
    assert actual_texts == expected_texts, (
        f"Expected subtitle texts {expected_texts}, got {actual_texts}"
    )


@settings(max_examples=100)
@given(
    scenes=st.lists(
        _composition_scene,
        min_size=1,
        max_size=20,
    )
)
def test_subtitle_timestamps_match_scene_time_range(scenes: list[CompositionScene]):
    """Property 11: 字幕时间戳与对应场景的时间范围一致。

    Feature: ai-video-generator, Property 11: 字幕生成完整性
    **Validates: Requirements 7.3**
    """
    entries = generate_subtitles_from_scenes(scenes)

    # Build a mapping from subtitle text to the scene it came from
    scenes_with_subs = [
        s for s in scenes
        if s.subtitle_text and s.subtitle_text.strip()
    ]

    assert len(entries) == len(scenes_with_subs)

    for entry, scene in zip(entries, scenes_with_subs):
        # start_time should match scene's start_time
        assert abs(entry.start_time - scene.start_time) < 1e-9, (
            f"Subtitle start_time {entry.start_time} != scene start_time {scene.start_time}"
        )
        # end_time should match scene's start_time + duration
        expected_end = scene.start_time + scene.duration
        assert abs(entry.end_time - expected_end) < 1e-9, (
            f"Subtitle end_time {entry.end_time} != expected {expected_end}"
        )


@settings(max_examples=100)
@given(
    scenes=st.lists(
        _composition_scene,
        min_size=1,
        max_size=20,
    )
)
def test_subtitle_indices_sequential(scenes: list[CompositionScene]):
    """Property 11: 字幕索引从 1 开始连续递增。

    Feature: ai-video-generator, Property 11: 字幕生成完整性
    **Validates: Requirements 7.3**
    """
    entries = generate_subtitles_from_scenes(scenes)

    for i, entry in enumerate(entries):
        assert entry.index == i + 1, (
            f"Expected subtitle index {i + 1}, got {entry.index}"
        )


@settings(max_examples=100)
@given(
    scenes=st.lists(
        _composition_scene_with_subtitle,
        min_size=1,
        max_size=10,
    )
)
def test_srt_content_contains_all_subtitles(scenes: list[CompositionScene]):
    """Property 11: SRT 内容包含所有字幕文本且格式正确。

    Feature: ai-video-generator, Property 11: 字幕生成完整性
    **Validates: Requirements 7.3**
    """
    entries = generate_subtitles_from_scenes(scenes)
    assume(len(entries) > 0)

    srt_content = generate_srt_content(entries)

    # Every subtitle text should appear in the SRT content
    for entry in entries:
        assert entry.text in srt_content, (
            f"Subtitle text '{entry.text}' not found in SRT content"
        )

    # Every entry's timestamp should appear in the SRT content
    for entry in entries:
        start_ts = format_srt_timestamp(entry.start_time)
        end_ts = format_srt_timestamp(entry.end_time)
        expected_ts_line = f"{start_ts} --> {end_ts}"
        assert expected_ts_line in srt_content, (
            f"Timestamp line '{expected_ts_line}' not found in SRT content"
        )
