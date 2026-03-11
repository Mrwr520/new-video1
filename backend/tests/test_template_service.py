"""模板服务单元测试"""

import pytest

from app.services.template_service import (
    ANIME_TEMPLATE,
    BUILTIN_TEMPLATES,
    MATH_TEMPLATE,
    SCIENCE_TEMPLATE,
    ContentTemplate,
    TemplateService,
)


@pytest.fixture
def service():
    """每个测试创建新的 TemplateService 实例"""
    return TemplateService()


class TestBuiltinTemplates:
    """内置模板定义测试"""

    def test_three_builtin_templates_exist(self, service: TemplateService):
        """应包含三个内置模板"""
        templates = service.list_templates()
        assert len(templates) == 3

    def test_anime_template_type(self):
        """动漫模板类型应为 anime"""
        assert ANIME_TEMPLATE.type == "anime"
        assert ANIME_TEMPLATE.is_builtin is True

    def test_science_template_type(self):
        """科普模板类型应为 science"""
        assert SCIENCE_TEMPLATE.type == "science"
        assert SCIENCE_TEMPLATE.is_builtin is True

    def test_math_template_type(self):
        """数学模板类型应为 math"""
        assert MATH_TEMPLATE.type == "math"
        assert MATH_TEMPLATE.is_builtin is True

    @pytest.mark.parametrize("tpl", list(BUILTIN_TEMPLATES.values()), ids=lambda t: t.type)
    def test_builtin_template_has_all_required_fields(self, tpl: ContentTemplate):
        """每个内置模板应包含所有必要字段且非空"""
        assert tpl.id
        assert tpl.name
        assert tpl.type
        assert tpl.character_extraction_prompt
        assert tpl.storyboard_prompt
        assert isinstance(tpl.image_style, dict) and tpl.image_style
        assert isinstance(tpl.motion_style, dict) and tpl.motion_style
        assert isinstance(tpl.voice_config, dict) and tpl.voice_config
        assert isinstance(tpl.subtitle_style, dict) and tpl.subtitle_style

    def test_anime_template_image_style_is_anime(self):
        """动漫模板图像风格预设应为 anime"""
        assert ANIME_TEMPLATE.image_style["style_preset"] == "anime"

    def test_science_template_image_style_is_infographic(self):
        """科普模板图像风格预设应为 infographic"""
        assert SCIENCE_TEMPLATE.image_style["style_preset"] == "infographic"

    def test_math_template_image_style_is_blackboard(self):
        """数学模板图像风格预设应为 blackboard"""
        assert MATH_TEMPLATE.image_style["style_preset"] == "blackboard"

    def test_anime_storyboard_mentions_plot(self):
        """动漫模板分镜 prompt 应包含情节推进相关内容"""
        assert "情节" in ANIME_TEMPLATE.storyboard_prompt

    def test_science_storyboard_mentions_knowledge(self):
        """科普模板分镜 prompt 应包含知识点拆分相关内容"""
        assert "知识点" in SCIENCE_TEMPLATE.storyboard_prompt

    def test_math_storyboard_mentions_derivation(self):
        """数学模板分镜 prompt 应包含推导过程相关内容"""
        assert "推导" in MATH_TEMPLATE.storyboard_prompt


class TestTemplateServiceCRUD:
    """模板服务 CRUD 操作测试"""

    def test_list_returns_all_templates(self, service: TemplateService):
        """list_templates 应返回所有模板"""
        templates = service.list_templates()
        ids = {t.id for t in templates}
        assert "builtin-anime" in ids
        assert "builtin-science" in ids
        assert "builtin-math" in ids

    def test_get_existing_template(self, service: TemplateService):
        """get_template 应返回指定模板"""
        tpl = service.get_template("builtin-anime")
        assert tpl is not None
        assert tpl.type == "anime"

    def test_get_nonexistent_template_returns_none(self, service: TemplateService):
        """get_template 对不存在的 ID 应返回 None"""
        assert service.get_template("nonexistent") is None

    def test_get_returns_deep_copy(self, service: TemplateService):
        """get_template 返回的应是深拷贝，修改不影响原模板"""
        tpl = service.get_template("builtin-anime")
        tpl.name = "modified"
        original = service.get_template("builtin-anime")
        assert original.name == "动漫小说"

    def test_create_custom_template(self, service: TemplateService):
        """应能创建自定义模板"""
        tpl = service.create_custom_template({
            "name": "我的模板",
            "type": "anime",
        })
        assert tpl.id.startswith("custom-")
        assert tpl.name == "我的模板"
        assert tpl.is_builtin is False
        # 应继承动漫模板的默认值
        assert tpl.character_extraction_prompt == ANIME_TEMPLATE.character_extraction_prompt

    def test_create_custom_template_with_overrides(self, service: TemplateService):
        """创建自定义模板时可覆盖默认字段"""
        tpl = service.create_custom_template({
            "name": "自定义科普",
            "type": "science",
            "storyboard_prompt": "自定义分镜 prompt",
        })
        assert tpl.storyboard_prompt == "自定义分镜 prompt"
        # 未覆盖的字段应继承科普模板默认值
        assert tpl.character_extraction_prompt == SCIENCE_TEMPLATE.character_extraction_prompt

    def test_create_increases_template_count(self, service: TemplateService):
        """创建自定义模板后列表数量应增加"""
        before = len(service.list_templates())
        service.create_custom_template({"name": "新模板", "type": "math"})
        after = len(service.list_templates())
        assert after == before + 1

    def test_update_template(self, service: TemplateService):
        """应能更新模板字段"""
        updated = service.update_template("builtin-anime", {"name": "新名称"})
        assert updated is not None
        assert updated.name == "新名称"
        # 其他字段不变
        assert updated.type == "anime"

    def test_update_nonexistent_returns_none(self, service: TemplateService):
        """更新不存在的模板应返回 None"""
        assert service.update_template("nonexistent", {"name": "x"}) is None

    def test_update_multiple_fields(self, service: TemplateService):
        """应能同时更新多个字段"""
        updated = service.update_template("builtin-anime", {
            "name": "更新名称",
            "image_style": {"style_preset": "custom", "width": 512, "height": 512},
        })
        assert updated.name == "更新名称"
        assert updated.image_style["style_preset"] == "custom"

    def test_delete_custom_template(self, service: TemplateService):
        """应能删除自定义模板"""
        tpl = service.create_custom_template({"name": "临时", "type": "anime"})
        assert service.delete_template(tpl.id) is True
        assert service.get_template(tpl.id) is None

    def test_delete_builtin_template_fails(self, service: TemplateService):
        """不应能删除内置模板"""
        assert service.delete_template("builtin-anime") is False
        assert service.get_template("builtin-anime") is not None

    def test_delete_nonexistent_returns_false(self, service: TemplateService):
        """删除不存在的模板应返回 False"""
        assert service.delete_template("nonexistent") is False
