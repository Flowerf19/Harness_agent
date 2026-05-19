"""
Unit tests for TavilyClient circuit breaker logic.

Tests circuit breaker state transitions (closed → open → half-open → closed/open)
using mocked Redis and _do_search.
"""
import sys
import time
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from twin.shared.external.tavily_client import TavilyClient, TavilyApiError


class TestCircuitBreakerClosed:
    """Test circuit breaker in closed state."""

    @pytest.mark.asyncio
    async def test_cb_closed_allows_call(self):
        """Circuit closed → search allowed (mock _do_search success)."""
        client = TavilyClient(api_key="test-key")

        with patch.object(client, "_get_redis_client", new_callable=AsyncMock, return_value=None):
            with patch.object(client, "_do_search", new_callable=AsyncMock) as mock_do_search:
                mock_do_search.return_value = {"results": [{"title": "Test"}], "answer": "Answer"}

                with patch.object(client, "_cb_on_success", new_callable=AsyncMock):
                    result = await client.search(query="test query")

                    assert "results" in result
                    mock_do_search.assert_called_once()


class TestCircuitBreakerOpens:
    """Test circuit breaker transitions to open after failures."""

    @pytest.mark.asyncio
    async def test_cb_opens_after_5_failures(self):
        """5 consecutive failures → state becomes 'open'."""
        client = TavilyClient(api_key="test-key")

        # Create a mock Redis client
        mock_redis = AsyncMock()
        mock_redis.__aenter__ = AsyncMock(return_value=mock_redis)
        mock_redis.__aexit__ = AsyncMock(return_value=None)
        mock_redis.closed = False

        redis_state = {
            "tavily:circuit_state": "closed",
            "tavily:failure_count": "0",
            "tavily:last_failure_time": "0",
        }

        async def mock_get(key):
            return redis_state.get(key)

        async def mock_set(key, value):
            redis_state[key] = str(value)

        mock_redis.get = AsyncMock(side_effect=mock_get)
        mock_redis.set = AsyncMock(side_effect=mock_set)

        with patch.object(client, "_get_redis_client", new_callable=AsyncMock, return_value=mock_redis):
            with patch.object(client, "_do_search", new_callable=AsyncMock) as mock_do_search:
                # Always raise a retryable error (500)
                mock_do_search.side_effect = TavilyApiError("Server error", status_code=500)

                # Make 5 failed searches
                for i in range(5):
                    try:
                        await client.search(query=f"test query {i}")
                    except TavilyApiError:
                        pass

                # After 5 failures, circuit should be open
                state = redis_state.get("tavily:circuit_state")
                assert state == "open"

                failure_count = int(redis_state.get("tavily:failure_count", "0"))
                assert failure_count >= 5


class TestCircuitBreakerOpenBlocksCall:
    """Test circuit breaker blocks calls when open."""

    @pytest.mark.asyncio
    async def test_cb_open_blocks_call_under_30s(self):
        """Circuit open + <30s → raises 'Circuit breaker open' error."""
        client = TavilyClient(api_key="test-key")

        mock_redis = AsyncMock()
        mock_redis.__aenter__ = AsyncMock(return_value=mock_redis)
        mock_redis.__aexit__ = AsyncMock(return_value=None)
        mock_redis.closed = False

        now = time.time()
        redis_state = {
            "tavily:circuit_state": "open",
            "tavily:failure_count": "5",
            "tavily:last_failure_time": str(now - 10),  # 10 seconds ago (< 30s)
        }

        async def mock_get(key):
            return redis_state.get(key)

        mock_redis.get = AsyncMock(side_effect=mock_get)
        mock_redis.set = AsyncMock()

        with patch.object(client, "_get_redis_client", new_callable=AsyncMock, return_value=mock_redis):
            with pytest.raises(TavilyApiError, match="Circuit breaker open"):
                await client.search(query="test query")


class TestCircuitBreakerHalfOpen:
    """Test circuit breaker transitions to half-open."""

    @pytest.mark.asyncio
    async def test_cb_half_open_after_30s(self):
        """Circuit open + >=30s → state transitions through half-open to closed on success."""
        client = TavilyClient(api_key="test-key")

        mock_redis = AsyncMock()
        mock_redis.__aenter__ = AsyncMock(return_value=mock_redis)
        mock_redis.__aexit__ = AsyncMock(return_value=None)
        mock_redis.closed = False

        now = time.time()
        redis_state = {
            "tavily:circuit_state": "open",
            "tavily:failure_count": "5",
            "tavily:last_failure_time": str(now - 35),  # 35 seconds ago (> 30s)
        }

        async def mock_get(key):
            return redis_state.get(key)

        async def mock_set(key, value):
            redis_state[key] = str(value)

        mock_redis.get = AsyncMock(side_effect=mock_get)
        mock_redis.set = AsyncMock(side_effect=mock_set)

        with patch.object(client, "_get_redis_client", new_callable=AsyncMock, return_value=mock_redis):
            with patch.object(client, "_do_search", new_callable=AsyncMock) as mock_do_search:
                mock_do_search.return_value = {"results": [], "answer": "test"}

                await client.search(query="test query")

                # After a successful call, _cb_on_success writes "closed" to Redis
                state = redis_state.get("tavily:circuit_state")
                assert state == "closed"

    @pytest.mark.asyncio
    async def test_cb_half_open_success_closes(self):
        """Half-open + success → state becomes 'closed'."""
        client = TavilyClient(api_key="test-key")

        mock_redis = AsyncMock()
        mock_redis.__aenter__ = AsyncMock(return_value=mock_redis)
        mock_redis.__aexit__ = AsyncMock(return_value=None)
        mock_redis.closed = False

        now = time.time()
        redis_state = {
            "tavily:circuit_state": "half-open",
            "tavily:failure_count": "5",
            "tavily:last_failure_time": str(now - 35),
        }

        async def mock_get(key):
            return redis_state.get(key)

        async def mock_set(key, value):
            redis_state[key] = str(value)

        mock_redis.get = AsyncMock(side_effect=mock_get)
        mock_redis.set = AsyncMock(side_effect=mock_set)

        with patch.object(client, "_get_redis_client", new_callable=AsyncMock, return_value=mock_redis):
            with patch.object(client, "_do_search", new_callable=AsyncMock) as mock_do_search:
                mock_do_search.return_value = {"results": [], "answer": "test"}

                await client.search(query="test query")

                state = redis_state.get("tavily:circuit_state")
                assert state == "closed"

    @pytest.mark.asyncio
    async def test_cb_half_open_fail_reopens(self):
        """Half-open + failure → state becomes 'open' again."""
        client = TavilyClient(api_key="test-key")

        mock_redis = AsyncMock()
        mock_redis.__aenter__ = AsyncMock(return_value=mock_redis)
        mock_redis.__aexit__ = AsyncMock(return_value=None)
        mock_redis.closed = False

        now = time.time()
        redis_state = {
            "tavily:circuit_state": "half-open",
            "tavily:failure_count": "5",
            "tavily:last_failure_time": str(now - 35),
        }

        async def mock_get(key):
            return redis_state.get(key)

        async def mock_set(key, value):
            redis_state[key] = str(value)

        mock_redis.get = AsyncMock(side_effect=mock_get)
        mock_redis.set = AsyncMock(side_effect=mock_set)

        with patch.object(client, "_get_redis_client", new_callable=AsyncMock, return_value=mock_redis):
            with patch.object(client, "_do_search", new_callable=AsyncMock) as mock_do_search:
                mock_do_search.side_effect = TavilyApiError("Server error", status_code=500)

                with pytest.raises(TavilyApiError):
                    await client.search(query="test query")

                state = redis_state.get("tavily:circuit_state")
                assert state == "open"


class TestCircuitBreakerRedisUnavailable:
    """Test circuit breaker graceful degradation when Redis unavailable."""

    @pytest.mark.asyncio
    async def test_cb_redis_unavailable_allows_call(self):
        """Redis unavailable → search allowed through (graceful degradation)."""
        client = TavilyClient(api_key="test-key")

        # _get_redis_client returns None
        with patch.object(client, "_get_redis_client", new_callable=AsyncMock, return_value=None):
            with patch.object(client, "_do_search", new_callable=AsyncMock) as mock_do_search:
                mock_do_search.return_value = {"results": [{"title": "Test"}], "answer": "Answer"}

                with patch.object(client, "_cb_on_success", new_callable=AsyncMock):
                    result = await client.search(query="test query")

                    assert "results" in result
                    mock_do_search.assert_called_once()
