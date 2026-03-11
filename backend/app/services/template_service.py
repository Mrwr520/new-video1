"""内容模板服务

管理内置模板和自定义模板的 CRUD 操作。
内置模板包含动漫（anime）、科普（science）、数学（math）三种类型。
"""

import copy
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class ContentTemplate:
    """内容模板数据类"""
    id: str
    name: str
    type: str                          # "anime" | "science" | "math" | 自定义
    character_extraction_prompt: str    # 角色提取 prompt 模板
    storyboard_prompt: str             # 分镜生成 prompt 模板
    image_style: dict                  # 图像风格参数
    motion_style: dict                 # 运动风格参数
    voice_config: dict                 # 语音配置
    subtitle_style: dict               # 字幕样式
    is_builtin: bool = True            # 是否为内置模板

    def to_dict(self) -> dict:
        """转换为字典"""
        return asdict(self)


# ============================================================
# 内置模板定义
# ============================================================

ANIME_TEMPLATE = ContentTemplate(
    id="builtin-anime",
    name="动漫小说",
    type="anime",
    character_extraction_prompt=(
        "你是一位专业的动漫角色分析师。请从以下小说文本中提取所有角色信息。\n"
        "对每个角色，请提供：\n"
        "1. 姓名\n"
        "2. 外貌描述（发色、瞳色、身高、体型、标志性特征，用动漫画风描述）\n"
        "3. 性格特征（核心性格、说话方式、口头禅）\n"
        "4. 背景信息（身份、与其他角色的关系）\n"
        "请以 JSON 数组格式输出，每个角色包含 name、appearance、personality、background 字段。\n"
        "注意：外貌描述应适合作为 AI 绘画的 prompt，使用动漫风格关键词。"
    ),
    storyboard_prompt=(
        "你是一位专业的动漫分镜师。请将以下小说文本拆解为分镜脚本。\n"
        "分镜策略：以情节推进为核心，注重戏剧冲突和情感高潮。\n"
        "每个分镜应包含：\n"
        "1. scene_description：场景的视觉描述（环境、光影、氛围，使用动漫画风关键词）\n"
        "2. dialogue：该场景的台词或旁白\n"
        "3. camera_direction：镜头指示（远景/中景/近景/特写，运镜方式）\n"
        "分镜原则：\n"
        "- 对话场景使用正反打镜头切换\n"
        "- 情感高潮使用特写镜头\n"
        "- 场景转换时使用远景建立环境\n"
        "- 动作场景使用快速切换和动态构图\n"
        "请以 JSON 数组格式输出。"
    ),
    image_style={
        "style_preset": "anime",
        "negative_prompt": "realistic, photo, 3d render, blurry, low quality, deformed",
        "width": 1024,
        "height": 576,
        "guidance_scale": 7.5,
        "extra": {
            "sampler": "euler_a",
            "steps": 30,
            "style_keywords": "anime style, vibrant colors, detailed, cel shading",
        },
    },
    motion_style={
        "motion_intensity": 0.6,
        "fps": 24,
        "duration": 5.0,
        "transition_type": "fade",
    },
    voice_config={
        "engine": "edge-tts",
        "default_voice": "zh-CN-XiaoxiaoNeural",
        "speed": 1.0,
        "pitch": 0.0,
    },
    subtitle_style={
        "font_size": 26,
        "font_color": "#FFFFFF",
        "bg_color": "#000000AA",
        "position": "bottom",
    },
    is_builtin=True,
)

SCIENCE_TEMPLATE = ContentTemplate(
    id="builtin-science",
    name="科普讲解",
    type="science",
    character_extraction_prompt=(
        "你是一位科普内容分析师。请从以下科普文本中提取需要可视化的关键元素。\n"
        "对每个元素，请提供：\n"
        "1. 姓名（概念名称或讲解者角色）\n"
        "2. 外貌描述（如果是讲解者：职业形象；如果是概念：拟人化或图标化描述）\n"
        "3. 性格特征（讲解风格：严谨/活泼/通俗）\n"
        "4. 背景信息（学科领域、知识层级）\n"
        "请以 JSON 数组格式输出，每个元素包含 name、appearance、personality、background 字段。\n"
        "注意：描述应适合生成信息图表风格的插图。"
    ),
    storyboard_prompt=(
        "你是一位专业的科普视频编导。请将以下科普文本拆解为分镜脚本。\n"
        "分镜策略：以知识点拆分为核心，确保每个分镜聚焦一个知识点。\n"
        "每个分镜应包含：\n"
        "1. scene_description：场景描述（使用图表、示意图、信息图表风格描述）\n"
        "2. dialogue：讲解旁白文本\n"
        "3. camera_direction：镜头指示（全屏图表/画中画/缩放聚焦）\n"
        "分镜原则：\n"
        "- 开头使用引入性问题或现象激发兴趣\n"
        "- 每个知识点配合直观的图表或示意图\n"
        "- 复杂概念使用逐步展开的动画分镜\n"
        "- 结尾使用总结回顾分镜\n"
        "- 适当插入生活化类比帮助理解\n"
        "请以 JSON 数组格式输出。"
    ),
    image_style={
        "style_preset": "infographic",
        "negative_prompt": "anime, cartoon, blurry, low quality, cluttered",
        "width": 1024,
        "height": 576,
        "guidance_scale": 8.0,
        "extra": {
            "sampler": "ddim",
            "steps": 35,
            "style_keywords": "clean infographic, flat design, diagram, educational illustration",
        },
    },
    motion_style={
        "motion_intensity": 0.3,
        "fps": 30,
        "duration": 6.0,
        "transition_type": "slide",
    },
    voice_config={
        "engine": "edge-tts",
        "default_voice": "zh-CN-YunxiNeural",
        "speed": 0.95,
        "pitch": 0.0,
    },
    subtitle_style={
        "font_size": 22,
        "font_color": "#333333",
        "bg_color": "#FFFFFFDD",
        "position": "bottom",
    },
    is_builtin=True,
)

MATH_TEMPLATE = ContentTemplate(
    id="builtin-math",
    name="数学讲解",
    type="math",
    character_extraction_prompt=(
        "你是一位数学教育内容分析师。请从以下数学讲解文本中提取关键元素。\n"
        "对每个元素，请提供：\n"
        "1. 姓名（数学概念名称、定理名称或讲解者角色）\n"
        "2. 外貌描述（公式的视觉呈现方式、几何图形描述、或讲解者形象）\n"
        "3. 性格特征（讲解风格：严谨推导/直觉引导/趣味探索）\n"
        "4. 背景信息（数学分支、前置知识、难度级别）\n"
        "请以 JSON 数组格式输出，每个元素包含 name、appearance、personality、background 字段。\n"
        "注意：描述应适合生成黑板/白板风格的数学可视化插图。"
    ),
    storyboard_prompt=(
        "你是一位专业的数学教学视频编导。请将以下数学讲解文本拆解为分镜脚本。\n"
        "分镜策略：以推导过程可视化为核心，逐步展示数学推理链条。\n"
        "每个分镜应包含：\n"
        "1. scene_description：场景描述（公式展示方式、几何图形、坐标系、推导步骤的视觉布局）\n"
        "2. dialogue：讲解旁白文本\n"
        "3. camera_direction：镜头指示（全屏公式/逐行展开/局部高亮/图形变换）\n"
        "分镜原则：\n"
        "- 先展示问题或定理陈述\n"
        "- 推导过程逐步展开，每步一个分镜\n"
        "- 关键步骤使用高亮和放大\n"
        "- 几何直觉与代数推导交替呈现\n"
        "- 最终结论使用醒目的框线标注\n"
        "- 适当插入直观的几何动画辅助理解\n"
        "请以 JSON 数组格式输出。"
    ),
    image_style={
        "style_preset": "blackboard",
        "negative_prompt": "anime, photo, blurry, low quality, cluttered background",
        "width": 1024,
        "height": 576,
        "guidance_scale": 7.0,
        "extra": {
            "sampler": "ddim",
            "steps": 30,
            "style_keywords": "mathematical notation, blackboard style, clean layout, LaTeX rendering",
        },
    },
    motion_style={
        "motion_intensity": 0.2,
        "fps": 30,
        "duration": 8.0,
        "transition_type": "fade",
    },
    voice_config={
        "engine": "edge-tts",
        "default_voice": "zh-CN-YunjianNeural",
        "speed": 0.9,
        "pitch": 0.0,
    },
    subtitle_style={
        "font_size": 20,
        "font_color": "#FFFFFF",
        "bg_color": "#1A1A2EDD",
        "position": "bottom",
    },
    is_builtin=True,
)

# 内置模板注册表
BUILTIN_TEMPLATES: dict[str, ContentTemplate] = {
    ANIME_TEMPLATE.id: ANIME_TEMPLATE,
    SCIENCE_TEMPLATE.id: SCIENCE_TEMPLATE,
    MATH_TEMPLATE.id: MATH_TEMPLATE,
}


class TemplateService:
    """内容模板服务，管理内置模板和自定义模板"""

    def __init__(self) -> None:
        # 内置模板（不可删除）+ 自定义模板
        self._templates: dict[str, ContentTemplate] = {}
        # 加载内置模板
        for tid, tpl in BUILTIN_TEMPLATES.items():
            self._templates[tid] = copy.deepcopy(tpl)

    def list_templates(self) -> list[ContentTemplate]:
        """列出所有模板"""
        return list(self._templates.values())

    def get_template(self, template_id: str) -> Optional[ContentTemplate]:
        """根据 ID 获取模板，不存在返回 None"""
        tpl = self._templates.get(template_id)
        return copy.deepcopy(tpl) if tpl else None

    def create_custom_template(self, data: dict) -> ContentTemplate:
        """创建自定义模板

        data 中必须包含 name 和 type 字段，其余字段可选，
        缺省时从同类型的内置模板继承默认值。
        """
        template_id = f"custom-{uuid.uuid4().hex[:8]}"

        # 查找同类型内置模板作为默认值基础
        base = self._find_base_template(data.get("type", "anime"))

        template = ContentTemplate(
            id=template_id,
            name=data["name"],
            type=data.get("type", "anime"),
            character_extraction_prompt=data.get(
                "character_extraction_prompt", base.character_extraction_prompt
            ),
            storyboard_prompt=data.get(
                "storyboard_prompt", base.storyboard_prompt
            ),
            image_style=data.get("image_style", copy.deepcopy(base.image_style)),
            motion_style=data.get("motion_style", copy.deepcopy(base.motion_style)),
            voice_config=data.get("voice_config", copy.deepcopy(base.voice_config)),
            subtitle_style=data.get("subtitle_style", copy.deepcopy(base.subtitle_style)),
            is_builtin=False,
        )
        self._templates[template_id] = template
        return copy.deepcopy(template)

    def update_template(self, template_id: str, data: dict) -> Optional[ContentTemplate]:
        """更新模板字段，返回更新后的模板；不存在返回 None"""
        tpl = self._templates.get(template_id)
        if tpl is None:
            return None

        # 逐字段更新（仅更新 data 中提供的字段）
        if "name" in data:
            tpl.name = data["name"]
        if "character_extraction_prompt" in data:
            tpl.character_extraction_prompt = data["character_extraction_prompt"]
        if "storyboard_prompt" in data:
            tpl.storyboard_prompt = data["storyboard_prompt"]
        if "image_style" in data:
            tpl.image_style = data["image_style"]
        if "motion_style" in data:
            tpl.motion_style = data["motion_style"]
        if "voice_config" in data:
            tpl.voice_config = data["voice_config"]
        if "subtitle_style" in data:
            tpl.subtitle_style = data["subtitle_style"]

        return copy.deepcopy(tpl)

    def delete_template(self, template_id: str) -> bool:
        """删除自定义模板，内置模板不可删除。返回是否成功删除。"""
        tpl = self._templates.get(template_id)
        if tpl is None:
            return False
        if tpl.is_builtin:
            return False
        del self._templates[template_id]
        return True

    def _find_base_template(self, template_type: str) -> ContentTemplate:
        """查找同类型的内置模板作为默认值基础，找不到则用动漫模板"""
        for tpl in BUILTIN_TEMPLATES.values():
            if tpl.type == template_type:
                return tpl
        return ANIME_TEMPLATE
