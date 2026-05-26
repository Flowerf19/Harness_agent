"""
Unit tests for TavilyClient retry logic.

Tests exponential backoff timing, non-retryable errors (401, 429),
retryable errors (500), and network error retries.
"""
import sys
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from twin.shared.external.tavily_client import TavilyClient, TavilyApiError


class TestRetryExponentialBackoff:
    """Test retry timing with exponential backoff."""

    @pytest.mark.asyncio
    async def test_retry_exponential_backoff_timing(self):
        """Verify retries happen with ~1s, ~2s, ~4s delays (use time mocking)."""
        client = TavilyClient(api_key="test-key")

        sleep_times = []

        async def mock_sleep(seconds):
            sleep_times.append(seconds)

        with patch.object(client, "_cb_check_before_call", new_callable=AsyncMock, return_value=True):
            with patch.object(client, "_do_search", new_callable=AsyncMock) as mock_do_search:
                # Fail first 2 times, succeed on 3rd
                mock_do_search.side_effect = [
                    TavilyApiError("Server error", status_code=500),
                    TavilyApiError("Server error", status_code=500),
                    {"results": [], "answer": "success"},
                ]

                with patch("asyncio.sleep", side_effect=mock_sleep):
                    with patch.object(client, "_cb_on_success", new_callable=AsyncMock):
                        result = await client.search(query="test query")

                        assert result["answer"] == "success"
                        # 2 failures → 2 sleeps: 2^0=1, 2^1=2
                        assert sleep_times == [1, 2]

    @pytest.mark.asyncio
    async def test_retryable_500_retries_3_times(self):
        """500 error → retries 3 times then fails."""
        client = TavilyClient(api_key="test-key")

        sleep_times = []

        async def mock_sleep(seconds):
            sleep_times.append(seconds)

        with patch.object(client, "_cb_check_before_call", new_callable=AsyncMock, return_value=True):
            with patch.object(client, "_do_search", new_callable=AsyncMock) as mock_do_search:
                mock_do_search.side_effect = TavilyApiError("Server error", status_code=500)

                with patch("asyncio.sleep", side_effect=mock_sleep):
                    with patch.object(client, "_cb_on_failure", new_callable=AsyncMock):
                        with pytest.raises(TavilyApiError) as exc_info:
                            await client.search(query="test query")

                    assert exc_info.value.status_code == 500

                    # CB_MAX_RETRIES = 3, so 3 attempts, 2 sleeps
                    assert mock_do_search.call_count == 3
                    assert sleep_times == [1, 2]  # 2^0, 2^1


class TestNonRetryableErrors:
    """Test errors that should not trigger retries."""

    @pytest.mark.asyncio
    async def test_non_retryable_401_raises_immediately(self):
        """401 error → no retry, raise immediately."""
        client = TavilyClient(api_key="test-key")

        with patch.object(client, "_cb_check_before_call", new_callable=AsyncMock, return_value=True):
            with patch.object(client, "_do_search", new_callable=AsyncMock) as mock_do_search:
                mock_do_search.side_effect = TavilyApiError("Invalid API key", status_code=401)

                with pytest.raises(TavilyApiError) as exc_info:
                    await client.search(query="test query")

                assert exc_info.value.status_code == 401
                # Should only be called once, no retries
                assert mock_do_search.call_count == 1

    @pytest.mark.asyncio
    async def test_non_retryable_429_raises_immediately(self):
        """429 error → no retry, raise immediately."""
        client = TavilyClient(api_key="test-key")

        with patch.object(client, "_cb_check_before_call", new_callable=AsyncMock, return_value=True):
            with patch.object(client, "_do_search", new_callable=AsyncMock) as mock_do_search:
                mock_do_search.side_effect = TavilyApiError("Rate limit exceeded", status_code=429)

                with pytest.raises(TavilyApiError) as exc_info:
                    await client.search(query="test query")

                assert exc_info.value.status_code == 429
                assert mock_do_search.call_count == 1

    @pytest.mark.asyncio
    async def test_non_retryable_400_raises_immediately(self):
        """400 error → no retry, raise immediately."""
        client = TavilyClient(api_key="test-key")

        with patch.object(client, "_cb_check_before_call", new_callable=AsyncMock, return_value=True):
            with patch.object(client, "_do_search", new_callable=AsyncMock) as mock_do_search:
                mock_do_search.side_effect = TavilyApiError("Bad request", status_code=400)

                with pytest.raises(TavilyApiError) as exc_info:
                    await client.search(query="test query")

                assert exc_info.value.status_code == 400
                assert mock_do_search.call_count == 1


class TestRetryThenSuccess:
    """Test retry followed by eventual success."""

    @pytest.mark.asyncio
    async def test_retry_then_success(self):
        """2 failures then success → returns result."""
        client = TavilyClient(api_key="test-key")

        sleep_times = []

        async def mock_sleep(seconds):
            sleep_times.append(seconds)

        with patch.object(client, "_cb_check_before_call", new_callable=AsyncMock, return_value=True):
            with patch.object(client, "_do_search", new_callable=AsyncMock) as mock_do_search:
                mock_do_search.side_effect = [
                    TavilyApiError("Server error", status_code=500),
                    TavilyApiError("Server error", status_code=500),
                    {"results": [{"title": "Found"}], "answer": "Success!"},
                ]

                with patch("asyncio.sleep", side_effect=mock_sleep):
                    with patch.object(client, "_cb_on_success", new_callable=AsyncMock):
                        result = await client.search(query="test query")

                        assert result["answer"] == "Success!"
                        assert mock_do_search.call_count == 3
                        assert sleep_times == [1, 2]


class TestNetworkErrorRetry:
    """Test network error triggers retry."""

    @pytest.mark.asyncio
    async def test_network_error_retries(self):
        """aiohttp.ClientError triggers retry."""
        import aiohttp

        client = TavilyClient(api_key="test-key")

        sleep_times = []

        async def mock_sleep(seconds):
            sleep_times.append(seconds)

        with patch.object(client, "_cb_check_before_call", new_callable=AsyncMock, return_value=True):
            with patch.object(client, "_do_search", new_callable=AsyncMock) as mock_do_search:
                # Network error then success
                mock_do_search.side_effect = [
                    aiohttp.ClientError("Connection refused"),
                    aiohttp.ClientError("Connection refused"),
                    {"results": [], "answer": "success"},
                ]

                with patch("asyncio.sleep", side_effect=mock_sleep):
                    with patch.object(client, "_cb_on_success", new_callable=AsyncMock):
                        result = await client.search(query="test query")

                        assert result["answer"] == "success"
                        assert mock_do_search.call_count == 3
                        assert sleep_times == [1, 2]

    @pytest.mark.asyncio
    async def test_network_error_all_failures_raises(self):
        """Network error all retries fail → raises TavilyApiError."""
        import aiohttp

        client = TavilyClient(api_key="test-key")

        sleep_times = []

        async def mock_sleep(seconds):
            sleep_times.append(seconds)

        with patch.object(client, "_cb_check_before_call", new_callable=AsyncMock, return_value=True):
            with patch.object(client, "_do_search", new_callable=AsyncMock) as mock_do_search:
                mock_do_search.side_effect = aiohttp.ClientError("Connection refused")

                with patch("asyncio.sleep", side_effect=mock_sleep):
                    with patch.object(client, "_cb_on_failure", new_callable=AsyncMock):
                        with pytest.raises(TavilyApiError, match="Unexpected error"):
                            await client.search(query="test query")

                    assert mock_do_search.call_count == 3
                    assert sleep_times == [1, 2]
