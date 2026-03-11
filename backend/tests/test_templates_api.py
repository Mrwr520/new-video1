"""模板 API 端点集成测试"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.templates import set_template_service
from app.main import app
from app.services.template_service import TemplateService


@pytest_asyncio.fixture
async def template_client(tmp_db):
    """创建测试客户端，每个测试使用新的 TemplateService"""
    set_template_service(TemplateService())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestListTemplates:
    """GET /api/templates"""

    @pytest.mark.asyncio
    async def test_list_returns_builtin_templates(self, template_client):
        """应返回三个内置模板"""
        resp = await template_client.get("/api/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        types = {t["type"] for t in data["templates"]}
        assert types == {"anime", "science", "math"}

    @pytest.mark.asyncio
    async def test_list_template_fields(self, template_client):
        """每个模板应包含所有必要字段"""
        resp = await template_client.get("/api/templates")
        for tpl in resp.json()["templates"]:
            assert "id" in tpl
            assert "name" in tpl
            assert "type" in tpl
            assert "character_extraction_prompt" in tpl
            assert "storyboard_prompt" in tpl
            assert "image_style" in tpl
            assert "motion_style" in tpl
            assert "voice_config" in tpl
            assert "subtitle_style" in tpl
            assert "is_builtin" in tpl


class TestGetTemplate:
    """GET /api/templates/{id}"""

    @pytest.mark.asyncio
    async def test_get_existing_template(self, template_client):
        """应能获取指定模板"""
        resp = await template_client.get("/api/templates/builtin-anime")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "anime"
        assert data["is_builtin"] is True

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_404(self, template_client):
        """获取不存在的模板应返回 404"""
        resp = await template_client.get("/api/templates/nonexistent")
        assert resp.status_code == 404


class TestCreateTemplate:
    """POST /api/templates"""

    @pytest.mark.asyncio
    async def test_create_custom_template(self, template_client):
        """应能创建自定义模板"""
        resp = await template_client.post("/api/templates", json={
            "name": "我的动漫模板",
            "type": "anime",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "我的动漫模板"
        assert data["is_builtin"] is False
        assert data["id"].startswith("custom-")

    @pytest.mark.asyncio
    async def test_create_with_custom_fields(self, template_client):
        """创建时可指定自定义字段"""
        resp = await template_client.post("/api/templates", json={
            "name": "自定义",
            "type": "science",
            "storyboard_prompt": "我的分镜 prompt",
            "image_style": {"style_preset": "custom", "width": 512},
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["storyboard_prompt"] == "我的分镜 prompt"
        assert data["image_style"]["style_preset"] == "custom"

    @pytest.mark.asyncio
    async def test_create_appears_in_list(self, template_client):
        """创建的模板应出现在列表中"""
        await template_client.post("/api/templates", json={
            "name": "新模板",
            "type": "math",
        })
        resp = await template_client.get("/api/templates")
        assert resp.json()["total"] == 4

    @pytest.mark.asyncio
    async def test_create_missing_name_returns_422(self, template_client):
        """缺少 name 字段应返回 422"""
        resp = await template_client.post("/api/templates", json={
            "type": "anime",
        })
        assert resp.status_code == 422


class TestUpdateTemplate:
    """PUT /api/templates/{id}"""

    @pytest.mark.asyncio
    async def test_update_template_name(self, template_client):
        """应能更新模板名称"""
        resp = await template_client.put("/api/templates/builtin-anime", json={
            "name": "新动漫名称",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "新动漫名称"

    @pytest.mark.asyncio
    async def test_update_preserves_other_fields(self, template_client):
        """更新部分字段不应影响其他字段"""
        # 先获取原始数据
        original = (await template_client.get("/api/templates/builtin-anime")).json()
        # 只更新名称
        resp = await template_client.put("/api/templates/builtin-anime", json={
            "name": "新名称",
        })
        updated = resp.json()
        assert updated["name"] == "新名称"
        assert updated["type"] == original["type"]
        assert updated["storyboard_prompt"] == original["storyboard_prompt"]

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_404(self, template_client):
        """更新不存在的模板应返回 404"""
        resp = await template_client.put("/api/templates/nonexistent", json={
            "name": "x",
        })
        assert resp.status_code == 404
