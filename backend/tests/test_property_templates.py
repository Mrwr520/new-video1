"""模板相关属性测试

Feature: ai-video-generator, Property 4: 模板加载正确性
Feature: ai-video-generator, Property 14: 模板自定义往返一致性

使用 hypothesis 生成随机模板类型和参数，验证模板加载与自定义更新的正确性。

**Validates: Requirements 1.4, 10.5**
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.template_service import TemplateService, ContentTemplate


# ============================================================
# 自定义策略
# ============================================================

# 有效的内置模板类型标识符
valid_template_types = st.sampled_from(["anime", "science", "math"])

# 内置模板 ID 与类型的映射
BUILTIN_ID_TYPE_MAP = {
    "builtin-anime": "anime",
    "builtin-science": "science",
    "builtin-math": "math",
}

valid_builtin_ids = st.sampled_from(list(BUILTIN_ID_TYPE_MAP.keys()))

# 非空字符串策略（用于 prompt 等文本字段）
non_empty_text = st.text(
    alphabet=st.characters(exclude_categories=("Cs",)),
    min_size=1,
    max_size=200,
).filter(lambda s: len(s.strip()) > 0)

# 图像风格字典策略
image_style_strategy = st.fixed_dictionaries({
    "style_preset": non_empty_text,
    "width": st.integers(min_value=256, max_value=2048),
    "height": st.integers(min_value=256, max_value=2048),
})

# 运动风格字典策略
motion_style_strategy = st.fixed_dictionaries({
    "motion_intensity": st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    "fps": st.integers(min_value=1, max_value=60),
    "duration": st.floats(min_value=0.5, max_value=30.0, allow_nan=False),
})

# 模板更新数据策略：随机选择要更新的字段子集
template_update_strategy = st.fixed_dictionaries(
    {},  # 无必填字段
    optional={
        "name": non_empty_text,
        "character_extraction_prompt": non_empty_text,
        "storyboard_prompt": non_empty_text,
        "image_style": image_style_strategy,
        "motion_style": motion_style_strategy,
    },
).filter(lambda d: len(d) > 0)  # 至少更新一个字段


# ============================================================
# Property 4: 模板加载正确性
# ============================================================

class TestTemplateLoadProperty:
    """Property 4: 模板加载正确性

    For any 有效的内容类型标识符，加载模板应当返回与该类型匹配的
    Content_Template 配置，且配置中包含所有必要字段
    （character_extraction_prompt、storyboard_prompt、image_style、motion_style）。

    **Validates: Requirements 1.4**
    """

    @given(template_id=valid_builtin_ids)
    @settings(max_examples=100)
    def test_builtin_template_loads_with_correct_type(self, template_id: str):
        """加载内置模板应返回与该 ID 对应类型匹配的模板"""
        service = TemplateService()
        template = service.get_template(template_id)

        assert template is not None
        assert isinstance(template, ContentTemplate)
        assert template.id == template_id
        assert template.type == BUILTIN_ID_TYPE_MAP[template_id]

    @given(template_id=valid_builtin_ids)
    @settings(max_examples=100)
    def test_builtin_template_has_all_required_fields(self, template_id: str):
        """加载的模板配置中包含所有必要字段且非空"""
        service = TemplateService()
        template = service.get_template(template_id)

        assert template is not None

        # character_extraction_prompt 必须存在且非空
        assert isinstance(template.character_extraction_prompt, str)
        assert len(template.character_extraction_prompt.strip()) > 0

        # storyboard_prompt 必须存在且非空
        assert isinstance(template.storyboard_prompt, str)
        assert len(template.storyboard_prompt.strip()) > 0

        # image_style 必须存在且为非空字典
        assert isinstance(template.image_style, dict)
        assert len(template.image_style) > 0

        # motion_style 必须存在且为非空字典
        assert isinstance(template.motion_style, dict)
        assert len(template.motion_style) > 0

    @given(template_id=valid_builtin_ids)
    @settings(max_examples=100)
    def test_builtin_template_is_marked_builtin(self, template_id: str):
        """内置模板的 is_builtin 标志应为 True"""
        service = TemplateService()
        template = service.get_template(template_id)

        assert template is not None
        assert template.is_builtin is True

    @given(template_type=valid_template_types)
    @settings(max_examples=100)
    def test_list_templates_contains_all_builtin_types(self, template_type: str):
        """模板列表中应包含所有内置类型"""
        service = TemplateService()
        templates = service.list_templates()
        types_in_list = [t.type for t in templates]

        assert template_type in types_in_list


# ============================================================
# Property 14: 模板自定义往返一致性
# ============================================================

class TestTemplateCustomRoundTripProperty:
    """Property 14: 模板自定义往返一致性

    For any 模板参数更新，更新后再读取应当得到包含更新内容的模板配置。

    **Validates: Requirements 10.5**
    """

    @given(
        base_type=valid_template_types,
        update_data=template_update_strategy,
    )
    @settings(max_examples=100)
    def test_custom_template_update_round_trip(
        self, base_type: str, update_data: dict
    ):
        """创建自定义模板后更新参数，再读取应包含更新内容"""
        service = TemplateService()

        # 创建自定义模板
        created = service.create_custom_template({
            "name": "测试模板",
            "type": base_type,
        })
        assert created is not None
        template_id = created.id

        # 应用更新
        updated = service.update_template(template_id, update_data)
        assert updated is not None

        # 重新读取
        reloaded = service.get_template(template_id)
        assert reloaded is not None

        # 验证更新的字段与读取结果一致
        for key, value in update_data.items():
            assert getattr(reloaded, key) == value, (
                f"字段 '{key}' 更新后读取不一致: "
                f"期望 {value!r}, 实际 {getattr(reloaded, key)!r}"
            )

    @given(
        base_type=valid_template_types,
        update_data=template_update_strategy,
    )
    @settings(max_examples=100)
    def test_update_preserves_unmodified_fields(
        self, base_type: str, update_data: dict
    ):
        """更新模板时，未修改的字段应保持不变"""
        service = TemplateService()

        # 创建自定义模板
        created = service.create_custom_template({
            "name": "保持字段测试",
            "type": base_type,
        })
        template_id = created.id

        # 记录更新前的所有字段值
        before = service.get_template(template_id)
        assert before is not None

        # 应用更新
        service.update_template(template_id, update_data)

        # 重新读取
        after = service.get_template(template_id)
        assert after is not None

        # 未更新的可变字段应保持不变
        all_updatable_fields = [
            "name", "character_extraction_prompt", "storyboard_prompt",
            "image_style", "motion_style", "voice_config", "subtitle_style",
        ]
        for field_name in all_updatable_fields:
            if field_name not in update_data:
                assert getattr(after, field_name) == getattr(before, field_name), (
                    f"未更新字段 '{field_name}' 发生了变化"
                )

        # id、type、is_builtin 不应被更新改变
        assert after.id == before.id
        assert after.type == before.type
        assert after.is_builtin == before.is_builtin
