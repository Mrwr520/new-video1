"""技巧搜索器

搜索剧本创作技巧，根据剧本类型和缺陷构建查询并调用搜索 API。
搜索失败时使用默认技巧库作为降级策略。

需求：4.1, 4.2, 4.3, 4.4
"""

import logging
from dataclasses import dataclass
from typing import Dict, List

from app.schemas.script_optimization import Technique
from app.services.search_api_client import SearchAPIClient

logger = logging.getLogger(__name__)


@dataclass
class TechniqueSearchConfig:
    """技巧搜索配置"""

    search_limit: int = 10
    search_type: str = "web"
    min_results: int = 3


# Built-in default techniques library, keyed by script type.
# Used as fallback when search API is unavailable (需求 4.4).
DEFAULT_TECHNIQUES: Dict[str, List[Technique]] = {
    "短视频": [
        Technique(
            name="黄金三秒法则",
            description="在视频开头三秒内抓住观众注意力，使用悬念、冲突或视觉冲击",
            example="开场直接展示最精彩的画面或抛出引人入胜的问题",
            category="开场技巧",
            source="默认技巧库",
        ),
        Technique(
            name="情绪曲线设计",
            description="通过起承转合设计观众的情绪变化，制造高潮和反转",
            example="先铺垫日常场景，突然引入意外事件，最后给出温暖结局",
            category="叙事技巧",
            source="默认技巧库",
        ),
        Technique(
            name="节奏把控",
            description="控制镜头切换频率和信息密度，保持观众注意力",
            example="高潮部分加快剪辑节奏，情感部分放慢节奏留白",
            category="节奏技巧",
            source="默认技巧库",
        ),
    ],
    "广告": [
        Technique(
            name="痛点切入法",
            description="从目标用户的痛点出发，引发共鸣后提供解决方案",
            example="先展示用户面临的困扰场景，再自然引出产品作为解决方案",
            category="营销技巧",
            source="默认技巧库",
        ),
        Technique(
            name="故事化营销",
            description="将产品融入故事情节中，避免硬性推销",
            example="通过一个小故事展示产品如何改变主角的生活",
            category="叙事技巧",
            source="默认技巧库",
        ),
        Technique(
            name="行动号召设计",
            description="在结尾设计明确的行动号召，引导观众下一步操作",
            example="使用限时优惠、扫码领取等方式促进转化",
            category="转化技巧",
            source="默认技巧库",
        ),
    ],
    "纪录片": [
        Technique(
            name="真实感营造",
            description="通过真实素材和采访增强纪录片的可信度和感染力",
            example="穿插真实人物采访和现场画面，避免过度修饰",
            category="纪实技巧",
            source="默认技巧库",
        ),
        Technique(
            name="悬念叙事",
            description="在纪录片中设置悬念，引导观众持续观看",
            example="开头抛出核心问题，逐步揭示答案",
            category="叙事技巧",
            source="默认技巧库",
        ),
        Technique(
            name="数据可视化",
            description="使用图表和动画将复杂数据直观呈现",
            example="用动态图表展示趋势变化，配合旁白解读",
            category="表现技巧",
            source="默认技巧库",
        ),
    ],
}

# Generic fallback techniques applicable to any script type
GENERIC_TECHNIQUES: List[Technique] = [
    Technique(
        name="冲突设置",
        description="在剧本中设置核心冲突，驱动情节发展和观众兴趣",
        example="主角面临两难选择，必须在有限时间内做出决定",
        category="叙事技巧",
        source="默认技巧库",
    ),
    Technique(
        name="角色塑造",
        description="通过细节和行为塑造立体的角色形象",
        example="通过角色的小习惯和口头禅展现性格特点",
        category="角色技巧",
        source="默认技巧库",
    ),
    Technique(
        name="视觉叙事",
        description="用画面而非对白传递信息和情感",
        example="通过环境变化和角色表情推动剧情，减少旁白依赖",
        category="视觉技巧",
        source="默认技巧库",
    ),
]


class TechniqueSearcher:
    """技巧搜索器

    根据剧本类型和缺陷搜索创作技巧。
    搜索失败时自动降级到默认技巧库。
    """

    def __init__(
        self,
        search_api_client: SearchAPIClient,
        fallback_techniques: List[Technique] | None = None,
        config: TechniqueSearchConfig | None = None,
    ):
        self._client = search_api_client
        self._fallback_techniques = fallback_techniques or []
        self._config = config or TechniqueSearchConfig()

    async def search_techniques(
        self,
        script: str,
        script_type: str,
        weaknesses: List[str],
    ) -> List[Technique]:
        """搜索创作技巧

        Args:
            script: 剧本内容
            script_type: 剧本类型（如 短视频、广告、纪录片）
            weaknesses: 剧本缺陷列表

        Returns:
            技巧列表；搜索失败时返回默认技巧库内容
        """
        try:
            query = self._build_search_query(script_type, weaknesses)
            if not query:
                logger.warning("Empty search query built; using fallback techniques")
                return self._get_fallback_techniques(script_type)

            logger.info(
                "Starting technique search (script_type=%s, weaknesses=%s, query=%s)",
                script_type,
                weaknesses,
                query,
            )
            raw_results = await self._call_search_api(query)
            techniques = self._parse_technique_results(raw_results)
            logger.info(
                "Technique search completed: %d results found",
                len(techniques),
            )

            if len(techniques) < self._config.min_results:
                logger.info(
                    "Search returned %d techniques (< %d minimum); "
                    "supplementing with fallback",
                    len(techniques),
                    self._config.min_results,
                )
                fallback = self._get_fallback_techniques(script_type)
                logger.info(
                    "Using %d fallback techniques to supplement results",
                    len(fallback),
                )
                # Add fallback techniques that aren't duplicates
                seen_names = {t.name for t in techniques}
                for t in fallback:
                    if t.name not in seen_names:
                        techniques.append(t)
                        seen_names.add(t.name)

            return techniques
        except Exception as e:
            logger.error("Technique search failed: %s", e, exc_info=True)
            return self._get_fallback_techniques(script_type)

    def _build_search_query(
        self,
        script_type: str,
        weaknesses: List[str],
    ) -> str:
        """根据剧本类型和缺陷构建搜索查询

        Args:
            script_type: 剧本类型
            weaknesses: 剧本缺陷列表

        Returns:
            搜索查询字符串
        """
        parts: List[str] = []

        if script_type and script_type.strip():
            parts.append(f"{script_type.strip()}剧本创作技巧")

        for weakness in weaknesses:
            w = weakness.strip()
            if w:
                parts.append(f"{w}改进方法")

        if not parts:
            return ""

        return " ".join(parts)

    async def _call_search_api(self, query: str) -> List[Dict]:
        """调用搜索 API

        Args:
            query: 搜索查询字符串

        Returns:
            原始搜索结果列表
        """
        return await self._client.search(
            query=query,
            search_type=self._config.search_type,
            limit=self._config.search_limit,
        )

    def _parse_technique_results(
        self, raw_results: List[Dict]
    ) -> List[Technique]:
        """解析搜索结果为 Technique 对象

        Args:
            raw_results: 原始搜索结果字典列表

        Returns:
            Technique 对象列表
        """
        techniques: List[Technique] = []
        for item in raw_results:
            try:
                name = item.get("title", item.get("name", ""))
                description = item.get("description", item.get("snippet", ""))
                example = item.get("example", "")
                category = item.get("category", "搜索结果")
                source = item.get("source", item.get("url", "search"))

                if not name:
                    continue

                techniques.append(
                    Technique(
                        name=name,
                        description=description,
                        example=example,
                        category=category,
                        source=source,
                    )
                )
            except Exception as e:
                logger.warning("Failed to parse technique result %s: %s", item, e)
                continue

        return techniques

    def _get_fallback_techniques(self, script_type: str) -> List[Technique]:
        """获取降级技巧库内容

        优先级：自定义 fallback > 按类型默认库 > 通用默认库

        Args:
            script_type: 剧本类型

        Returns:
            默认技巧列表（至少 3 条）
        """
        # 1. Custom fallback techniques provided at init
        if self._fallback_techniques:
            return list(self._fallback_techniques)

        # 2. Type-specific default techniques
        type_key = script_type.strip() if script_type else ""
        if type_key in DEFAULT_TECHNIQUES:
            return list(DEFAULT_TECHNIQUES[type_key])

        # 3. Generic fallback
        return list(GENERIC_TECHNIQUES)
