"""剧本生成器 (Script Generator)

调用 LLM API 生成和优化剧本。支持初始生成和基于评审反馈的迭代重新生成。
集成现有的 LLMService，包含错误处理和重试机制。

需求：1.1, 1.3, 7.4
"""

import asyncio
import logging
from typing import List

from app.schemas.script_optimization import (
    EvaluationResult,
    Hotspot,
    Technique,
)
from app.services.llm_service import LLMService, LLMServiceError

logger = logging.getLogger(__name__)

# 默认重试次数（在 LLMService 自身重试之上的额外重试）
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BASE_DELAY = 1.0


class ScriptGenerationError(LLMServiceError):
    """剧本生成专用异常"""

    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message, code="SCRIPT_GENERATION_ERROR", retryable=retryable)


def _build_initial_prompt_messages(prompt: str) -> list[dict]:
    """构建初始剧本生成的 chat messages。"""
    system_prompt = (
        "你是一个专业的视频剧本编写助手。你的任务是根据用户的描述生成高质量的视频剧本。\n"
        "剧本应该包含以下要素：\n"
        "1. 清晰的故事结构（开头、发展、高潮、结尾）\n"
        "2. 生动的场景描述\n"
        "3. 自然的对话和旁白\n"
        "4. 明确的镜头指示\n"
        "5. 吸引观众的创意元素\n\n"
        "请直接输出剧本内容，不要包含额外的说明或标记。"
    )
    user_prompt = f"请根据以下描述生成一个视频剧本：\n\n{prompt}"
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _build_regeneration_messages(
    previous_script: str,
    evaluation: EvaluationResult,
    hotspots: List[Hotspot],
    techniques: List[Technique],
) -> list[dict]:
    """构建重新生成剧本的 chat messages。"""
    system_prompt = (
        "你是一个专业的视频剧本优化助手。你的任务是根据评审反馈优化现有剧本。\n"
        "请仔细分析评审意见，结合提供的热点信息和创作技巧，生成改进后的剧本。\n"
        "优化时请注意：\n"
        "1. 保留原剧本的核心创意和故事框架\n"
        "2. 针对评审中指出的不足进行改进\n"
        "3. 融入相关热点元素提升时效性\n"
        "4. 运用推荐的创作技巧提升专业性\n\n"
        "请直接输出优化后的完整剧本，不要包含额外的说明或标记。"
    )
    user_prompt = _build_regeneration_prompt(
        previous_script, evaluation, hotspots, techniques
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _build_regeneration_prompt(
    previous_script: str,
    evaluation: EvaluationResult,
    hotspots: List[Hotspot],
    techniques: List[Technique],
) -> str:
    """构建重新生成的用户提示词。"""
    parts: list[str] = []

    # 原始剧本
    parts.append("--- 当前剧本 ---")
    parts.append(previous_script)

    # 评审结果
    parts.append("\n--- 评审结果 ---")
    parts.append(f"总分：{evaluation.total_score}/10")
    ds = evaluation.dimension_scores
    parts.append(f"内容质量：{ds.content_quality}/10")
    parts.append(f"结构完整性：{ds.structure}/10")
    parts.append(f"创意性：{ds.creativity}/10")
    parts.append(f"热点相关性：{ds.hotspot_relevance}/10")
    parts.append(f"技巧运用：{ds.technique_application}/10")

    # 改进建议
    if evaluation.suggestions:
        parts.append("\n--- 改进建议 ---")
        for i, suggestion in enumerate(evaluation.suggestions, 1):
            parts.append(f"{i}. {suggestion}")

    # 热点信息
    if hotspots:
        parts.append("\n--- 当前热点信息（请适当融入） ---")
        for hotspot in hotspots:
            parts.append(f"- {hotspot.title}：{hotspot.description}")

    # 创作技巧
    if techniques:
        parts.append("\n--- 推荐创作技巧（请适当运用） ---")
        for technique in techniques:
            parts.append(f"- {technique.name}：{technique.description}")
            if technique.example:
                parts.append(f"  示例：{technique.example}")

    parts.append("\n请根据以上评审反馈和参考信息，优化并重新生成完整的剧本。")

    return "\n".join(parts)


class ScriptGenerator:
    """剧本生成器，调用 LLM API 生成和优化剧本。

    通过 LLMService 与 LLM API 交互，支持：
    - 根据用户提示词生成初始剧本
    - 根据评审反馈、热点和技巧重新生成优化剧本
    - 错误处理和重试机制
    """

    def __init__(
        self,
        llm_service: LLMService,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_base_delay: float = DEFAULT_RETRY_BASE_DELAY,
    ):
        self.llm_service = llm_service
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay

    async def generate_initial_script(self, prompt: str) -> str:
        """生成初始剧本。

        Args:
            prompt: 用户输入的剧本提示词

        Returns:
            生成的剧本内容

        Raises:
            ScriptGenerationError: 生成失败（重试耗尽后）
        """
        if not prompt or not prompt.strip():
            raise ScriptGenerationError("剧本提示词不能为空")

        logger.info("Starting initial script generation")
        messages = _build_initial_prompt_messages(prompt.strip())
        return await self._call_with_retry(messages, "初始剧本生成")

    async def regenerate_script(
        self,
        previous_script: str,
        evaluation: EvaluationResult,
        hotspots: List[Hotspot],
        techniques: List[Technique],
    ) -> str:
        """根据评审结果重新生成剧本。

        Args:
            previous_script: 上一版本剧本
            evaluation: 评审结果
            hotspots: 热点信息
            techniques: 技巧建议

        Returns:
            优化后的剧本内容

        Raises:
            ScriptGenerationError: 生成失败（重试耗尽后）
        """
        if not previous_script or not previous_script.strip():
            raise ScriptGenerationError("上一版本剧本不能为空")

        logger.info("Starting script regeneration based on evaluation feedback")
        messages = _build_regeneration_messages(
            previous_script, evaluation, hotspots, techniques
        )
        return await self._call_with_retry(messages, "剧本重新生成")

    async def _call_with_retry(self, messages: list[dict], operation: str) -> str:
        """带重试的 LLM 调用。

        LLMService 自身已有重试机制，此处提供额外的应用层重试，
        用于处理 LLMService 重试耗尽后仍可恢复的场景。

        Args:
            messages: chat messages
            operation: 操作描述（用于日志）

        Returns:
            LLM 生成的文本

        Raises:
            ScriptGenerationError: 所有重试耗尽
        """
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                result = await self.llm_service._call_llm(messages)
                if not result or not result.strip():
                    raise ScriptGenerationError(
                        f"{operation}返回空内容", retryable=True
                    )
                logger.info("%s成功 (尝试 %d/%d)", operation, attempt + 1, self.max_retries + 1)
                return result.strip()
            except LLMServiceError as e:
                last_error = e
                if not e.retryable or attempt >= self.max_retries:
                    logger.error(
                        "%s失败 (尝试 %d/%d): %s",
                        operation, attempt + 1, self.max_retries + 1, e,
                    )
                    break
                delay = self.retry_base_delay * (2 ** attempt)
                logger.warning(
                    "%s失败，%0.1f 秒后重试 (尝试 %d/%d): %s",
                    operation, delay, attempt + 1, self.max_retries + 1, e,
                )
                await asyncio.sleep(delay)
            except Exception as e:
                last_error = e
                logger.error("%s发生意外错误: %s", operation, e)
                break

        raise ScriptGenerationError(
            f"{operation}失败，已耗尽重试次数: {last_error}"
        )
