"""文本校验服务和文本提交 API 的单元测试"""

import pytest
import pytest_asyncio

from app.services.text_service import (
    MIN_TEXT_LENGTH,
    MAX_TEXT_LENGTH,
    ValidationStatus,
    validate_text,
    parse_file_content,
)


# ============================================================
# validate_text 纯函数测试
# ============================================================

class TestValidateText:
    """文本校验纯函数测试"""

    def test_empty_string_is_invalid(self):
        result = validate_text("")
        assert result.status == ValidationStatus.INVALID
        assert result.char_count == 0

    def test_whitespace_only_is_invalid(self):
        result = validate_text("   \t\n  ")
        assert result.status == ValidationStatus.INVALID
        assert result.char_count == 0

    def test_too_short_is_invalid(self):
        short_text = "a" * (MIN_TEXT_LENGTH - 1)
        result = validate_text(short_text)
        assert result.status == ValidationStatus.INVALID
        assert result.char_count == len(short_text)

    def test_too_long_is_invalid(self):
        long_text = "a" * (MAX_TEXT_LENGTH + 1)
        result = validate_text(long_text)
        assert result.status == ValidationStatus.INVALID
        assert result.char_count == len(long_text)

    def test_exact_min_length_is_valid(self):
        text = "a" * MIN_TEXT_LENGTH
        result = validate_text(text)
        assert result.status == ValidationStatus.VALID

    def test_exact_max_length_is_valid(self):
        text = "a" * MAX_TEXT_LENGTH
        result = validate_text(text)
        assert result.status == ValidationStatus.VALID

    def test_normal_text_is_valid(self):
        result = validate_text("这是一段足够长的正常文本内容，用于测试校验逻辑。")
        assert result.status == ValidationStatus.VALID
        assert result.char_count > 0

    def test_strips_whitespace_before_validation(self):
        # 内容去除空白后刚好达到最小长度
        text = "  " + "a" * MIN_TEXT_LENGTH + "  "
        result = validate_text(text)
        assert result.status == ValidationStatus.VALID
        assert result.char_count == MIN_TEXT_LENGTH


# ============================================================
# parse_file_content 文件解析测试
# ============================================================

class TestParseFileContent:
    """文件内容解析测试"""

    def test_txt_file_returns_content_as_is(self):
        content = "Hello, this is plain text."
        result = parse_file_content(content, "story.txt")
        assert result == content

    def test_md_file_strips_headings(self):
        content = "# Title\n\nSome paragraph text."
        result = parse_file_content(content, "story.md")
        assert "# " not in result
        assert "Title" in result
        assert "Some paragraph text." in result

    def test_md_file_strips_bold_italic(self):
        content = "This is **bold** and *italic* text."
        result = parse_file_content(content, "doc.md")
        assert "**" not in result
        assert "*" not in result
        assert "bold" in result
        assert "italic" in result

    def test_md_file_strips_links(self):
        content = "Click [here](https://example.com) for more."
        result = parse_file_content(content, "readme.md")
        assert "[" not in result
        assert "here" in result

    def test_md_file_strips_images(self):
        content = "See ![alt](image.png) below."
        result = parse_file_content(content, "doc.markdown")
        assert "![" not in result

    def test_unknown_extension_treated_as_txt(self):
        content = "# Not stripped"
        result = parse_file_content(content, "file.unknown")
        assert result == content

    def test_case_insensitive_extension(self):
        content = "# Title\nBody"
        result = parse_file_content(content, "FILE.MD")
        assert "# " not in result


# ============================================================
# POST /api/projects/{id}/text API 端点测试
# ============================================================

class TestSubmitTextAPI:
    """文本提交 API 端点测试"""

    @pytest_asyncio.fixture
    async def project_id(self, client):
        """创建一个测试项目并返回其 ID"""
        resp = await client.post("/api/projects", json={
            "name": "测试项目",
            "template_id": "anime",
        })
        assert resp.status_code == 201
        return resp.json()["id"]

    @pytest.mark.asyncio
    async def test_submit_valid_text(self, client, project_id):
        resp = await client.post(f"/api/projects/{project_id}/text", json={
            "text": "这是一段足够长的测试文本，用于验证文本提交接口的正确性。",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "valid"
        assert data["char_count"] > 0

    @pytest.mark.asyncio
    async def test_submit_empty_text_returns_invalid(self, client, project_id):
        resp = await client.post(f"/api/projects/{project_id}/text", json={
            "text": "",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "invalid"

    @pytest.mark.asyncio
    async def test_submit_short_text_returns_invalid(self, client, project_id):
        resp = await client.post(f"/api/projects/{project_id}/text", json={
            "text": "短",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "invalid"

    @pytest.mark.asyncio
    async def test_submit_text_to_nonexistent_project(self, client):
        resp = await client.post("/api/projects/nonexistent/text", json={
            "text": "这是一段足够长的测试文本内容。",
        })
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_submit_text_updates_project(self, client, project_id):
        text = "这是一段足够长的测试文本，用于验证文本提交后项目状态更新。"
        await client.post(f"/api/projects/{project_id}/text", json={"text": text})

        # 验证项目已更新
        resp = await client.get(f"/api/projects/{project_id}")
        data = resp.json()
        assert data["source_text"] == text
        assert data["status"] == "text_submitted"

    @pytest.mark.asyncio
    async def test_submit_markdown_file(self, client, project_id):
        md_content = "# 标题\n\n这是一段 Markdown 格式的文本内容，包含足够的字符数。"
        resp = await client.post(f"/api/projects/{project_id}/text", json={
            "text": md_content,
            "filename": "story.md",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "valid"

        # 验证存储的是解析后的纯文本
        resp = await client.get(f"/api/projects/{project_id}")
        stored_text = resp.json()["source_text"]
        assert "# " not in stored_text
        assert "标题" in stored_text

    @pytest.mark.asyncio
    async def test_submit_txt_file(self, client, project_id):
        txt_content = "这是一段纯文本文件的内容，用于测试 TXT 文件导入功能。"
        resp = await client.post(f"/api/projects/{project_id}/text", json={
            "text": txt_content,
            "filename": "story.txt",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "valid"
