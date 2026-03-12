"""图像生成服务

支持 OpenAI 兼容的图像生成 API（DALL-E、Stable Diffusion API、Flux 等）。
实现 prompt 构建逻辑（结合场景描述 + 角色外貌 + 模板风格），
以及关键帧图片下载和存储。
"""

import logging
import uuid
from pathlib import Path
from typing import Optional

import httpx

from app.models.character import Character
from app.models.scene import StoryboardScene

logger = logging.getLogger(__name__)

# 默认项目文件存储根目录
DEFAULT_PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"

# 默认图像尺寸（16:9，满足 ≥1024x576 要求）
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 576


class ImageGenError(Exception):
    """图像生成服务基础异常"""

    def __init__(self, message: str, code: str = "IMAGE_GEN_FAILED", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ImageGenApiError(ImageGenError):
    """图像生成 API 调用错误"""

    def __init__(self, message: str, status_code: int = 0):
        retryable = status_code >= 500 or status_code == 429
        super().__init__(message, code="IMAGE_GEN_API_ERROR", retryable=retryable)
        self.status_code = status_code


class ImageGenTimeoutError(ImageGenError):
    """图像生成 API 超时"""

    def __init__(self, message: str = "图像生成 API 请求超时"):
        super().__init__(message, code="IMAGE_GEN_TIMEOUT", retryable=True)


# ============================================================
# Prompt 构建
# ============================================================

def build_image_prompt(
    scene: StoryboardScene,
    characters: list[Character],
    style_config: dict,
) -> str:
    """构建图像生成 prompt，结合场景描述 + 角色外貌 + 模板风格。

    策略：
    1. 以场景自带的 image_prompt 为基础（如果有）
    2. 追加出现在场景中的角色外貌描述，保持视觉一致性
    3. 追加模板风格关键词
    """
    parts: list[str] = []

    # 1) 场景 image_prompt 或 scene_description
    if scene.image_prompt and scene.image_prompt.strip():
        parts.append(scene.image_prompt.strip())
    elif scene.scene_description and scene.scene_description.strip():
        parts.append(scene.scene_description.strip())

    # 2) 角色外貌（用于保持视觉一致性 — Req 4.2）
    char_descriptions = []
    for char in characters:
        # 优先使用 image_prompt，其次 appearance
        desc = (char.image_prompt.strip() if char.image_prompt else "") or (
            char.appearance.strip() if char.appearance else ""
        )
        if desc:
            char_descriptions.append(desc)
    if char_descriptions:
        parts.append(", ".join(char_descriptions))

    # 3) 模板风格关键词
    extra = style_config.get("extra", {})
    style_keywords = extra.get("style_keywords", "")
    if style_keywords:
        parts.append(style_keywords)

    # 4) 风格预设
    style_preset = style_config.get("style_preset", "")
    if style_preset:
        parts.append(f"{style_preset} style")

    return ", ".join(p for p in parts if p)


def build_negative_prompt(style_config: dict) -> str:
    """从风格配置中提取 negative prompt"""
    return style_config.get("negative_prompt", "")


def get_image_size(style_config: dict) -> tuple[int, int]:
    """从风格配置中获取图像尺寸，确保不低于 1024x576"""
    width = style_config.get("width", DEFAULT_WIDTH)
    height = style_config.get("height", DEFAULT_HEIGHT)
    # 确保满足最低分辨率要求 (Req 4.6)
    if width < DEFAULT_WIDTH:
        width = DEFAULT_WIDTH
    if height < DEFAULT_HEIGHT:
        height = DEFAULT_HEIGHT
    return width, height


# ============================================================
# 图像生成服务
# ============================================================

class ImageGeneratorService:
    """图像生成服务，支持 OpenAI 兼容的图像生成 API。

    通过构造函数注入 HTTP 客户端，便于测试时 mock。
    """

    def __init__(
        self,
        api_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "dall-e-3",
        timeout: float = 120.0,
        max_retries: int = 3,
        projects_dir: Optional[Path] = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.projects_dir = projects_dir or DEFAULT_PROJECTS_DIR
        self._client = client
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
            self._owns_client = True
        return self._client

    async def close(self) -> None:
        if self._client and self._owns_client:
            await self._client.aclose()
            self._client = None

    # ----------------------------------------------------------
    # 公开接口
    # ----------------------------------------------------------

    async def generate_keyframe(
        self,
        scene: StoryboardScene,
        characters: list[Character],
        style_config: dict,
        project_id: str = "default",
    ) -> str:
        """生成单个分镜的关键帧图片，返回文件路径。

        Args:
            scene: 分镜场景
            characters: 角色列表（用于视觉一致性）
            style_config: 模板图像风格配置
            project_id: 项目 ID，用于确定存储路径

        Returns:
            生成的关键帧图片文件路径

        Raises:
            ImageGenError: 图像生成失败
        """
        prompt = build_image_prompt(scene, characters, style_config)
        negative_prompt = build_negative_prompt(style_config)
        width, height = get_image_size(style_config)

        image_url = await self._call_image_api(prompt, negative_prompt, width, height)
        file_path = await self._download_and_save(image_url, project_id, scene.id)
        return file_path

    async def regenerate_keyframe(
        self,
        scene: StoryboardScene,
        characters: list[Character],
        style_config: dict,
        project_id: str = "default",
    ) -> str:
        """重新生成关键帧（与 generate_keyframe 逻辑相同，生成新文件）"""
        return await self.generate_keyframe(scene, characters, style_config, project_id)

    # ----------------------------------------------------------
    # API 调用
    # ----------------------------------------------------------

    async def _call_image_api(
        self,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
    ) -> str:
        """调用 OpenAI 兼容的图像生成 API，返回图片 URL。

        支持 DALL-E 和 Stable Diffusion / Flux 等兼容接口。
        """
        client = await self._get_client()
        url = f"{self.api_url}/images/generations"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
            "size": f"{width}x{height}",
        }
        # negative_prompt 不是 OpenAI 标准字段，但许多兼容 API 支持
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                response = await client.post(url, json=payload, headers=headers)

                if response.status_code == 200:
                    return self._extract_image_url(response.json())

                if response.status_code >= 500 or response.status_code == 429:
                    last_error = ImageGenApiError(
                        f"图像 API 返回错误状态码: {response.status_code}",
                        status_code=response.status_code,
                    )
                    logger.warning(
                        "图像 API 错误 (尝试 %d/%d): %s",
                        attempt + 1, self.max_retries, last_error,
                    )
                    continue

                raise ImageGenApiError(
                    f"图像 API 返回错误: {response.status_code} - {response.text}",
                    status_code=response.status_code,
                )

            except httpx.TimeoutException:
                last_error = ImageGenTimeoutError()
                logger.warning(
                    "图像 API 超时 (尝试 %d/%d)", attempt + 1, self.max_retries,
                )
                continue
            except (ImageGenApiError, ImageGenTimeoutError):
                raise
            except ImageGenError:
                raise
            except Exception as e:
                raise ImageGenError(f"图像 API 调用异常: {e}")

        if last_error:
            raise last_error
        raise ImageGenError("图像 API 调用失败，已耗尽重试次数")

    @staticmethod
    def _extract_image_url(response_data: dict) -> str:
        """从 OpenAI 兼容响应中提取图片 URL"""
        try:
            data_list = response_data.get("data", [])
            if not data_list:
                raise ImageGenError("图像 API 响应中没有 data")
            # 优先取 url，其次 b64_json
            url = data_list[0].get("url", "")
            if url:
                return url
            # 如果是 base64 格式，返回 data URI
            b64 = data_list[0].get("b64_json", "")
            if b64:
                return f"data:image/png;base64,{b64}"
            raise ImageGenError("图像 API 响应中没有 url 或 b64_json")
        except (KeyError, IndexError, TypeError) as e:
            raise ImageGenError(f"图像 API 响应结构异常: {e}")

    # ----------------------------------------------------------
    # 下载和存储
    # ----------------------------------------------------------

    async def _download_and_save(
        self, image_url: str, project_id: str, scene_id: str
    ) -> str:
        """下载图片并保存到项目的 keyframes 目录。

        Args:
            image_url: 图片 URL 或 data URI
            project_id: 项目 ID
            scene_id: 场景 ID

        Returns:
            保存的文件路径（字符串）
        """
        keyframes_dir = self.projects_dir / project_id / "keyframes"
        keyframes_dir.mkdir(parents=True, exist_ok=True)

        filename = f"scene_{scene_id}.png"
        file_path = keyframes_dir / filename

        if image_url.startswith("data:"):
            # base64 data URI
            self._save_base64_image(image_url, file_path)
        else:
            # HTTP URL — download
            await self._download_image(image_url, file_path)

        return str(file_path)

    async def _download_image(self, url: str, file_path: Path) -> None:
        """从 URL 下载图片并保存"""
        client = await self._get_client()
        try:
            response = await client.get(url)
            if response.status_code != 200:
                raise ImageGenError(
                    f"下载图片失败: HTTP {response.status_code}",
                    code="IMAGE_DOWNLOAD_FAILED",
                    retryable=True,
                )
            file_path.write_bytes(response.content)
        except httpx.TimeoutException:
            raise ImageGenTimeoutError("下载图片超时")
        except ImageGenError:
            raise
        except Exception as e:
            raise ImageGenError(f"下载图片异常: {e}")

    @staticmethod
    def _save_base64_image(data_uri: str, file_path: Path) -> None:
        """将 base64 data URI 解码并保存为文件"""
        import base64

        # 格式: data:image/png;base64,<data>
        try:
            header, b64_data = data_uri.split(",", 1)
            image_bytes = base64.b64decode(b64_data)
            file_path.write_bytes(image_bytes)
        except Exception as e:
            raise ImageGenError(f"保存 base64 图片失败: {e}")
