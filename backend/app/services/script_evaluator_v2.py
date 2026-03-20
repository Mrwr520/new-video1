"""剧本评审器 v2

多维度评审剧本并生成改进建议。通过 LLM 对剧本进行五个维度的评分：
内容质量、结构完整性、创意性、热点相关性、技巧运用。

需求：2.1, 2.2, 2.3, 2.4
"""

import json
import logging
from typing import List

from app.schemas.script_optimization import (
    DimensionScores,
    DimensionWeights,
    EvaluationResult,
    Hotspot,
    Technique,
)
from app.services.llm_service import LLMService, _extract_json_from_text, LLMServiceError

logger = logging.getLogger(__name__)

# LLM 评审 prompt 模板
EVALUATION_SYSTEM_PROMPT = (
    "你是一个专业的剧本评审专家。你的任务是从多个维度评审给定的剧本。\n"
    "你必须严格以 JSON 对象格式输出评审结果，不要包含任何其他文字说明。\n"
    "JSON 对象必须包含以下字段：\n"
    '  - "content_quality": 内容质量评分 (0-10)\n'
    '  - "structure": 结构完整性评分 (0-10)\n'
    '  - "creativity": 创意性评分 (0-10)\n'
    '  - "hotspot_relevance": 热点相关性评分 (0-10)\n'
    '  - "technique_application": 技巧运用评分 (0-10)\n'
    '  - "reasoning": 各维度评分理由（字符串）\n'
    "\n输出示例：\n"
    '{"content_quality": 7.5, "structure": 8.0, "creativity": 6.5, '
    '"hotspot_relevance": 5.0, "technique_application": 7.0, '
    '"reasoning": "内容质量较好，结构完整，但创意性和热点相关性有待提升"}'
)


def _build_evaluation_messages(
    script: str,
    hotspots: List[Hotspot],
    techniques: List[Technique],
) -> list[dict]:
    """构建评审的 chat messages。"""
    hotspot_text = ""
    if hotspots:
        hotspot_items = "\n".join(
            f"- {h.title}: {h.description}" for h in hotspots
        )
        hotspot_text = f"\n--- 当前热点信息 ---\n{hotspot_items}\n"

    technique_text = ""
    if techniques:
        technique_items = "\n".join(
            f"- {t.name}: {t.description}" for t in techniques
        )
        technique_text = f"\n--- 推荐创作技巧 ---\n{technique_items}\n"

    user_prompt = (
        "请从以下五个维度评审这个剧本：\n"
        "1. 内容质量：剧本内容是否丰富、准确、有深度\n"
        "2. 结构完整性：剧本结构是否完整、逻辑是否清晰\n"
        "3. 创意性：剧本是否有创新点和吸引力\n"
        "4. 热点相关性：剧本是否与当前热点话题相关\n"
        "5. 技巧运用：剧本是否运用了专业的创作技巧\n"
        f"{hotspot_text}{technique_text}"
        f"\n--- 以下是需要评审的剧本 ---\n\n{script}"
    )

    return [
        {"role": "system", "content": EVALUATION_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def _parse_evaluation_response(raw_text: str) -> dict:
    """解析 LLM 返回的评审 JSON 数据。"""
    json_str = _extract_json_from_text(raw_text)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise LLMServiceError(f"评审结果 JSON 解析失败: {e}")

    if not isinstance(data, dict):
        raise LLMServiceError("评审结果格式错误：期望 JSON 对象")

    required_fields = [
        "content_quality", "structure", "creativity",
        "hotspot_relevance", "technique_application",
    ]
    for field in required_fields:
        if field not in data:
            raise LLMServiceError(f"评审结果缺少字段: {field}")

    return data


def _clamp_score(value: float) -> float:
    """将分数限制在 0-10 范围内。"""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 5.0  # 解析失败时返回中间值
    return max(0.0, min(10.0, score))


class ScriptEvaluator:
    """多维度剧本评审器 v2。

    通过 LLM 对剧本进行五个维度的评分，计算加权平均总分，
    并生成改进建议。
    """

    def __init__(
        self,
        llm_service: LLMService,
        weights: DimensionWeights,
    ):
        """初始化剧本评审器。

        Args:
            llm_service: LLM 服务实例
            weights: 各维度评审权重
        """
        self.llm_service = llm_service
        self.weights = weights

    async def evaluate_script(
        self,
        script: str,
        hotspots: List[Hotspot],
        techniques: List[Technique],
    ) -> EvaluationResult:
        """评审剧本，返回多维度评分和改进建议。

        Args:
            script: 剧本内容
            hotspots: 热点信息列表
            techniques: 技巧信息列表

        Returns:
            EvaluationResult: 包含总分、各维度分数和改进建议

        Raises:
            LLMServiceError: LLM 调用或解析失败
        """
        messages = _build_evaluation_messages(script, hotspots, techniques)
        logger.info(
            "Starting script evaluation (script_length=%d, hotspots=%d, techniques=%d)",
            len(script),
            len(hotspots),
            len(techniques),
        )
        raw_response = await self.llm_service._call_llm(messages)
        parsed = _parse_evaluation_response(raw_response)

        dimension_scores = DimensionScores(
            content_quality=_clamp_score(parsed["content_quality"]),
            structure=_clamp_score(parsed["structure"]),
            creativity=_clamp_score(parsed["creativity"]),
            hotspot_relevance=_clamp_score(parsed["hotspot_relevance"]),
            technique_application=_clamp_score(parsed["technique_application"]),
        )

        total_score = self._calculate_total_score(dimension_scores)
        suggestions = self._generate_suggestions(
            script, dimension_scores, hotspots, techniques
        )

        logger.info(
            "Script evaluation completed: total_score=%.2f "
            "(content=%.2f, structure=%.2f, creativity=%.2f, "
            "hotspot=%.2f, technique=%.2f), suggestions=%d",
            total_score,
            dimension_scores.content_quality,
            dimension_scores.structure,
            dimension_scores.creativity,
            dimension_scores.hotspot_relevance,
            dimension_scores.technique_application,
            len(suggestions),
        )

        return EvaluationResult(
            total_score=total_score,
            dimension_scores=dimension_scores,
            suggestions=suggestions,
        )

    def _calculate_total_score(self, dimension_scores: DimensionScores) -> float:
        """计算加权平均总分。

        使用 DimensionWeights.calculate_total_score 进行计算，
        结果四舍五入到两位小数。

        Args:
            dimension_scores: 各维度分数

        Returns:
            加权平均总分 (0-10)
        """
        return round(self.weights.calculate_total_score(dimension_scores), 2)

    def _generate_suggestions(
        self,
        script: str,
        dimension_scores: DimensionScores,
        hotspots: List[Hotspot],
        techniques: List[Technique],
    ) -> List[str]:
        """根据评分结果生成改进建议。

        对低于 7 分的维度生成针对性建议，并结合热点和技巧信息
        提供具体的改进方向。

        Args:
            script: 剧本内容
            dimension_scores: 各维度分数
            hotspots: 热点信息列表
            techniques: 技巧信息列表

        Returns:
            改进建议列表，至少包含一条建议
        """
        suggestions: List[str] = []
        threshold = 7.0

        if dimension_scores.content_quality < threshold:
            suggestions.append(
                f"内容质量评分为 {dimension_scores.content_quality}，"
                "建议丰富剧本内容，增加细节描写和情感表达。"
            )

        if dimension_scores.structure < threshold:
            suggestions.append(
                f"结构完整性评分为 {dimension_scores.structure}，"
                "建议优化剧本结构，确保开头、发展、高潮、结尾完整。"
            )

        if dimension_scores.creativity < threshold:
            suggestions.append(
                f"创意性评分为 {dimension_scores.creativity}，"
                "建议增加创新元素，尝试独特的叙事角度或表现手法。"
            )

        if dimension_scores.hotspot_relevance < threshold:
            if hotspots:
                hotspot_titles = "、".join(h.title for h in hotspots[:3])
                suggestions.append(
                    f"热点相关性评分为 {dimension_scores.hotspot_relevance}，"
                    f"建议融入当前热点话题：{hotspot_titles}。"
                )
            else:
                suggestions.append(
                    f"热点相关性评分为 {dimension_scores.hotspot_relevance}，"
                    "建议关注当前热门话题，增强剧本的时效性。"
                )

        if dimension_scores.technique_application < threshold:
            if techniques:
                technique_names = "、".join(t.name for t in techniques[:3])
                suggestions.append(
                    f"技巧运用评分为 {dimension_scores.technique_application}，"
                    f"建议运用以下创作技巧：{technique_names}。"
                )
            else:
                suggestions.append(
                    f"技巧运用评分为 {dimension_scores.technique_application}，"
                    "建议学习和运用更多专业创作技巧。"
                )

        # 确保至少有一条建议（需求 2.4）
        if not suggestions:
            suggestions.append("剧本整体质量良好，可以继续优化细节以追求更高品质。")

        return suggestions
