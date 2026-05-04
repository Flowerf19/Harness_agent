"""
TavilyClient - Web Search API client cho AI agents.

Tavily là search API được tối ưu cho AI agents, cung cấp:
- Real-time web search
- AI-generated answers
- Clean, structured results

API Documentation: https://docs.tavily.com/
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

import aiohttp

from src.config.settings import Config

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_AVAILABLE = False


def _safe_decode(val: Any, default: str) -> str:
    """Safely decode a value from Redis (bytes, str, or None) to str."""
    if val is None:
        return default
    if isinstance(val, bytes):
        return val.decode()
    return str(val)


@dataclass
class SearchResult:
    """Structured search result for LLM consumption."""
    query: str
    answer: Optional[str]  # AI-generated answer from Tavily
    sources: List[dict]    # List of {title, url, content, score}
    topic: Optional[str]   # "general" or "news"
    time_range: Optional[str]  # "day", "week", "month", "year"
    result_count: int      # Number of sources


class TavilyApiError(Exception):
    """
    Exception raised khi Tavily API call fails.

    Attributes:
        message: Error message
        status_code: HTTP status code (if available)
        original_error: Original exception (if any)
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        original_error: Optional[Exception] = None
    ):
        self.message = message
        self.status_code = status_code
        self.original_error = original_error
        super().__init__(f"Tavily API Error: {message}")

    def __repr__(self) -> str:
        return f"TavilyApiError(message={self.message}, status_code={self.status_code})"


class TavilyClient:
    """
    Tavily Web Search API Client.

    Sử dụng aiohttp để thực hiện async HTTP requests.
    Handles authentication, timeouts, và error handling.

    Example:
        client = TavilyClient()
        if client.is_configured():
            results = await client.search("Python async programming")
    """

    # Circuit breaker configuration
    CB_FAILURE_THRESHOLD = 5      # consecutive failures before circuit opens
    CB_RECOVERY_TIMEOUT = 30      # seconds before open circuit transitions to half-open
    CB_MAX_RETRIES = 3            # max retry attempts for retryable errors
    CB_REDIS_KEY_STATE = "tavily:circuit_state"
    CB_REDIS_KEY_FAILURES = "tavily:failure_count"
    CB_REDIS_KEY_LAST_FAILURE = "tavily:last_failure_time"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        max_results: Optional[int] = None,
        search_depth: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        """
        Initialize TavilyClient.

        Args:
            api_key: Tavily API key (default: from Config)
            api_url: Tavily API URL (default: from Config)
            max_results: Default max results (default: from Config)
            search_depth: Default search depth "basic" or "advanced" (default: from Config)
            timeout: Request timeout in seconds (default: from Config)
        """
        self.api_key = api_key or Config.TAVILY_API_KEY
        self.api_url = api_url or Config.TAVILY_API_URL
        self.max_results = max_results or Config.TAVILY_MAX_RESULTS
        self.search_depth = search_depth or Config.TAVILY_SEARCH_DEPTH
        self.timeout = timeout or Config.TAVILY_TIMEOUT

        self._session: Optional[aiohttp.ClientSession] = None
        self._redis_client: Optional[Any] = None

        logger.info(
            f"TavilyClient initialized - configured: {self.is_configured()}, "
            f"max_results: {self.max_results}, depth: {self.search_depth}"
        )

    def is_configured(self) -> bool:
        """
        Check if Tavily API is properly configured.

        Returns:
            bool: True if API key is set
        """
        return bool(self.api_key)

    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Get or create aiohttp session.

        Returns:
            aiohttp.ClientSession: HTTP client session
        """
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close aiohttp session and Redis client."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("TavilyClient session closed")
        if self._redis_client and not self._redis_client.closed:
            await self._redis_client.close()
            logger.debug("TavilyClient Redis client closed")

    # ── Circuit breaker helpers ──────────────────────────────────────────

    async def _get_redis_client(self):
        """Get a Redis client, reusing an existing one if available."""
        if not REDIS_AVAILABLE or not Config.REDIS_URL:
            return None
        if self._redis_client is None:
            try:
                self._redis_client = redis.from_url(Config.REDIS_URL)
            except Exception as e:
                logger.warning(f"Tavily circuit breaker: Redis connection failed: {e}")
                return None
        return self._redis_client

    async def _cb_get_state(self) -> Optional[Dict[str, Any]]:
        """
        Read circuit breaker state from Redis.

        Returns:
            Dict with 'state', 'failure_count', 'last_failure_time',
            or None if Redis unavailable.
        """
        r = await self._get_redis_client()
        if r is None:
            return None
        try:
            async with r as conn:
                state = await conn.get(self.CB_REDIS_KEY_STATE)
                failures = await conn.get(self.CB_REDIS_KEY_FAILURES)
                last_failure = await conn.get(self.CB_REDIS_KEY_LAST_FAILURE)
            return {
                "state": _safe_decode(state, "closed"),
                "failure_count": int(_safe_decode(failures, "0")),
                "last_failure_time": float(_safe_decode(last_failure, "0")),
            }
        except Exception as e:
            logger.warning(f"Tavily circuit breaker: failed to read state: {e}")
            return None

    async def _cb_set_state(
        self,
        state: str,
        failure_count: int = 0,
        last_failure_time: Optional[float] = None,
    ) -> None:
        """Write circuit breaker state to Redis."""
        r = await self._get_redis_client()
        if r is None:
            return
        try:
            async with r as conn:
                await conn.set(self.CB_REDIS_KEY_STATE, state)
                await conn.set(self.CB_REDIS_KEY_FAILURES, failure_count)
                if last_failure_time is not None:
                    await conn.set(self.CB_REDIS_KEY_LAST_FAILURE, last_failure_time)
                else:
                    await conn.set(self.CB_REDIS_KEY_LAST_FAILURE, time.time())
            logger.info(f"Tavily circuit breaker → state={state}, failures={failure_count}")
        except Exception as e:
            logger.warning(f"Tavily circuit breaker: failed to write state: {e}")

    async def _cb_check_before_call(self) -> bool:
        """
        Check if a call is allowed based on circuit breaker state.

        Returns:
            True if the call is allowed, False if circuit is open.
        """
        cb = await self._cb_get_state()
        if cb is None:
            # Redis unavailable — allow call through
            return True

        state = cb["state"]

        if state == "closed":
            return True

        if state == "open":
            elapsed = time.time() - cb["last_failure_time"]
            if elapsed < self.CB_RECOVERY_TIMEOUT:
                logger.warning(
                    f"Tavily circuit breaker OPEN — blocking call "
                    f"(retry in {self.CB_RECOVERY_TIMEOUT - elapsed:.0f}s)"
                )
                return False
            else:
                # Transition to half-open
                await self._cb_set_state("half-open", cb["failure_count"], cb["last_failure_time"])
                logger.info("Tavily circuit breaker: open → half-open (test call allowed)")
                return True

        if state == "half-open":
            # Allow exactly one test call (we're it)
            return True

        return True

    async def _cb_on_success(self) -> None:
        """Handle successful call — reset to closed."""
        await self._cb_set_state("closed", failure_count=0, last_failure_time=None)
        logger.info("Tavily circuit breaker: → closed (success)")

    async def _cb_on_failure(self) -> int:
        """
        Handle failed call — increment counter, open circuit if threshold hit.

        Returns:
            New failure count.
        """
        cb = await self._cb_get_state()
        if cb is None:
            return 0

        new_count = cb["failure_count"] + 1
        now = time.time()

        if new_count >= self.CB_FAILURE_THRESHOLD:
            await self._cb_set_state("open", failure_count=new_count, last_failure_time=now)
            logger.warning(
                f"Tavily circuit breaker: → OPEN ({new_count} consecutive failures)"
            )
        else:
            await self._cb_set_state(cb["state"], failure_count=new_count, last_failure_time=now)

        return new_count

    # ── Internal search call (no retries, no circuit breaker) ────────────

    async def _do_search(
        self,
        url: str,
        headers: dict,
        payload: dict,
    ) -> Dict[str, Any]:
        """
        Execute the actual HTTP call to Tavily API.

        Raises TavilyApiError on any failure.
        """
        session = await self._get_session()
        async with session.post(url, json=payload, headers=headers) as response:
            logger.debug(f"Tavily API response: {response.status}")

            if response.status == 401:
                raise TavilyApiError("Invalid API key", status_code=401)
            elif response.status == 429:
                raise TavilyApiError("Rate limit exceeded", status_code=429)
            elif response.status >= 500:
                raise TavilyApiError(f"Server error: {response.status}", status_code=response.status)
            elif response.status >= 400:
                error_text = await response.text()
                raise TavilyApiError(f"Request failed: {error_text}", status_code=response.status)

            data = await response.json()

            if "results" not in data:
                raise TavilyApiError("Invalid response: missing 'results' field")

            return data

    async def search(
        self,
        query: str,
        search_depth: Optional[str] = None,
        max_results: Optional[int] = None,
        include_answer: bool = True,
        include_raw_content: bool = False,
        include_images: bool = False,
        topic: Optional[str] = None,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        time_range: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute web search via Tavily API with retry and circuit breaker.

        Args:
            query: Search query string
            search_depth: "basic" or "advanced" (default: from config)
            max_results: Max number of results (default: from config)
            include_answer: Include AI-generated answer
            include_raw_content: Include raw page content
            include_images: Include image URLs
            topic: "general" or "news"
            include_domains: Whitelist domains to search
            exclude_domains: Blacklist domains to exclude
            time_range: "day", "week", "month", "year"

        Returns:
            Dict containing:
                - answer: AI-generated answer (if include_answer=True)
                - results: List of search results with title, url, content, score

        Raises:
            TavilyApiError: If API call fails
        """
        # Validate configuration
        if not self.is_configured():
            raise TavilyApiError("Tavily API key not configured")

        if not query or not query.strip():
            raise TavilyApiError("Search query cannot be empty")

        # Use defaults or override
        search_depth = search_depth or self.search_depth
        max_results = max_results or self.max_results

        # Build request
        url = f"{self.api_url}/search"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "query": query.strip(),
            "search_depth": search_depth,
            "max_results": max_results,
            "include_answer": include_answer,
            "include_raw_content": include_raw_content,
            "include_images": include_images,
            "topic": topic,
            "include_domains": include_domains or [],
            "exclude_domains": exclude_domains or [],
            "time_range": time_range,
        }

        logger.info(f"🔍 Tavily search: query='{query[:50]}...', depth={search_depth}, max={max_results}")

        # Check circuit breaker
        if not await self._cb_check_before_call():
            raise TavilyApiError("Circuit breaker open, service unavailable")

        # Retry logic with exponential backoff
        last_error = None
        for attempt in range(self.CB_MAX_RETRIES):
            try:
                data = await self._do_search(url, headers, payload)
                # Success — reset circuit breaker
                await self._cb_on_success()
                result_count = len(data.get("results", []))
                logger.info(f"✅ Tavily search returned {result_count} results")
                return data

            except TavilyApiError as e:
                last_error = e

                # Non-retryable: 401, 429, 4xx client errors
                if e.status_code is not None and e.status_code < 500:
                    logger.warning(f"Tavily search: non-retryable error (HTTP {e.status_code}): {e.message}")
                    raise

                # Retryable: 5xx, timeout, network errors
                is_last_attempt = attempt == self.CB_MAX_RETRIES - 1
                if is_last_attempt:
                    logger.error(f"Tavily search: all {self.CB_MAX_RETRIES} attempts failed — {e.message}")
                    break

                # Wait with exponential backoff: 1s → 2s → 4s
                backoff = 2 ** attempt
                logger.warning(
                    f"Tavily search: attempt {attempt + 1}/{self.CB_MAX_RETRIES} failed, "
                    f"retrying in {backoff}s — {e.message}"
                )
                await asyncio.sleep(backoff)

            except Exception as e:
                # Unexpected errors count as failures too
                last_error = TavilyApiError(f"Unexpected error: {e}", original_error=e)
                is_last_attempt = attempt == self.CB_MAX_RETRIES - 1
                if is_last_attempt:
                    logger.error(f"Tavily search: all {self.CB_MAX_RETRIES} attempts failed — {e}")
                    break
                backoff = 2 ** attempt
                logger.warning(
                    f"Tavily search: attempt {attempt + 1}/{self.CB_MAX_RETRIES} failed, "
                    f"retrying in {backoff}s — {e}"
                )
                await asyncio.sleep(backoff)

        # All retries exhausted — update circuit breaker and raise
        await self._cb_on_failure()
        raise last_error

    def __repr__(self) -> str:
        return f"<TavilyClient: configured={self.is_configured()}>"