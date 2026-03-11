"""文本校验属性测试

Feature: ai-video-generator, Property 1: 文本校验正确性

使用 hypothesis 生成随机字符串，验证 validate_text 函数对各类输入的校验正确性。

**Validates: Requirements 1.3, 1.5**
"""

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from app.services.text_service import (
    MIN_TEXT_LENGTH,
    MAX_TEXT_LENGTH,
    ValidationStatus,
    validate_text,
)


# ============================================================
# 自定义策略：生成各类别的文本输入
# ============================================================

# 空字符串策略
empty_strings = st.just("")

# 纯空白字符串策略（空格、制表符、换行等组合）
whitespace_strings = st.text(
    alphabet=st.sampled_from([" ", "\t", "\n", "\r", "\u3000"]),
    min_size=1,
    max_size=50,
)

# 过短字符串策略：strip 后长度 < MIN_TEXT_LENGTH 且非空
short_strings = st.text(
    alphabet=st.characters(exclude_categories=("Cs",)),
    min_size=1,
    max_size=MIN_TEXT_LENGTH + 10,
).filter(lambda s: 0 < len(s.strip()) < MIN_TEXT_LENGTH)

# 超长字符串策略：strip 后长度 > MAX_TEXT_LENGTH
overlong_strings = st.integers(
    min_value=MAX_TEXT_LENGTH + 1,
    max_value=MAX_TEXT_LENGTH + 500,
).map(lambda n: "a" * n)

# 有效字符串策略：strip 后长度在 [MIN_TEXT_LENGTH, MAX_TEXT_LENGTH] 之间
valid_strings = st.integers(
    min_value=MIN_TEXT_LENGTH,
    max_value=min(MAX_TEXT_LENGTH, MIN_TEXT_LENGTH + 1000),
).map(lambda n: "有效文本" * (n // 4 + 1))
# 确保 strip 后长度在有效范围内
valid_strings = valid_strings.filter(
    lambda s: MIN_TEXT_LENGTH <= len(s.strip()) <= MAX_TEXT_LENGTH
)


# ============================================================
# Property 1: 文本校验正确性
# ============================================================

class TestTextValidationProperty:
    """Property 1: 文本校验正确性

    For any 输入字符串，文本校验函数应当：
    - 对空字符串和纯空白字符串返回无效
    - 对长度低于最小阈值的字符串返回无效
    - 对超过最大长度限制的字符串返回无效
    - 对满足长度要求的非空字符串返回有效

    **Validates: Requirements 1.3, 1.5**
    """

    @given(text=empty_strings)
    @settings(max_examples=100)
    def test_empty_string_is_invalid(self, text: str):
        """空字符串应返回 INVALID"""
        result = validate_text(text)
        assert result.status == ValidationStatus.INVALID
        assert result.char_count == 0

    @given(text=whitespace_strings)
    @settings(max_examples=100)
    def test_whitespace_only_is_invalid(self, text: str):
        """纯空白字符串应返回 INVALID"""
        result = validate_text(text)
        assert result.status == ValidationStatus.INVALID
        assert result.char_count == 0

    @given(text=short_strings)
    @settings(max_examples=100)
    def test_short_text_is_invalid(self, text: str):
        """长度低于最小阈值的字符串应返回 INVALID"""
        result = validate_text(text)
        assert result.status == ValidationStatus.INVALID
        assert 0 < result.char_count < MIN_TEXT_LENGTH

    @given(text=overlong_strings)
    @settings(max_examples=100)
    def test_overlong_text_is_invalid(self, text: str):
        """超过最大长度限制的字符串应返回 INVALID"""
        result = validate_text(text)
        assert result.status == ValidationStatus.INVALID
        assert result.char_count > MAX_TEXT_LENGTH

    @given(text=valid_strings)
    @settings(max_examples=100)
    def test_valid_text_is_valid(self, text: str):
        """满足长度要求的非空字符串应返回 VALID"""
        result = validate_text(text)
        assert result.status == ValidationStatus.VALID
        assert MIN_TEXT_LENGTH <= result.char_count <= MAX_TEXT_LENGTH

    @given(text=st.text(min_size=0, max_size=200))
    @settings(max_examples=200)
    def test_validation_is_total_function(self, text: str):
        """对任意字符串输入，校验函数都应返回有效的结果（不抛异常）"""
        result = validate_text(text)
        assert result.status in (ValidationStatus.VALID, ValidationStatus.INVALID)
        assert result.char_count >= 0
        assert isinstance(result.message, str)
        assert len(result.message) > 0
