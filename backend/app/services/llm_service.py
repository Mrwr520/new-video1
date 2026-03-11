"""LLM 服务

封装 OpenAI 兼容 API 调用，提供角色提取和分镜脚本生成功能。
支持通过依赖注入替换 HTTP 客户端，便于测试。
"""

import json
import uuid
import logging
from typing import Any, Optional, Protocol

import httpx

from app.models.character import Character
from app.models.scene import StoryboardScene
from app.services.template_service import ContentTemplate

logger = logging.getLogger(__name__)


class LLMClientProtocol(Protocol):
    """LLM HTTP 客户端协议，便于测试时替换"""

    async def post(self, url: str, **kwargs: Any) -> httpx.Response: ...


class LLMServiceError(Exception):
    """LLM 服务基础异常"""

    def __init__(self, message: str, code: str = "LLM_ERROR", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class LLMParseError(LLMServiceError):
    """LLM 响应解析错误"""

    def __init__(self, message: str):
        super().__init__(message, code="LLM_PARSE_ERROR", retryable=True)


class LLMTimeoutError(LLMServiceError):
    """LLM API 超时错误"""

    def __init__(self, message: str = "LLM API 请求超时"):
        super().__init__(message, code="LLM_TIMEOUT", retryable=True)


class LLMApiError(LLMServiceError):
    """LLM API 调用错误"""

    def __init__(self, message: str, status_code: int = 0):
        retryable = status_code >= 500 or status_code == 429
        super().__init__(message, code="LLM_API_ERROR", retryable=retryable)
        self.status_code = status_code


# ============================================================
# Prompt 构建辅助函数
# ============================================================

def _build_character_extraction_messages(text: str, template: ContentTemplate) -> list[dict]:
    """构建角色提取的 chat messages"""
    system_prompt = (
        "你是一个专业的文本分析助手。你的任务是从给定文本中提取角色信息。\n"
        "你必须严格以 JSON 数组格式输出结果，不要包含任何其他文字说明。\n"
        "每个角色对象必须包含以下字段：\n"
        '  - "name": 角色名称（字符串）\n'
        '  - "appearance": 外貌描述（字符串）\n'
        '  - "personality": 性格特征（字符串）\n'
        '  - "background": 背景信息（字符串）\n'
        '  - "image_prompt": 用于 AI 图像生成的英文 prompt（字符串）\n'
        "\n输出示例：\n"
        '[{"name":"张三","appearance":"黑色短发，身材高大","personality":"沉稳冷静","background":"退役军人","image_prompt":"a tall man with short black hair, calm expression, military bearing"}]'
    )

    user_prompt = (
        f"{template.character_extraction_prompt}\n\n"
        f"--- 以下是需要分析的文本 ---\n\n{text}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _build_storyboard_messages(
    text: str, characters: list[Character], template: ContentTemplate
) -> list[dict]:
    """构建分镜脚本生成的 chat messages"""
    # 将角色信息序列化为文本
    char_descriptions = "\n".join(
        f"- {c.name}：{c.appearance}，{c.personality}" for c in characters
    )

    system_prompt = (
        "你是一个专业的分镜脚本编写助手。你的任务是将文本拆解为有序的分镜脚本。\n"
        "你必须严格以 JSON 数组格式输出结果，不要包含任何其他文字说明。\n"
        "每个分镜对象必须包含以下字段：\n"
        '  - "scene_description": 场景的视觉描述（字符串）\n'
        '  - "dialogue": 该场景的台词或旁白（字符串）\n'
        '  - "camera_direction": 镜头指示，如远景、近景、特写（字符串）\n'
        '  - "image_prompt": 用于 AI 图像生成的英文 prompt（字符串）\n'
        '  - "motion_prompt": 用于视频生成的运动描述英文 prompt（字符串）\n'
        "\n输出示例：\n"
        '[{"scene_description":"夕阳下的城市天际线","dialogue":"故事从这里开始...","camera_direction":"远景，缓慢推进","image_prompt":"city skyline at sunset, golden hour","motion_prompt":"slow zoom in, gentle camera movement"}]'
    )

    user_prompt = (
        f"{template.storyboard_prompt}\n\n"
        f"--- 角色信息 ---\n{char_descriptions}\n\n"
        f"--- 以下是需要拆解的文本 ---\n\n{text}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


# ============================================================
# JSON 解析辅助函数
# ============================================================

def _extract_json_from_text(text: str) -> str:
    """从 LLM 响应文本中提取 JSON 内容。

    LLM 有时会在 JSON 前后添加 markdown 代码块标记或额外文字，
    此函数尝试提取纯 JSON 部分。
    """
    text = text.strip()

    # 尝试提取 ```json ... ``` 代码块
    if "```" in text:
        # 找到第一个 ``` 后的内容
        parts = text.split("```")
        for part in parts:
            cleaned = part.strip()
            # 去掉可能的语言标记（如 json）
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith("[") or cleaned.startswith("{"):
                return cleaned

    # 尝试找到 JSON 数组的起止位置
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    # 尝试找到 JSON 对象的起止位置
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    return text


def parse_characters_response(raw_text: str) -> list[dict]:
    """解析 LLM 返回的角色 JSON 数据"""
    json_str = _extract_json_from_text(raw_text)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise LLMParseError(f"角色提取结果 JSON 解析失败: {e}")

    if isinstance(data, dict):
        # 有时 LLM 返回 {"characters": [...]}
        for key in ("characters", "roles", "data", "result"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
        else:
            data = [data]

    if not isinstance(data, list):
        raise LLMParseError("角色提取结果格式错误：期望 JSON 数组")

    return data


def parse_storyboard_response(raw_text: str) -> list[dict]:
    """解析 LLM 返回的分镜 JSON 数据"""
    json_str = _extract_json_from_text(raw_text)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise LLMParseError(f"分镜脚本 JSON 解析失败: {e}")

    if isinstance(data, dict):
        for key in ("scenes", "storyboard", "data", "result"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
        else:
            data = [data]

    if not isinstance(data, list):
        raise LLMParseError("分镜脚本结果格式错误：期望 JSON 数组")

    return data


# ============================================================
# LLM 服务主类
# ============================================================

class LLMService:
    """封装 LLM API 调用，支持 OpenAI 兼容接口。

    通过构造函数注入 HTTP 客户端，便于测试时 mock。
    """

    def __init__(
        self,
        api_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "gpt-4o-mini",
        timeout: float = 120.0,
        max_retries: int = 3,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        # 允许注入自定义客户端（测试用）
        self._client = client
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        """获取 HTTP 客户端，懒初始化"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
            self._owns_client = True
        return self._client

    async def close(self) -> None:
        """关闭 HTTP 客户端"""
        if self._client and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def _call_llm(self, messages: list[dict]) -> str:
        """调用 LLM API，返回助手回复文本。

        包含重试逻辑：超时和 5xx 错误自动重试。
        """
        client = await self._get_client()
        url = f"{self.api_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
        }

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                response = await client.post(url, json=payload, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    return self._extract_content(data)

                # 可重试的状态码
                if response.status_code >= 500 or response.status_code == 429:
                    last_error = LLMApiError(
                        f"LLM API 返回错误状态码: {response.status_code}",
                        status_code=response.status_code,
                    )
                    logger.warning(
                        "LLM API 错误 (尝试 %d/%d): %s",
                        attempt + 1, self.max_retries, last_error,
                    )
                    continue

                # 不可重试的客户端错误
                raise LLMApiError(
                    f"LLM API 返回错误: {response.status_code} - {response.text}",
                    status_code=response.status_code,
                )

            except httpx.TimeoutException:
                last_error = LLMTimeoutError()
                logger.warning(
                    "LLM API 超时 (尝试 %d/%d)", attempt + 1, self.max_retries,
                )
                continue
            except (LLMApiError, LLMTimeoutError):
                raise
            except LLMServiceError:
                raise
            except Exception as e:
                raise LLMServiceError(f"LLM API 调用异常: {e}")

        # 所有重试都失败
        if last_error:
            raise last_error
        raise LLMServiceError("LLM API 调用失败，已耗尽重试次数")

    @staticmethod
    def _extract_content(response_data: dict) -> str:
        """从 OpenAI 兼容响应中提取助手回复内容"""
        try:
            choices = response_data.get("choices", [])
            if not choices:
                raise LLMParseError("LLM 响应中没有 choices")
            message = choices[0].get("message", {})
            content = message.get("content", "")
            if not content:
                raise LLMParseError("LLM 响应内容为空")
            return content
        except (KeyError, IndexError, TypeError) as e:
            raise LLMParseError(f"LLM 响应结构异常: {e}")

    async def extract_characters(
        self, text: str, template: ContentTemplate
    ) -> list[Character]:
        """从文本中提取角色信息。

        Args:
            text: 输入文本
            template: 内容模板，包含角色提取 prompt 策略

        Returns:
            提取到的角色列表

        Raises:
            LLMServiceError: LLM 调用或解析失败
        """
        messages = _build_character_extraction_messages(text, template)
        raw_response = await self._call_llm(messages)
        raw_characters = parse_characters_response(raw_response)

        characters = []
        for item in raw_characters:
            char = Character(
                id=f"char-{uuid.uuid4().hex[:8]}",
                name=item.get("name", "未知角色"),
                appearance=item.get("appearance", ""),
                personality=item.get("personality", ""),
                background=item.get("background", ""),
                image_prompt=item.get("image_prompt", ""),
            )
            characters.append(char)

        return characters

    async def generate_storyboard(
        self, text: str, characters: list[Character], template: ContentTemplate
    ) -> list[StoryboardScene]:
        """将文本拆解为分镜脚本。

        Args:
            text: 输入文本
            characters: 已确认的角色列表
            template: 内容模板，包含分镜生成 prompt 策略

        Returns:
            分镜场景列表

        Raises:
            LLMServiceError: LLM 调用或解析失败
        """
        messages = _build_storyboard_messages(text, characters, template)
        raw_response = await self._call_llm(messages)
        raw_scenes = parse_storyboard_response(raw_response)

        scenes = []
        for idx, item in enumerate(raw_scenes):
            scene = StoryboardScene(
                id=f"scene-{uuid.uuid4().hex[:8]}",
                order=idx + 1,
                scene_description=item.get("scene_description", ""),
                dialogue=item.get("dialogue", ""),
                camera_direction=item.get("camera_direction", ""),
                image_prompt=item.get("image_prompt", ""),
                motion_prompt=item.get("motion_prompt", ""),
            )
            scenes.append(scene)

        return scenes
