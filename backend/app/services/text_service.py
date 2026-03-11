"""文本校验和文件解析服务

提供纯函数用于文本校验（非空、最小长度、最大长度）和文件内容解析（TXT、Markdown）。
"""

from dataclasses import dataclass
from enum import Enum

# 校验阈值常量
MIN_TEXT_LENGTH = 10
MAX_TEXT_LENGTH = 100_000


class ValidationStatus(str, Enum):
    """校验结果状态"""
    VALID = "valid"
    INVALID = "invalid"


@dataclass
class TextValidationResult:
    """文本校验结果"""
    status: ValidationStatus
    message: str
    char_count: int = 0


def validate_text(text: str) -> TextValidationResult:
    """校验文本内容，纯函数，可独立测试。

    规则：
    - 空字符串或纯空白字符串 → 无效
    - 去除首尾空白后长度 < MIN_TEXT_LENGTH → 无效
    - 去除首尾空白后长度 > MAX_TEXT_LENGTH → 无效
    - 其余情况 → 有效
    """
    stripped = text.strip()
    char_count = len(stripped)

    if char_count == 0:
        return TextValidationResult(
            status=ValidationStatus.INVALID,
            message="文本内容不能为空",
            char_count=0,
        )

    if char_count < MIN_TEXT_LENGTH:
        return TextValidationResult(
            status=ValidationStatus.INVALID,
            message=f"文本长度不足，最少需要 {MIN_TEXT_LENGTH} 个字符，当前 {char_count} 个字符",
            char_count=char_count,
        )

    if char_count > MAX_TEXT_LENGTH:
        return TextValidationResult(
            status=ValidationStatus.INVALID,
            message=f"文本超过处理上限，最多 {MAX_TEXT_LENGTH} 个字符，当前 {char_count} 个字符",
            char_count=char_count,
        )

    return TextValidationResult(
        status=ValidationStatus.VALID,
        message="校验通过",
        char_count=char_count,
    )


def parse_file_content(content: str, filename: str) -> str:
    """解析上传文件的文本内容。

    对 TXT 文件直接返回内容，对 Markdown 文件去除常见标记后返回纯文本。
    """
    lower_name = filename.lower()
    if lower_name.endswith(".md") or lower_name.endswith(".markdown"):
        return _parse_markdown(content)
    # 默认当作纯文本处理（包括 .txt）
    return content


def _parse_markdown(content: str) -> str:
    """简单的 Markdown → 纯文本转换，保留文本内容，去除标记符号。"""
    import re

    text = content
    # 去除标题标记 (# ## ### 等)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # 去除粗体/斜体标记
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}(.+?)_{1,3}", r"\1", text)
    # 去除行内代码
    text = re.sub(r"`(.+?)`", r"\1", text)
    # 去除链接，保留文本
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    # 去除图片标记
    text = re.sub(r"!\[.*?\]\(.+?\)", "", text)
    # 去除水平线
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    # 去除无序列表标记
    text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
    # 去除有序列表标记
    text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)
    # 去除引用标记
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)

    return text
