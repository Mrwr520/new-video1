"""热点搜索器

搜索网络实时热点，根据剧本主题提取关键词并调用搜索 API。

需求：3.1, 3.2, 3.3, 3.4
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List

from app.schemas.script_optimization import Hotspot
from app.services.search_api_client import SearchAPIClient

logger = logging.getLogger(__name__)

# Common Chinese stop words and filler words to filter out during keyword extraction
CHINESE_STOP_WORDS = frozenset(
    [
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
        "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
        "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "被",
        "从", "把", "让", "用", "对", "为", "与", "而", "但", "如果", "因为",
        "所以", "可以", "这个", "那个", "什么", "怎么", "哪", "吗", "呢", "吧",
        "啊", "呀", "哦", "嗯", "哈", "嘛", "么", "之", "其", "或", "及",
        "等", "能", "将", "已", "于", "由", "此", "则", "以", "并", "还",
        "又", "更", "最", "每", "各", "该", "某", "这些", "那些",
    ]
)

# Common English stop words
ENGLISH_STOP_WORDS = frozenset(
    [
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "shall", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "as", "into", "through", "during",
        "before", "after", "above", "below", "between", "and", "but", "or",
        "not", "no", "so", "if", "then", "than", "too", "very", "just",
        "about", "up", "out", "it", "its", "this", "that", "these", "those",
        "i", "you", "he", "she", "we", "they", "me", "him", "her", "us",
        "them", "my", "your", "his", "our", "their", "what", "which", "who",
    ]
)


@dataclass
class SearchConfig:
    """搜索配置"""

    max_keywords: int = 5
    search_limit: int = 10
    min_keyword_length: int = 2
    search_type: str = "news"


class HotspotSearcher:
    """热点搜索器

    根据剧本内容和主题搜索网络实时热点信息。
    """

    def __init__(
        self,
        search_api_client: SearchAPIClient,
        config: SearchConfig | None = None,
    ):
        self._client = search_api_client
        self._config = config or SearchConfig()

    async def search_hotspots(
        self, script: str, topic: str
    ) -> List[Hotspot]:
        """搜索相关热点

        Args:
            script: 剧本内容
            topic: 剧本主题

        Returns:
            热点列表；搜索失败时返回空列表
        """
        try:
            keywords = self._extract_keywords(script, topic)
            if not keywords:
                logger.warning("No keywords extracted from script and topic")
                return []

            logger.info(
                "Starting hotspot search (topic=%s, keywords=%s)",
                topic,
                keywords,
            )
            raw_results = await self._call_search_api(keywords)
            hotspots = self._parse_hotspot_results(raw_results)
            logger.info(
                "Hotspot search completed: %d results found",
                len(hotspots),
            )
            return hotspots
        except Exception as e:
            logger.error("Hotspot search failed: %s", e, exc_info=True)
            return []

    def _extract_keywords(self, script: str, topic: str) -> List[str]:
        """从剧本和主题中提取关键词

        Uses simple text analysis: splits text, filters stop words and
        short tokens, then returns the most frequent terms.

        Args:
            script: 剧本内容
            topic: 剧本主题

        Returns:
            关键词列表
        """
        # Topic words get priority — always included first
        topic_words = self._tokenize_and_filter(topic)

        # Extract words from script body
        script_words = self._tokenize_and_filter(script)

        # Count frequency of script words
        freq: Dict[str, int] = {}
        for w in script_words:
            freq[w] = freq.get(w, 0) + 1

        # Sort script words by frequency (descending)
        sorted_script_words = sorted(freq.keys(), key=lambda w: freq[w], reverse=True)

        # Build final keyword list: topic words first, then top script words
        seen: set = set()
        keywords: List[str] = []

        for w in topic_words:
            lower = w.lower()
            if lower not in seen:
                seen.add(lower)
                keywords.append(w)

        for w in sorted_script_words:
            lower = w.lower()
            if lower not in seen:
                seen.add(lower)
                keywords.append(w)
            if len(keywords) >= self._config.max_keywords:
                break

        return keywords[: self._config.max_keywords]

    def _tokenize_and_filter(self, text: str) -> List[str]:
        """Tokenize text and filter out stop words and short tokens."""
        if not text:
            return []

        # Split on whitespace and common punctuation
        tokens = re.split(r"[\s,;.!?，。！？；：、\n\r\t]+", text)

        result: List[str] = []
        for token in tokens:
            token = token.strip()
            if not token:
                continue
            if len(token) < self._config.min_keyword_length:
                continue
            if token.lower() in ENGLISH_STOP_WORDS:
                continue
            if token in CHINESE_STOP_WORDS:
                continue
            result.append(token)

        return result

    async def _call_search_api(self, keywords: List[str]) -> List[Dict]:
        """调用搜索 API

        Joins keywords into a single query string and calls the search client.

        Args:
            keywords: 关键词列表

        Returns:
            原始搜索结果列表
        """
        query = " ".join(keywords)
        return await self._client.search(
            query=query,
            search_type=self._config.search_type,
            limit=self._config.search_limit,
        )

    def _parse_hotspot_results(
        self, raw_results: List[Dict]
    ) -> List[Hotspot]:
        """解析搜索结果为 Hotspot 对象

        Args:
            raw_results: 原始搜索结果字典列表

        Returns:
            Hotspot 对象列表
        """
        hotspots: List[Hotspot] = []
        for item in raw_results:
            try:
                title = item.get("title", "")
                description = item.get("description", item.get("snippet", ""))
                source = item.get("source", item.get("url", "unknown"))
                relevance_score = float(item.get("relevance_score", item.get("score", 0.5)))
                # Clamp relevance_score to [0, 1]
                relevance_score = max(0.0, min(1.0, relevance_score))

                timestamp_raw = item.get("timestamp", item.get("published_at"))
                if isinstance(timestamp_raw, str):
                    try:
                        timestamp = datetime.fromisoformat(timestamp_raw)
                    except (ValueError, TypeError):
                        timestamp = datetime.now(timezone.utc)
                elif isinstance(timestamp_raw, datetime):
                    timestamp = timestamp_raw
                else:
                    timestamp = datetime.now(timezone.utc)

                if not title:
                    continue

                hotspots.append(
                    Hotspot(
                        title=title,
                        description=description,
                        source=source,
                        relevance_score=relevance_score,
                        timestamp=timestamp,
                    )
                )
            except Exception as e:
                logger.warning("Failed to parse hotspot result %s: %s", item, e)
                continue

        return hotspots
