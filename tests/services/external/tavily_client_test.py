"""
Unit tests for TavilyClient.

Tests initialization, configuration checks, search payload construction,
validation, SearchResult dataclass, and _safe_decode helper.
"""
import sys
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from twin.shared.external.tavily_client import (
    TavilyClient,
    TavilyApiError,
    SearchResult,
    _safe_decode,
)
from twin.shared.config.settings import Config


class TestTavilyClientInit:
    """Test TavilyClient initialization."""

    def test_init_default_config(self):
        """TavilyClient init uses Config defaults when no args provided."""
        client = TavilyClient()

        assert client.api_key == Config.TAVILY_API_KEY
        assert client.api_url == Config.TAVILY_API_URL
        assert client.max_results == Config.TAVILY_MAX_RESULTS
        assert client.search_depth == Config.TAVILY_SEARCH_DEPTH
        assert client.timeout == Config.TAVILY_TIMEOUT

    def test_init_overrides(self):
        """TavilyClient init uses provided overrides."""
        client = TavilyClient(
            api_key="test-key",
            api_url="https://custom.api.com",
            max_results=10,
            search_depth="advanced",
            timeout=60,
        )

        assert client.api_key == "test-key"
        assert client.api_url == "https://custom.api.com"
        assert client.max_results == 10
        assert client.search_depth == "advanced"
        assert client.timeout == 60


class TestTavilyClientIsConfigured:
    """Test TavilyClient.is_configured()."""

    def test_is_configured_true(self):
        """API key set → is_configured() returns True."""
        client = TavilyClient(api_key="some-api-key")
        assert client.is_configured() is True

    def test_is_configured_false(self):
        """No API key → is_configured() returns False."""
        with patch.object(Config, "TAVILY_API_KEY", None):
            client = TavilyClient()
            assert client.is_configured() is False


class TestTavilyClientSearch:
    """Test TavilyClient.search()."""

    @pytest.mark.asyncio
    async def test_search_new_params_in_payload(self):
        """Verify topic, include_domains, exclude_domains, time_range are in the payload."""
        client = TavilyClient(api_key="test-key")

        with patch.object(client, "_do_search", new_callable=AsyncMock) as mock_do_search:
            mock_do_search.return_value = {"results": [], "answer": "test"}
            # Also mock circuit breaker to allow call through
            with patch.object(client, "_cb_check_before_call", new_callable=AsyncMock, return_value=True):
                with patch.object(client, "_cb_on_success", new_callable=AsyncMock):
                    await client.search(
                        query="test query",
                        topic="news",
                        include_domains=["example.com"],
                        exclude_domains=["spam.com"],
                        time_range="week",
                    )

                    call_args = mock_do_search.call_args
                    payload = call_args[0][2]  # Third positional arg is payload

                    assert payload["topic"] == "news"
                    assert payload["include_domains"] == ["example.com"]
                    assert payload["exclude_domains"] == ["spam.com"]
                    assert payload["time_range"] == "week"

    @pytest.mark.asyncio
    async def test_search_empty_query_raises(self):
        """Empty query → TavilyApiError."""
        client = TavilyClient(api_key="test-key")

        with pytest.raises(TavilyApiError, match="empty"):
            await client.search(query="")

    @pytest.mark.asyncio
    async def test_search_whitespace_query_raises(self):
        """Whitespace-only query → TavilyApiError."""
        client = TavilyClient(api_key="test-key")

        with pytest.raises(TavilyApiError, match="empty"):
            await client.search(query="   ")

    @pytest.mark.asyncio
    async def test_search_not_configured_raises(self):
        """No API key → TavilyApiError."""
        with patch.object(Config, "TAVILY_API_KEY", None):
            client = TavilyClient()

            with pytest.raises(TavilyApiError, match="not configured"):
                await client.search(query="test query")


class TestSearchResult:
    """Test SearchResult dataclass."""

    def test_search_result_dataclass_creation(self):
        """SearchResult dataclass can be created."""
        sources = [
            {"title": "Test", "url": "https://example.com", "content": "Content", "score": 0.9}
        ]
        result = SearchResult(
            query="test query",
            answer="Test answer",
            sources=sources,
            topic="general",
            time_range="week",
            result_count=1,
        )

        assert result.query == "test query"
        assert result.answer == "Test answer"
        assert len(result.sources) == 1
        assert result.sources[0]["title"] == "Test"
        assert result.topic == "general"
        assert result.time_range == "week"
        assert result.result_count == 1

    def test_search_result_with_none_fields(self):
        """SearchResult can have None fields."""
        result = SearchResult(
            query="test",
            answer=None,
            sources=[],
            topic=None,
            time_range=None,
            result_count=0,
        )

        assert result.answer is None
        assert result.topic is None
        assert result.time_range is None
        assert result.result_count == 0


class TestSafeDecode:
    """Test _safe_decode helper function."""

    def test_safe_decode_none(self):
        """_safe_decode(None, 'default') returns 'default'."""
        assert _safe_decode(None, "default") == "default"

    def test_safe_decode_bytes(self):
        """_safe_decode(b'test', 'default') returns 'test'."""
        assert _safe_decode(b"test", "default") == "test"

    def test_safe_decode_str(self):
        """_safe_decode('test', 'default') returns 'test'."""
        assert _safe_decode("test", "default") == "test"

    def test_safe_decode_int(self):
        """_safe_decode(42, 'default') returns '42'."""
        assert _safe_decode(42, "default") == "42"
