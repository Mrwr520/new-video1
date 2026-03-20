"""HotspotSearcher 单元测试

测试热点搜索器的核心功能：关键词提取、搜索调用、结果解析、错误处理。

需求：3.1, 3.2, 3.3, 3.4
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.script_optimization import Hotspot
from app.services.hotspot_searcher import HotspotSearcher, SearchConfig
from app.services.search_api_client import SearchAPIClient, SearchAPIError


@pytest.fixture
def mock_search_client():
    client = MagicMock(spec=SearchAPIClient)
    client.search = AsyncMock(return_value=[])
    return client


@pytest.fixture
def config():
    return SearchConfig(max_keywords=5, search_limit=10, min_keyword_length=2)


@pytest.fixture
def searcher(mock_search_client, config):
    return HotspotSearcher(search_api_client=mock_search_client, config=config)


class TestExtractKeywords:
    def test_extracts_topic_words_first(self, searcher):
        keywords = searcher._extract_keywords("一些剧本内容", "科技创新")
        assert "科技创新" in keywords or any("科技" in k or "创新" in k for k in keywords)

    def test_returns_empty_for_empty_input(self, searcher):
        keywords = searcher._extract_keywords("", "")
        assert keywords == []

    def test_filters_stop_words(self, searcher):
        keywords = searcher._extract_keywords("the is and but not", "topic")
        # English stop words should be filtered
        assert "the" not in keywords
        assert "is" not in keywords
        assert "topic" in keywords

    def test_filters_short_tokens(self, searcher):
        keywords = searcher._extract_keywords("a b c longword another", "主题")
        # Single-char tokens should be filtered (min_keyword_length=2)
        assert "a" not in keywords
        assert "b" not in keywords

    def test_respects_max_keywords(self, mock_search_client):
        config = SearchConfig(max_keywords=3)
        searcher = HotspotSearcher(mock_search_client, config)
        keywords = searcher._extract_keywords(
            "word1 word2 word3 word4 word5 word6", "topic1 topic2"
        )
        assert len(keywords) <= 3

    def test_deduplicates_keywords(self, searcher):
        keywords = searcher._extract_keywords("python python python", "python")
        assert keywords.count("python") == 1

    def test_topic_words_have_priority(self, searcher):
        keywords = searcher._extract_keywords(
            "content about various things", "important_topic"
        )
        assert keywords[0] == "important_topic"

    def test_chinese_text_extraction(self, searcher):
        keywords = searcher._extract_keywords(
            "人工智能 技术 发展 趋势 分析", "人工智能 视频"
        )
        assert "人工智能" in keywords
        assert "视频" in keywords

    def test_filters_chinese_stop_words(self, searcher):
        keywords = searcher._extract_keywords("这个 那个 什么 怎么 科技", "主题词")
        assert "这个" not in keywords
        assert "那个" not in keywords
        assert "科技" in keywords


class TestCallSearchAPI:
    @pytest.mark.asyncio
    async def test_calls_client_with_joined_keywords(self, searcher, mock_search_client):
        mock_search_client.search.return_value = []
        await searcher._call_search_api(["科技", "创新", "趋势"])
        mock_search_client.search.assert_called_once_with(
            query="科技 创新 趋势",
            search_type="news",
            limit=10,
        )

    @pytest.mark.asyncio
    async def test_uses_config_search_type(self, mock_search_client):
        config = SearchConfig(search_type="web", search_limit=5)
        searcher = HotspotSearcher(mock_search_client, config)
        await searcher._call_search_api(["test"])
        mock_search_client.search.assert_called_once_with(
            query="test",
            search_type="web",
            limit=5,
        )


class TestParseHotspotResults:
    def test_parses_valid_results(self, searcher):
        raw = [
            {
                "title": "热点新闻1",
                "description": "描述1",
                "source": "来源1",
                "relevance_score": 0.9,
                "timestamp": "2024-01-15T10:00:00+00:00",
            },
            {
                "title": "热点新闻2",
                "snippet": "摘要2",
                "url": "https://example.com",
                "score": 0.7,
            },
        ]
        hotspots = searcher._parse_hotspot_results(raw)
        assert len(hotspots) == 2
        assert hotspots[0].title == "热点新闻1"
        assert hotspots[0].description == "描述1"
        assert hotspots[0].source == "来源1"
        assert hotspots[0].relevance_score == 0.9
        # Second result uses fallback field names
        assert hotspots[1].description == "摘要2"
        assert hotspots[1].source == "https://example.com"

    def test_skips_items_without_title(self, searcher):
        raw = [
            {"description": "no title here", "source": "src"},
            {"title": "", "description": "empty title"},
            {"title": "valid", "description": "ok", "source": "s"},
        ]
        hotspots = searcher._parse_hotspot_results(raw)
        assert len(hotspots) == 1
        assert hotspots[0].title == "valid"

    def test_clamps_relevance_score(self, searcher):
        raw = [
            {"title": "t1", "relevance_score": 1.5},
            {"title": "t2", "relevance_score": -0.3},
        ]
        hotspots = searcher._parse_hotspot_results(raw)
        assert hotspots[0].relevance_score == 1.0
        assert hotspots[1].relevance_score == 0.0

    def test_handles_missing_fields_gracefully(self, searcher):
        raw = [{"title": "minimal"}]
        hotspots = searcher._parse_hotspot_results(raw)
        assert len(hotspots) == 1
        assert hotspots[0].description == ""
        assert hotspots[0].source == "unknown"
        assert hotspots[0].relevance_score == 0.5

    def test_empty_results(self, searcher):
        assert searcher._parse_hotspot_results([]) == []

    def test_handles_datetime_object_timestamp(self, searcher):
        ts = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        raw = [{"title": "t", "timestamp": ts}]
        hotspots = searcher._parse_hotspot_results(raw)
        assert hotspots[0].timestamp == ts

    def test_handles_invalid_timestamp_string(self, searcher):
        raw = [{"title": "t", "timestamp": "not-a-date"}]
        hotspots = searcher._parse_hotspot_results(raw)
        assert len(hotspots) == 1
        # Should fall back to now()
        assert isinstance(hotspots[0].timestamp, datetime)


class TestSearchHotspots:
    @pytest.mark.asyncio
    async def test_full_search_flow(self, searcher, mock_search_client):
        mock_search_client.search.return_value = [
            {"title": "热点1", "description": "desc1", "source": "src1", "relevance_score": 0.8},
            {"title": "热点2", "description": "desc2", "source": "src2", "relevance_score": 0.7},
            {"title": "热点3", "description": "desc3", "source": "src3", "relevance_score": 0.6},
        ]
        hotspots = await searcher.search_hotspots("人工智能 技术 发展", "人工智能")
        assert len(hotspots) == 3
        assert all(isinstance(h, Hotspot) for h in hotspots)

    @pytest.mark.asyncio
    async def test_returns_empty_on_api_error(self, searcher, mock_search_client):
        """需求 3.4: 搜索失败时返回空列表"""
        mock_search_client.search.side_effect = SearchAPIError("API down")
        hotspots = await searcher.search_hotspots("剧本内容", "主题")
        assert hotspots == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_unexpected_error(self, searcher, mock_search_client):
        mock_search_client.search.side_effect = RuntimeError("unexpected")
        hotspots = await searcher.search_hotspots("剧本内容", "主题")
        assert hotspots == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_keywords(self, searcher, mock_search_client):
        """Empty script and topic should yield no keywords and return empty"""
        hotspots = await searcher.search_hotspots("", "")
        assert hotspots == []
        mock_search_client.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_error_on_failure(self, searcher, mock_search_client, caplog):
        """需求 3.4: 搜索失败时记录错误日志"""
        mock_search_client.search.side_effect = SearchAPIError("timeout")
        import logging
        with caplog.at_level(logging.ERROR, logger="app.services.hotspot_searcher"):
            await searcher.search_hotspots("内容", "主题")
        assert "Hotspot search failed" in caplog.text

    @pytest.mark.asyncio
    async def test_default_config(self, mock_search_client):
        """Should work with default config"""
        searcher = HotspotSearcher(search_api_client=mock_search_client)
        mock_search_client.search.return_value = [
            {"title": "t", "description": "d", "source": "s", "relevance_score": 0.5}
        ]
        hotspots = await searcher.search_hotspots("some script content here", "topic")
        assert len(hotspots) == 1
