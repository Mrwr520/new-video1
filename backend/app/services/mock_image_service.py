"""模拟图像生成服务

用于测试和演示，不需要真实的 API Key 或本地模型。
生成带有场景描述文字的占位图片。

特点：
- 无需 API Key
- 无需下载模型
- 快速生成占位图片
- 与 ImageGeneratorService 接口一致
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from app.models.character import Character
from app.models.scene import StoryboardScene
from app.services.image_service import (
    build_image_prompt,
    get_image_size,
    DEFAULT_PROJECTS_DIR,
)

logger = logging.getLogger(__name__)


class MockImageGeneratorService:
    """模拟图像生成服务。
    
    生成带有场景描述的占位图片，用于测试和演示。
    """

    def __init__(
        self,
        projects_dir: Optional[Path] = None,
        delay: float = 2.0,  # 模拟生成延迟
    ):
        self.projects_dir = projects_dir or DEFAULT_PROJECTS_DIR
        self.delay = delay

    async def generate_keyframe(
        self,
        scene: StoryboardScene,
        characters: list[Character],
        style_config: dict,
        project_id: str = "default",
    ) -> str:
        """生成模拟关键帧图片，返回文件路径。"""
        # 模拟生成延迟
        await asyncio.sleep(self.delay)

        prompt = build_image_prompt(scene, characters, style_config)
        width, height = get_image_size(style_config)

        # 生成占位图片
        file_path = self._generate_placeholder(
            prompt=prompt,
            scene_description=scene.scene_description,
            width=width,
            height=height,
            project_id=project_id,
            scene_id=scene.id,
        )

        logger.info("模拟生成关键帧: %s", file_path)
        return file_path

    async def regenerate_keyframe(
        self,
        scene: StoryboardScene,
        characters: list[Character],
        style_config: dict,
        project_id: str = "default",
    ) -> str:
        """重新生成关键帧"""
        return await self.generate_keyframe(scene, characters, style_config, project_id)

    def _generate_placeholder(
        self,
        prompt: str,
        scene_description: str,
        width: int,
        height: int,
        project_id: str,
        scene_id: str,
    ) -> str:
        """生成带有场景描述的占位图片"""
        try:
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            raise RuntimeError("需要安装 Pillow: pip install Pillow")

        # 创建图片
        image = Image.new("RGB", (width, height), color=(30, 40, 60))
        draw = ImageDraw.Draw(image)

        # 尝试使用系统字体，失败则使用默认字体
        try:
            # Windows
            font_large = ImageFont.truetype("msyh.ttc", 32)
            font_small = ImageFont.truetype("msyh.ttc", 20)
        except Exception:
            try:
                # Linux
                font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
                font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
            except Exception:
                # 降级到默认字体
                font_large = ImageFont.load_default()
                font_small = ImageFont.load_default()

        # 绘制标题
        title = "模拟生成的关键帧"
        title_bbox = draw.textbbox((0, 0), title, font=font_large)
        title_width = title_bbox[2] - title_bbox[0]
        title_x = (width - title_width) // 2
        draw.text((title_x, 50), title, fill=(255, 255, 255), font=font_large)

        # 绘制场景描述（多行文本）
        desc_lines = self._wrap_text(scene_description, width - 100, draw, font_small)
        y_offset = 150
        for line in desc_lines[:5]:  # 最多显示 5 行
            line_bbox = draw.textbbox((0, 0), line, font=font_small)
            line_width = line_bbox[2] - line_bbox[0]
            line_x = (width - line_width) // 2
            draw.text((line_x, y_offset), line, fill=(200, 200, 200), font=font_small)
            y_offset += 35

        # 绘制 prompt 提示（底部）
        prompt_preview = prompt[:80] + "..." if len(prompt) > 80 else prompt
        prompt_lines = self._wrap_text(f"Prompt: {prompt_preview}", width - 100, draw, font_small)
        y_offset = height - 100
        for line in prompt_lines[:2]:  # 最多显示 2 行
            draw.text((50, y_offset), line, fill=(150, 150, 150), font=font_small)
            y_offset += 30

        # 保存图片
        keyframes_dir = self.projects_dir / project_id / "keyframes"
        keyframes_dir.mkdir(parents=True, exist_ok=True)

        filename = f"scene_{scene_id}.png"
        file_path = keyframes_dir / filename
        image.save(str(file_path), format="PNG")

        return str(file_path)

    @staticmethod
    def _wrap_text(text: str, max_width: int, draw, font) -> list[str]:
        """将文本按宽度换行"""
        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            test_line = current_line + word + " "
            bbox = draw.textbbox((0, 0), test_line, font=font)
            width = bbox[2] - bbox[0]
            
            if width <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line.strip())
                current_line = word + " "

        if current_line:
            lines.append(current_line.strip())

        return lines

    async def close(self) -> None:
        """兼容 ImageGeneratorService 的 close 接口"""
        pass
