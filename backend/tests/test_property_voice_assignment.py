"""Property 9: 角色语音分配唯一性

Feature: ai-video-generator, Property 9: 角色语音分配唯一性
For any 包含多个角色的项目，TTS 语音分配函数应当为每个不同的角色分配不同的 voice_id。

**Validates: Requirements 6.2**
"""

from hypothesis import given, settings, assume, strategies as st

from app.services.tts_service import VoiceInfo, assign_voices_to_characters


# ============================================================
# Strategies
# ============================================================

# Generate a unique character name: non-empty printable string
_char_name = st.text(
    alphabet=st.characters(categories=("L", "N")),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip())

# Generate a list of unique character names (at least 2 for "multiple characters")
unique_character_names = st.lists(
    _char_name,
    min_size=2,
    max_size=20,
    unique=True,
)

# Generate a VoiceInfo with a unique id
def _voice_info_strategy():
    """Strategy that produces a VoiceInfo with a random unique id."""
    return st.builds(
        VoiceInfo,
        id=st.text(
            alphabet=st.characters(categories=("L", "N", "Pd")),
            min_size=3,
            max_size=30,
        ).filter(lambda s: s.strip()),
        name=st.just("voice"),
        language=st.sampled_from(["zh-CN", "en-US", "ja-JP"]),
        gender=st.sampled_from(["Male", "Female"]),
        preview_url=st.none(),
    )

# Generate a list of VoiceInfo objects with unique ids
unique_voices = st.lists(
    _voice_info_strategy(),
    min_size=2,
    max_size=30,
    unique_by=lambda v: v.id,
)


# ============================================================
# Property Test
# ============================================================

@settings(max_examples=100)
@given(
    characters=unique_character_names,
    voices=unique_voices,
)
def test_voice_assignment_uniqueness(characters: list[str], voices: list[VoiceInfo]):
    """Property 9: 当角色数 <= 可用语音数时，每个角色分配的 voice_id 必须唯一。

    Feature: ai-video-generator, Property 9: 角色语音分配唯一性
    **Validates: Requirements 6.2**
    """
    # Only test the uniqueness guarantee when we have enough voices
    assume(len(characters) <= len(voices))

    result = assign_voices_to_characters(characters, voices)

    # All characters should be present in the result
    assert set(result.keys()) == set(characters)

    # All assigned voice_ids must be unique
    assigned_voice_ids = list(result.values())
    assert len(assigned_voice_ids) == len(set(assigned_voice_ids)), (
        f"Expected unique voice_ids for {len(characters)} characters, "
        f"but got duplicates: {assigned_voice_ids}"
    )

    # Each assigned voice_id must come from the available voices
    available_ids = {v.id for v in voices}
    for vid in assigned_voice_ids:
        assert vid in available_ids, (
            f"Assigned voice_id '{vid}' not in available voices"
        )
