"""
属性测试：文本存储往返一致性 & 文件导入往返一致性

Feature: ai-video-generator, Property 2: 文本存储往返一致性
Feature: ai-video-generator, Property 3: 文件导入往返一致性

**Validates: Requirements 1.1, 1.2**

Property 2: 对任意有效文本内容，提交存储后再读取应当得到与原始输入完全相同的文本。
Property 3: 对任意有效的 TXT 或 Markdown 文件内容，导入后读取应当得到与原始文件内容等价的文本。
"""

import asyncio
import tempfile
from pathlib import Path

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from httpx import ASGITransport, AsyncClient

from app.database import init_db, set_db_path
from app.main import app
from app.services.text_service import (
    MIN_TEXT_LENGTH,
    MAX_TEXT_LENGTH,
    parse_file_content,
)


# --- 策略定义 ---

# 有效纯文本策略：strip 后长度在 [MIN_TEXT_LENGTH, MAX_TEXT_LENGTH] 之间
# 使用多种 Unicode 字符类别确保覆盖中英文、数字、标点等
_valid_text_alphabet = st.characters(
    categories=("L", "N", "P", "S", "Z"),
    exclude_characters="\x00",  # 排除 NULL 字符，SQLite 不友好
)

valid_text_st = st.text(
    alphabet=_valid_text_alphabet,
    min_size=MIN_TEXT_LENGTH,
    max_size=min(MAX_TEXT_LENGTH, MIN_TEXT_LENGTH + 2000),
).filter(lambda s: MIN_TEXT_LENGTH <= len(s.strip()) <= MAX_TEXT_LENGTH)

# TXT 文件内容策略：与纯文本相同，但会通过 filename=xxx.txt 提交
txt_content_st = valid_text_st

# Markdown 文件内容策略：包含常见 Markdown 标记的文本
# 生成带有标题、粗体、列表等标记的内容
_md_heading = st.sampled_from(["# ", "## ", "### "])
_md_emphasis = st.sampled_from(["**", "*", "__", "_"])
_md_list_marker = st.sampled_from(["- ", "* ", "1. "])

# 生成一段 Markdown 文本行
_md_plain_line = st.text(
    alphabet=st.characters(categories=("L", "N", "Z"), exclude_characters="\x00#*_`[]!()\n\r"),
    min_size=3,
    max_size=80,
).filter(lambda s: len(s.strip()) > 0)


@st.composite
def markdown_content_st(draw):
    """生成包含 Markdown 标记的有效文本内容"""
    lines = []
    # 生成 3~10 行内容
    num_lines = draw(st.integers(min_value=3, max_value=10))
    for i in range(num_lines):
        line_text = draw(_md_plain_line)
        # 随机决定是否添加 Markdown 标记
        line_type = draw(st.sampled_from(["plain", "heading", "emphasis", "list"]))
        if line_type == "heading":
            heading = draw(_md_heading)
            lines.append(heading + line_text)
        elif line_type == "emphasis":
            em = draw(_md_emphasis)
            lines.append(em + line_text + em)
        elif line_type == "list":
            marker = draw(_md_list_marker)
            lines.append(marker + line_text)
        else:
            lines.append(line_text)

    content = "\n".join(lines)
    # 确保解析后的文本满足最小长度要求
    parsed = parse_file_content(content, "test.md")
    if len(parsed.strip()) < MIN_TEXT_LENGTH:
        # 补充足够长度的纯文本
        padding = "补充文本内容" * (MIN_TEXT_LENGTH // 6 + 1)
        content = content + "\n" + padding
    return content


# Markdown 文件名策略
md_filename_st = st.sampled_from(["story.md", "content.markdown", "novel.md", "text.MARKDOWN"])

# TXT 文件名策略
txt_filename_st = st.sampled_from(["story.txt", "content.txt", "novel.TXT", "input.txt"])


# --- 辅助函数 ---

def run_async(coro):
    """在新事件循环中运行异步协程"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _create_project(client: AsyncClient) -> str:
    """创建一个测试项目，返回项目 ID"""
    resp = await client.post("/api/projects", json={
        "name": "测试项目",
        "template_id": "anime",
    })
    assert resp.status_code == 201
    return resp.json()["id"]


async def _submit_and_read_text(text: str, filename: str | None = None):
    """提交文本后读取项目，返回存储的 source_text"""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        set_db_path(db_path)
        await init_db()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 创建项目
            project_id = await _create_project(client)

            # 提交文本
            payload = {"text": text}
            if filename:
                payload["filename"] = filename

            submit_resp = await client.post(
                f"/api/projects/{project_id}/text", json=payload
            )
            assert submit_resp.status_code == 200, (
                f"提交失败: {submit_resp.status_code} {submit_resp.text}"
            )
            submit_data = submit_resp.json()
            assert submit_data["status"] == "valid", (
                f"校验未通过: {submit_data['message']}"
            )

            # 读取项目
            get_resp = await client.get(f"/api/projects/{project_id}")
            assert get_resp.status_code == 200
            return get_resp.json()["source_text"]


# --- Property 2: 文本存储往返一致性 ---

@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(text=valid_text_st)
def test_property_2_text_storage_round_trip(text):
    """
    Property 2: 文本存储往返一致性

    对任意有效文本内容，提交存储后再读取应当得到与原始输入完全相同的文本。

    **Validates: Requirements 1.1, 1.2**
    """
    stored_text = run_async(_submit_and_read_text(text))
    assert stored_text == text, (
        f"文本存储往返不一致:\n"
        f"  原始长度: {len(text)}\n"
        f"  存储长度: {len(stored_text) if stored_text else 'None'}"
    )


# --- Property 3: 文件导入往返一致性 ---

@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(text=txt_content_st, filename=txt_filename_st)
def test_property_3_txt_file_import_round_trip(text, filename):
    """
    Property 3: 文件导入往返一致性 (TXT)

    对任意有效的 TXT 文件内容，导入后读取应当得到与原始文件内容相同的文本。

    **Validates: Requirements 1.1, 1.2**
    """
    stored_text = run_async(_submit_and_read_text(text, filename))
    # TXT 文件不做转换，存储内容应与原始内容完全一致
    assert stored_text == text, (
        f"TXT 文件导入往返不一致:\n"
        f"  文件名: {filename}\n"
        f"  原始长度: {len(text)}\n"
        f"  存储长度: {len(stored_text) if stored_text else 'None'}"
    )


@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)
@given(content=markdown_content_st(), filename=md_filename_st)
def test_property_3_markdown_file_import_round_trip(content, filename):
    """
    Property 3: 文件导入往返一致性 (Markdown)

    对任意有效的 Markdown 文件内容，导入后读取应当得到与
    parse_file_content(原始内容) 等价的文本。

    **Validates: Requirements 1.1, 1.2**
    """
    # 预期存储的文本是经过 Markdown 解析后的纯文本
    expected = parse_file_content(content, filename)
    stored_text = run_async(_submit_and_read_text(content, filename))
    assert stored_text == expected, (
        f"Markdown 文件导入往返不一致:\n"
        f"  文件名: {filename}\n"
        f"  原始内容长度: {len(content)}\n"
        f"  预期长度: {len(expected)}\n"
        f"  存储长度: {len(stored_text) if stored_text else 'None'}"
    )
