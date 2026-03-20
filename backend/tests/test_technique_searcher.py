"""TechniqueSearcher 单元测试

测试技巧搜索器的核心功能：查询构建、搜索调用、结果解析、降级策略。

需求：4.1, 4.2, 4.3, 4.4
"""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.script_optimization import Technique
from app.services.search_api_client import SearchAPIClient, SearchAPIError
from app.services.technique_searcher import (
    DEFAULT_TECHNIQUES,
    GENERIC_TECHNIQUES,
    TechniqueSearchConfig,
    TechniqueSearcher,
)


@pytest.fixture
def mock_search_client():
    client = MagicMock(spec=SearchAPIClient)
    client.search = AsyncMock(return_value=[])
    return client


@pytest.fixture
def config():
    return TechniqueSearchConfig(search_limit=10, search_type="web", min_results=3)


@pytest.fixture
def searcher(mock_search_client, config):
    return TechniqueSearcher(
        search_api_client=mock_search_client, config=config
    )


@pytest.fixture
def custom_fallback():
    return [
        Technique(name="自定义技巧1", description="d1", example="e1", category="c1", source="custom"),
        Technique(name="自定义技巧2", description="d2", example="e2", category="c2", source="custom"),
        Technique(name="自定义技巧3", description="d3", example="e3", category="c3", source="custom"),
    ]


class TestBuildSearchQuery:
    def test_builds_query_with_type_and_weaknesses(self, searcher):
        query = searcher._build_search_query("短视频", ["节奏太慢", "开场无力"])
        assert "短视频剧本创作技巧" in query
        assert "节奏太慢改进方法" in query
        assert "开场无力改进方法" in query

    def test_builds_query_with_type_only(self, searcher):
        query = searcher._build_search_query("广告", [])
        assert "广告剧本创作技巧" in query

    def test_builds_query_with_weaknesses_only(self, searcher):
        query = searcher._build_search_query("", ["结构混乱"])
        assert "结构混乱改进方法" in query
        assert "剧本创作技巧" not in query

    def test_returns_empty_for_empty_inputs(self, searcher):
        query = searcher._build_search_query("", [])
        assert query == ""

    def test_strips_whitespace(self, searcher):
        query = searcher._build_search_query("  短视频  ", ["  节奏太慢  "])
        assert "短视频剧本创作技巧" in query
        assert "节奏太慢改进方法" in query

    def test_skips_empty_weaknesses(self, searcher):
        query = searcher._build_search_query("短视频", ["", "  ", "节奏太慢"])
        assert "节奏太慢改进方法" in query
        # Empty weaknesses should not produce extra parts
        parts = query.split(" ")
        assert len(parts) == 2  # type + one weakness


class TestCallSearchAPI:
    @pytest.mark.asyncio
    async def test_calls_client_with_query(self, searcher, mock_search_client):
        mock_search_client.search.return_value = []
        await searcher._call_search_api("短视频剧本创作技巧")
        mock_search_client.search.assert_called_once_with(
            query="短视频剧本创作技巧",
            search_type="web",
            limit=10,
        )

    @pytest.mark.asyncio
    async def test_uses_config_settings(self, mock_search_client):
        config = TechniqueSearchConfig(search_type="news", search_limit=5)
        searcher = TechniqueSearcher(mock_search_client, config=config)
        await searcher._call_search_api("test query")
        mock_search_client.search.assert_called_once_with(
            query="test query",
            search_type="news",
            limit=5,
        )


class TestParseTechniqueResults:
    def test_parses_valid_results(self, searcher):
        raw = [
            {
                "title": "技巧1",
                "description": "描述1",
                "example": "示例1",
                "category": "叙事",
                "source": "来源1",
            },
            {
                "name": "技巧2",
                "snippet": "摘要2",
                "url": "https://example.com",
            },
        ]
        techniques = searcher._parse_technique_results(raw)
        assert len(techniques) == 2
        assert techniques[0].name == "技巧1"
        assert techniques[0].description == "描述1"
        assert techniques[0].example == "示例1"
        assert techniques[0].category == "叙事"
        assert techniques[0].source == "来源1"
        # Second result uses fallback field names
        assert techniques[1].name == "技巧2"
        assert techniques[1].description == "摘要2"
        assert techniques[1].source == "https://example.com"
        assert techniques[1].category == "搜索结果"

    def test_skips_items_without_name(self, searcher):
        raw = [
            {"description": "no name", "source": "src"},
            {"title": "", "description": "empty title"},
            {"title": "valid", "description": "ok"},
        ]
        techniques = searcher._parse_technique_results(raw)
        assert len(techniques) == 1
        assert techniques[0].name == "valid"

    def test_handles_missing_fields_gracefully(self, searcher):
        raw = [{"title": "minimal"}]
        techniques = searcher._parse_technique_results(raw)
        assert len(techniques) == 1
        assert techniques[0].description == ""
        assert techniques[0].example == ""
        assert techniques[0].source == "search"
        assert techniques[0].category == "搜索结果"

    def test_empty_results(self, searcher):
        assert searcher._parse_technique_results([]) == []

    def test_skips_malformed_items(self, searcher):
        raw = [
            {"title": "good", "description": "ok"},
            "not a dict",  # type: ignore
        ]
        # The string item should be skipped via exception handling
        techniques = searcher._parse_technique_results(raw)
        assert len(techniques) >= 1
        assert techniques[0].name == "good"


class TestGetFallbackTechniques:
    def test_returns_custom_fallback_when_provided(self, mock_search_client, config, custom_fallback):
        searcher = TechniqueSearcher(mock_search_client, fallback_techniques=custom_fallback, config=config)
        result = searcher._get_fallback_techniques("短视频")
        assert len(result) == 3
        assert result[0].name == "自定义技巧1"

    def test_returns_type_specific_defaults(self, searcher):
        result = searcher._get_fallback_techniques("短视频")
        assert len(result) >= 3
        assert all(isinstance(t, Technique) for t in result)
        assert result == DEFAULT_TECHNIQUES["短视频"]

    def test_returns_generic_for_unknown_type(self, searcher):
        result = searcher._get_fallback_techniques("未知类型")
        assert len(result) >= 3
        assert result == GENERIC_TECHNIQUES

    def test_returns_generic_for_empty_type(self, searcher):
        result = searcher._get_fallback_techniques("")
        assert len(result) >= 3
        assert result == GENERIC_TECHNIQUES

    def test_returns_copy_not_reference(self, searcher):
        """Fallback should return a copy so callers can't mutate the defaults"""
        result = searcher._get_fallback_techniques("短视频")
        result.append(Technique(name="extra", description="", example="", category="", source=""))
        assert len(searcher._get_fallback_techniques("短视频")) == len(DEFAULT_TECHNIQUES["短视频"])


class TestSearchTechniques:
    @pytest.mark.asyncio
    async def test_full_search_flow(self, searcher, mock_search_client):
        """需求 4.1, 4.3: 调用搜索 API 并返回至少 3 条技巧"""
        mock_search_client.search.return_value = [
            {"title": "技巧1", "description": "d1", "example": "e1", "category": "c1", "source": "s1"},
            {"title": "技巧2", "description": "d2", "example": "e2", "category": "c2", "source": "s2"},
            {"title": "技巧3", "description": "d3", "example": "e3", "category": "c3", "source": "s3"},
        ]
        techniques = await searcher.search_techniques("剧本内容", "短视频", ["节奏太慢"])
        assert len(techniques) >= 3
        assert all(isinstance(t, Technique) for t in techniques)

    @pytest.mark.asyncio
    async def test_supplements_with_fallback_when_few_results(self, searcher, mock_search_client):
        """需求 4.3: 不足 3 条时补充默认技巧"""
        mock_search_client.search.return_value = [
            {"title": "搜索技巧1", "description": "d1"},
        ]
        techniques = await searcher.search_techniques("剧本内容", "短视频", ["问题"])
        assert len(techniques) >= 3
        # First result should be from search
        assert techniques[0].name == "搜索技巧1"

    @pytest.mark.asyncio
    async def test_no_duplicate_names_when_supplementing(self, searcher, mock_search_client):
        """Supplemented fallback should not duplicate search results by name"""
        mock_search_client.search.return_value = [
            {"title": "黄金三秒法则", "description": "from search"},
        ]
        techniques = await searcher.search_techniques("剧本内容", "短视频", ["问题"])
        names = [t.name for t in techniques]
        assert names.count("黄金三秒法则") == 1

    @pytest.mark.asyncio
    async def test_returns_fallback_on_api_error(self, searcher, mock_search_client):
        """需求 4.4: 搜索失败时返回默认技巧库内容"""
        mock_search_client.search.side_effect = SearchAPIError("API down")
        techniques = await searcher.search_techniques("剧本内容", "短视频", ["问题"])
        assert len(techniques) >= 3
        assert all(isinstance(t, Technique) for t in techniques)

    @pytest.mark.asyncio
    async def test_returns_fallback_on_unexpected_error(self, searcher, mock_search_client):
        """需求 4.4: 任何异常都降级到默认技巧"""
        mock_search_client.search.side_effect = RuntimeError("unexpected")
        techniques = await searcher.search_techniques("剧本内容", "广告", [])
        assert len(techniques) >= 3

    @pytest.mark.asyncio
    async def test_returns_fallback_when_empty_query(self, searcher, mock_search_client):
        """Empty type and weaknesses should use fallback directly"""
        techniques = await searcher.search_techniques("剧本内容", "", [])
        assert len(techniques) >= 3
        mock_search_client.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_error_on_failure(self, searcher, mock_search_client, caplog):
        """需求 4.4: 搜索失败时记录错误日志"""
        mock_search_client.search.side_effect = SearchAPIError("timeout")
        with caplog.at_level(logging.ERROR, logger="app.services.technique_searcher"):
            await searcher.search_techniques("内容", "短视频", ["问题"])
        assert "Technique search failed" in caplog.text

    @pytest.mark.asyncio
    async def test_default_config(self, mock_search_client):
        """Should work with default config"""
        searcher = TechniqueSearcher(search_api_client=mock_search_client)
        mock_search_client.search.return_value = [
            {"title": "t1", "description": "d1"},
            {"title": "t2", "description": "d2"},
            {"title": "t3", "description": "d3"},
        ]
        techniques = await searcher.search_techniques("script", "短视频", ["weakness"])
        assert len(techniques) >= 3

    @pytest.mark.asyncio
    async def test_uses_custom_fallback_on_error(self, mock_search_client, config, custom_fallback):
        """Custom fallback techniques should be used when search fails"""
        searcher = TechniqueSearcher(mock_search_client, fallback_techniques=custom_fallback, config=config)
        mock_search_client.search.side_effect = SearchAPIError("fail")
        techniques = await searcher.search_techniques("内容", "短视频", ["问题"])
        assert len(techniques) == 3
        assert techniques[0].name == "自定义技巧1"

    @pytest.mark.asyncio
    async def test_query_includes_type_and_weaknesses(self, searcher, mock_search_client):
        """需求 4.2: 根据剧本类型和缺陷提取搜索关键词"""
        mock_search_client.search.return_value = [
            {"title": "t1", "description": "d1"},
            {"title": "t2", "description": "d2"},
            {"title": "t3", "description": "d3"},
        ]
        await searcher.search_techniques("剧本", "短视频", ["节奏太慢", "开场无力"])
        call_args = mock_search_client.search.call_args
        query = call_args.kwargs["query"]
        assert "短视频" in query
        assert "节奏太慢" in query
        assert "开场无力" in query
