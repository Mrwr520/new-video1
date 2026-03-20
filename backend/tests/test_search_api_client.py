"""SearchAPIClient 单元测试

测试搜索 API 客户端的核心功能：搜索、重试机制、速率限制。
"""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import httpx

from app.services.search_api_client import (
    RateLimitConfig,
    RetryConfig,
    SearchAPIClient,
    SearchAPIAuthError,
    SearchAPIError,
    SearchAPIRateLimitError,
)


@pytest.fixture
def retry_config():
    """快速重试配置，用于测试"""
    return RetryConfig(max_retries=3, retry_delay=0.01, backoff_factor=2.0)


@pytest.fixture
def rate_limit_config():
    return RateLimitConfig(min_interval=0.05)


@pytest.fixture
def client(retry_config, rate_limit_config):
    return SearchAPIClient(
        api_key="test-key",
        api_endpoint="https://api.example.com",
        retry_config=retry_config,
        rate_limit_config=rate_limit_config,
    )


def _mock_response(status_code=200, json_data=None):
    """创建模拟的 httpx.Response"""
    response = httpx.Response(
        status_code=status_code,
        json=json_data or {"results": []},
        request=httpx.Request("GET", "https://api.example.com/search"),
    )
    return response


class TestSearchAPIClientInit:
    def test_default_config(self):
        c = SearchAPIClient(api_key="key", api_endpoint="https://api.example.com")
        assert c.api_key == "key"
        assert c.api_endpoint == "https://api.example.com"
        assert c.retry_config.max_retries == 3
        assert c.rate_limit_config.min_interval == 0.2

    def test_custom_config(self, retry_config, rate_limit_config):
        c = SearchAPIClient(
            api_key="key",
            api_endpoint="https://api.example.com/",
            retry_config=retry_config,
            rate_limit_config=rate_limit_config,
        )
        assert c.api_endpoint == "https://api.example.com"
        assert c.retry_config.max_retries == 3
        assert c.rate_limit_config.min_interval == 0.05


class TestSearch:
    @pytest.mark.asyncio
    async def test_empty_query_returns_empty(self, client):
        result = await client.search("")
        assert result == []

    @pytest.mark.asyncio
    async def test_whitespace_query_returns_empty(self, client):
        result = await client.search("   ")
        assert result == []

    @pytest.mark.asyncio
    async def test_successful_web_search(self, client):
        mock_results = [{"title": "Result 1"}, {"title": "Result 2"}]
        mock_resp = _mock_response(200, {"results": mock_results})

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            results = await client.search("test query")
            assert results == mock_results

    @pytest.mark.asyncio
    async def test_successful_news_search(self, client):
        mock_results = [{"title": "News 1"}]
        mock_resp = _mock_response(200, {"results": mock_results})

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp) as mock_get:
            results = await client.search("test", search_type="news", limit=5)
            assert results == mock_results
            call_kwargs = mock_get.call_args
            assert call_kwargs.kwargs["params"]["type"] == "news"
            assert call_kwargs.kwargs["params"]["count"] == 5

    @pytest.mark.asyncio
    async def test_auth_header_sent(self, client):
        mock_resp = _mock_response(200, {"results": []})

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp) as mock_get:
            await client.search("test")
            call_kwargs = mock_get.call_args
            assert call_kwargs.kwargs["headers"]["Authorization"] == "Bearer test-key"

    @pytest.mark.asyncio
    async def test_auth_error_raises_immediately(self, client):
        mock_resp = _mock_response(401, {"error": "unauthorized"})

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
            with pytest.raises(SearchAPIAuthError):
                await client.search("test")

    @pytest.mark.asyncio
    async def test_rate_limit_error_retries(self, client):
        """429 errors should be retried"""
        rate_limit_resp = _mock_response(429, {"error": "rate limited"})
        success_resp = _mock_response(200, {"results": [{"title": "ok"}]})

        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                resp = rate_limit_resp
                resp.raise_for_status()  # will raise
            return success_resp

        # 429 raises httpx.HTTPStatusError on raise_for_status
        responses = [rate_limit_resp, rate_limit_resp, success_resp]
        call_idx = 0

        async def mock_get(*args, **kwargs):
            nonlocal call_idx
            resp = responses[call_idx]
            call_idx += 1
            return resp

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=mock_get):
            results = await client.search("test")
            assert results == [{"title": "ok"}]


class TestRetryMechanism:
    @pytest.mark.asyncio
    async def test_retries_on_failure(self, client):
        """Should retry up to max_retries times"""
        call_count = 0

        async def failing_func():
            nonlocal call_count
            call_count += 1
            raise httpx.ConnectError("Connection failed")

        with pytest.raises(SearchAPIError, match="3 retries"):
            await client._execute_with_retry(failing_func)

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_succeeds_after_retries(self, client):
        """Should return result if a retry succeeds"""
        call_count = 0

        async def eventually_succeeds():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.ConnectError("Connection failed")
            return "success"

        result = await client._execute_with_retry(eventually_succeeds)
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_auth_error(self, client):
        """Auth errors should not be retried"""
        call_count = 0

        async def auth_fail():
            nonlocal call_count
            call_count += 1
            raise SearchAPIAuthError("Invalid key")

        with pytest.raises(SearchAPIAuthError):
            await client._execute_with_retry(auth_fail)

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_first_attempt_success(self, client):
        """Should return immediately on first success"""
        async def success():
            return [{"title": "result"}]

        result = await client._execute_with_retry(success)
        assert result == [{"title": "result"}]


class TestRateLimit:
    @pytest.mark.asyncio
    async def test_rate_limit_enforces_interval(self):
        """Consecutive requests should respect min_interval"""
        config = RateLimitConfig(min_interval=0.1)
        c = SearchAPIClient(
            api_key="key",
            api_endpoint="https://api.example.com",
            retry_config=RetryConfig(max_retries=1, retry_delay=0.01),
            rate_limit_config=config,
        )

        timestamps = []

        async def record_time():
            timestamps.append(time.monotonic())
            return []

        # Call _enforce_rate_limit + record multiple times
        for _ in range(3):
            await c._enforce_rate_limit()
            timestamps.append(time.monotonic())

        # Check intervals between consecutive calls
        for i in range(1, len(timestamps)):
            interval = timestamps[i] - timestamps[i - 1]
            assert interval >= config.min_interval - 0.01  # small tolerance

    @pytest.mark.asyncio
    async def test_no_delay_on_first_request(self):
        """First request should not be delayed"""
        config = RateLimitConfig(min_interval=1.0)
        c = SearchAPIClient(
            api_key="key",
            api_endpoint="https://api.example.com",
            rate_limit_config=config,
        )

        start = time.monotonic()
        await c._enforce_rate_limit()
        elapsed = time.monotonic() - start

        # First request should be nearly instant
        assert elapsed < 0.1
