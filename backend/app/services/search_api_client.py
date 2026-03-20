"""搜索 API 客户端

封装第三方搜索 API 调用，支持 web 和 news 搜索，
包含重试机制（最多 3 次）和速率限制保护。

需求：3.1, 4.1, 7.1, 7.2, 7.5, 8.4
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

import httpx

logger = logging.getLogger(__name__)


class SearchAPIError(Exception):
    """搜索 API 错误基类"""
    pass


class SearchAPIRateLimitError(SearchAPIError):
    """速率限制错误"""
    pass


class SearchAPIAuthError(SearchAPIError):
    """认证错误"""
    pass


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    retry_delay: float = 1.0
    backoff_factor: float = 2.0


@dataclass
class RateLimitConfig:
    """速率限制配置"""
    min_interval: float = 0.2  # 最小请求间隔（秒）


class SearchAPIClient:
    """第三方搜索 API 客户端

    封装搜索 API 调用，提供重试机制和速率限制保护。
    """

    def __init__(
        self,
        api_key: str,
        api_endpoint: str,
        retry_config: RetryConfig | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ):
        self.api_key = api_key
        self.api_endpoint = api_endpoint.rstrip("/")
        self.retry_config = retry_config or RetryConfig()
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self._last_request_time: float = 0.0
        self._rate_limit_lock = asyncio.Lock()

    async def search(
        self,
        query: str,
        search_type: str = "web",
        limit: int = 10,
    ) -> List[Dict]:
        """执行搜索

        Args:
            query: 搜索查询
            search_type: 搜索类型 (web, news)
            limit: 结果数量限制

        Returns:
            搜索结果列表

        Raises:
            SearchAPIError: 搜索失败（重试耗尽后）
        """
        if not query or not query.strip():
            return []

        logger.info(
            "Search API call: query=%s, type=%s, limit=%d",
            query,
            search_type,
            limit,
        )

        async def _do_request() -> List[Dict]:
            await self._enforce_rate_limit()
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.api_endpoint}/search",
                    params={
                        "q": query,
                        "type": search_type,
                        "count": limit,
                    },
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
                if response.status_code == 401:
                    raise SearchAPIAuthError("Invalid API key")
                if response.status_code == 429:
                    raise SearchAPIRateLimitError("Rate limit exceeded")
                response.raise_for_status()
                data = response.json()
                results = data.get("results", [])
                logger.info(
                    "Search API returned %d results for query: %s",
                    len(results),
                    query,
                )
                return results

        return await self._execute_with_retry(_do_request)

    async def _execute_with_retry(
        self,
        request_func: Callable[[], Any],
    ) -> Any:
        """带重试的请求执行

        使用指数退避策略重试失败的请求，最多重试 max_retries 次。
        认证错误不会重试。

        Args:
            request_func: 异步请求函数

        Returns:
            请求结果

        Raises:
            SearchAPIError: 重试耗尽后仍失败
        """
        last_exception: Exception | None = None

        for attempt in range(self.retry_config.max_retries):
            try:
                return await request_func()
            except SearchAPIAuthError:
                raise
            except Exception as e:
                last_exception = e
                if attempt < self.retry_config.max_retries - 1:
                    delay = self.retry_config.retry_delay * (
                        self.retry_config.backoff_factor ** attempt
                    )
                    logger.warning(
                        "Search API request failed (attempt %d/%d): %s. "
                        "Retrying in %.1fs...",
                        attempt + 1,
                        self.retry_config.max_retries,
                        e,
                        delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "Search API request failed after %d attempts: %s",
                        self.retry_config.max_retries,
                        e,
                    )

        raise SearchAPIError(
            f"Request failed after {self.retry_config.max_retries} retries: "
            f"{last_exception}"
        )

    async def _enforce_rate_limit(self) -> None:
        """强制执行速率限制

        确保连续请求之间的间隔不小于配置的最小间隔。
        """
        async with self._rate_limit_lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            if elapsed < self.rate_limit_config.min_interval:
                wait_time = self.rate_limit_config.min_interval - elapsed
                await asyncio.sleep(wait_time)
            self._last_request_time = time.monotonic()
