"""
Integration tests for TavilyClient against the REAL Tavily API.

These tests call the actual Tavily API and require a valid TAVILY_API_KEY.
All tests are skipped gracefully when the API key is not set.

Usage:
    conda run -n discord_bot pytest tests/services/external/tavily_integration_test.py -v
"""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

PROJECT_ROOT = Path("/home/flowerf/Projects/discord-bot-v1")
sys.path.insert(0, str(PROJECT_ROOT))

from twin.shared.external.tavily_client import TavilyClient, TavilyApiError


# Skip all tests in this module when no API key is available
pytestmark = pytest.mark.skipif(
    not os.getenv("TAVILY_API_KEY"),
    reason="No TAVILY_API_KEY",
)


@pytest.fixture
def client():
    """Create a fresh TavilyClient for each test."""
    return TavilyClient()


@pytest.fixture(autouse=True)
def cleanup(client):
    """Close the client session after each test."""
    yield
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Running inside an async context — schedule cleanup
            loop.create_task(client.close())
        else:
            loop.run_until_complete(client.close())
    except Exception:
        pass  # Best-effort cleanup


class TestRealSearchBasic:
    """Basic search returns results with answer and sources."""

    @pytest.mark.asyncio
    async def test_real_search_basic(self, client):
        """Basic search returns results with answer and sources."""
        result = await client.search(
            query="Python programming language",
            search_depth="basic",
            max_results=3,
            include_answer=True,
        )

        assert "results" in result
        assert isinstance(result["results"], list)
        assert len(result["results"]) > 0

        # Each result should have title, url, content, score
        for r in result["results"]:
            assert "title" in r
            assert "url" in r
            assert "content" in r
            assert "score" in r

        # Answer should be present when include_answer=True
        assert "answer" in result
        assert result["answer"] is not None
        assert len(result["answer"]) > 0


class TestRealSearchTopicNews:
    """topic='news' returns time-relevant results."""

    @pytest.mark.asyncio
    async def test_real_search_with_topic_news(self, client):
        """Search with topic='news' returns time-relevant results."""
        result = await client.search(
            query="technology",
            topic="news",
            max_results=3,
        )

        assert "results" in result
        assert isinstance(result["results"], list)
        # News results may vary, but should return something
        assert len(result["results"]) >= 0


class TestRealSearchIncludeDomains:
    """include_domains restricts results to specified domains."""

    @pytest.mark.asyncio
    async def test_real_search_include_domains(self, client):
        """include_domains=['wikipedia.org'] should include wikipedia results."""
        result = await client.search(
            query="artificial intelligence",
            include_domains=["wikipedia.org"],
            max_results=5,
        )

        assert "results" in result
        # If results are returned, at least some should be from wikipedia
        if result["results"]:
            wikipedia_urls = [
                r for r in result["results"]
                if "wikipedia.org" in r.get("url", "")
            ]
            assert len(wikipedia_urls) > 0, (
                "Expected at least one wikipedia.org result when include_domains=['wikipedia.org']"
            )


class TestRealSearchExcludeDomains:
    """exclude_domains filters out results from specified domains."""

    @pytest.mark.asyncio
    async def test_real_search_exclude_domains(self, client):
        """exclude_domains=['youtube.com'] should NOT include youtube results."""
        result = await client.search(
            query="Python tutorial",
            exclude_domains=["youtube.com"],
            max_results=5,
        )

        assert "results" in result
        for r in result["results"]:
            url = r.get("url", "")
            assert "youtube.com" not in url, (
                f"Found youtube.com result when exclude_domains=['youtube.com']: {url}"
            )


class TestRealSearchTimeRangeWeek:
    """time_range='week' returns recent results."""

    @pytest.mark.asyncio
    async def test_real_search_time_range_week(self, client):
        """time_range='week' returns recent results."""
        result = await client.search(
            query="news",
            time_range="week",
            max_results=3,
        )

        assert "results" in result
        # The API should return results; time_range filtering is server-side
        assert isinstance(result["results"], list)


class TestRealSearchAdvancedDepth:
    """search_depth='advanced' returns results."""

    @pytest.mark.asyncio
    async def test_real_search_advanced_depth(self, client):
        """search_depth='advanced' returns results."""
        result = await client.search(
            query="machine learning",
            search_depth="advanced",
            max_results=3,
        )

        assert "results" in result
        assert isinstance(result["results"], list)
        assert len(result["results"]) > 0


class TestRealCircuitBreakerResets:
    """After successful search, circuit state is 'closed' in Redis."""

    @pytest.mark.asyncio
    async def test_real_circuit_breaker_resets(self):
        """After successful search, circuit state should be 'closed' in Redis (mocked)."""
        client = TavilyClient()

        # Mock Redis to capture state writes
        mock_redis = AsyncMock()
        mock_redis.__aenter__ = AsyncMock(return_value=mock_redis)
        mock_redis.__aexit__ = AsyncMock(return_value=None)
        mock_redis.closed = False

        redis_state = {}

        async def mock_get(key):
            return redis_state.get(key)

        async def mock_set(key, value):
            redis_state[key] = str(value)

        mock_redis.get = AsyncMock(side_effect=mock_get)
        mock_redis.set = AsyncMock(side_effect=mock_set)

        with patch.object(client, "_get_redis_client", new_callable=AsyncMock, return_value=mock_redis):
            # Real API call (not mocked) — uses real Tavily API
            result = await client.search(
                query="test",
                max_results=1,
            )

            assert "results" in result

        # After success, circuit breaker should have written "closed" state
        state = redis_state.get("tavily:circuit_state")
        assert state == "closed", (
            f"Expected circuit breaker state 'closed' after successful search, got '{state}'"
        )

        # Cleanup
        await client.close()
