"""
Unit tests for SearchOrchestrator.

Tests initialization, auto mode (T2 → web fallback), t2-only mode,
web-only mode, merge_results, and empty query handling.
"""
import sys
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from twin.shared.external.search_orchestrator import SearchOrchestrator
from twin.shared.external.tavily_client import SearchResult


class TestSearchOrchestratorInit:
    """Test SearchOrchestrator initialization."""

    def test_init_all_none(self):
        """SearchOrchestrator with all None services."""
        orchestrator = SearchOrchestrator()

        assert orchestrator.memory is None
        assert orchestrator.tavily_client is None


class TestSearchOrchestratorAutoMode:
    """Test auto mode fallback chain: T2 → Web → error."""

    @pytest.mark.asyncio
    async def test_auto_mode_T2_returns_results(self):
        """T2 returns results → web NOT called."""
        mock_T2_page = MagicMock()
        mock_T2_page.canonical_topic = "Test_Topic"
        mock_T2_page.category = "test"
        mock_T2_page.current_summary = "Test summary"
        mock_T2_page.key_points = ["point1"]
        mock_T2_page.importance = 4

        memory_manager = AsyncMock()
        memory_manager.search_pages = AsyncMock(return_value=[mock_T2_page])

        mock_tavily = MagicMock()

        orchestrator = SearchOrchestrator(
            memory_manager=memory_manager,
            tavily_client=mock_tavily,
        )

        result = await orchestrator.search(user_id="123", query="test query", mode="auto")

        assert "Test_Topic" in result
        memory_manager.search_pages.assert_called_once()
        # Tavily should NOT be called since T2 returned results
        assert not mock_tavily.search.called if hasattr(mock_tavily, "search") else True

    @pytest.mark.asyncio
    async def test_auto_mode_web_fallback(self):
        """T2 empty → web IS called."""
        memory_manager = AsyncMock()
        memory_manager.search_pages = AsyncMock(return_value=[])

        mock_tavily_client = MagicMock()
        mock_tavily_client.is_configured.return_value = True
        mock_tavily_client.search = AsyncMock(return_value={
            "answer": "Web answer",
            "results": [{"title": "Web Result", "url": "https://example.com", "content": "Content", "score": 0.9}],
            "query_context": {"topic": "general"},
        })

        orchestrator = SearchOrchestrator(
            memory_manager=memory_manager,
            tavily_client=mock_tavily_client,
        )

        result = await orchestrator.search(user_id="123", query="test query", mode="auto")

        assert "Web" in result or "example.com" in result
        mock_tavily_client.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_mode_both_fail_returns_error(self):
        """Both T2 and web fail → Vietnamese error message."""
        memory_manager = AsyncMock()
        memory_manager.search_pages = AsyncMock(side_effect=Exception("T2 error"))

        mock_tavily_client = MagicMock()
        mock_tavily_client.is_configured.return_value = True
        mock_tavily_client.search = AsyncMock(side_effect=Exception("Web error"))

        orchestrator = SearchOrchestrator(
            memory_manager=memory_manager,
            tavily_client=mock_tavily_client,
        )

        result = await orchestrator.search(user_id="123", query="test query", mode="auto")

        assert "Không tìm thấy" in result


class TestSearchOrchestratorT2OnlyMode:
    """Test t2-only mode."""

    @pytest.mark.asyncio
    async def test_T2_only_mode(self):
        """mode='t2' only calls T2."""
        mock_T2_page = MagicMock()
        mock_T2_page.canonical_topic = "Test_Topic"
        mock_T2_page.category = "test"
        mock_T2_page.current_summary = "Test summary"
        mock_T2_page.key_points = []
        mock_T2_page.importance = 3

        memory_manager = AsyncMock()
        memory_manager.search_pages = AsyncMock(return_value=[mock_T2_page])

        mock_tavily_client = MagicMock()

        orchestrator = SearchOrchestrator(
            memory_manager=memory_manager,
            tavily_client=mock_tavily_client,
        )

        result = await orchestrator.search(user_id="123", query="test query", mode="t2")

        assert "Test_Topic" in result
        memory_manager.search_pages.assert_called_once()


class TestSearchOrchestratorWebOnlyMode:
    """Test web-only mode."""

    @pytest.mark.asyncio
    async def test_web_only_mode(self):
        """mode='web' only calls web."""
        mock_tavily_client = MagicMock()
        mock_tavily_client.is_configured.return_value = True
        mock_tavily_client.search = AsyncMock(return_value={
            "answer": "Web answer",
            "results": [{"title": "Result", "url": "https://example.com", "content": "Content", "score": 0.9}],
            "query_context": None,
        })

        orchestrator = SearchOrchestrator(tavily_client=mock_tavily_client)

        result = await orchestrator.search(user_id="123", query="test query", mode="web")

        assert "Web" in result or "Result" in result
        mock_tavily_client.search.assert_called_once()


class TestMergeResults:
    """Test merge_results method."""

    def test_merge_results_T2_and_web(self):
        """merge_results() combines both result sets."""
        orchestrator = SearchOrchestrator()

        mock_T2_page = MagicMock()
        mock_T2_page.canonical_topic = "T2_Topic"
        mock_T2_page.category = "T2"
        mock_T2_page.current_summary = "T2 summary"
        mock_T2_page.key_points = ["point1"]
        mock_T2_page.importance = 4

        web_result = SearchResult(
            query="test",
            answer="Web answer",
            sources=[{"title": "Web Source", "url": "https://example.com", "content": "Content", "score": 0.9}],
            topic="general",
            time_range="day",
            result_count=1,
        )

        merged = orchestrator.merge_results(t2_results=[mock_T2_page], web_result=web_result)

        assert "T2 Memory" in merged
        assert "Web Search" in merged
        assert "T2_Topic" in merged
        assert "Web Source" in merged

    def test_merge_results_T2_only(self):
        """merge_results() with only T2 results."""
        orchestrator = SearchOrchestrator()

        mock_T2_page = MagicMock()
        mock_T2_page.canonical_topic = "Topic"
        mock_T2_page.category = "cat"
        mock_T2_page.current_summary = "Summary"
        mock_T2_page.key_points = []
        mock_T2_page.importance = 3

        merged = orchestrator.merge_results(t2_results=[mock_T2_page], web_result=None)

        assert "T2 Memory" in merged
        assert "Web Search" not in merged

    def test_merge_results_web_only(self):
        """merge_results() with only web results."""
        orchestrator = SearchOrchestrator()

        web_result = SearchResult(
            query="test",
            answer="Answer",
            sources=[{"title": "Source", "url": "https://example.com", "content": "Content", "score": 0.9}],
            topic=None,
            time_range=None,
            result_count=1,
        )

        merged = orchestrator.merge_results(t2_results=[], web_result=web_result)

        assert "Web Search" in merged
        assert "T2 Memory" not in merged


class TestEmptyQuery:
    """Test empty query handling."""

    @pytest.mark.asyncio
    async def test_empty_query_returns_error(self):
        """Empty query → Vietnamese error."""
        orchestrator = SearchOrchestrator()

        result = await orchestrator.search(user_id="123", query="", mode="auto")

        assert "Lỗi" in result
        assert "query" in result.lower() or "Tìm kiếm" in result

    @pytest.mark.asyncio
    async def test_whitespace_query_returns_error(self):
        """Whitespace-only query → Vietnamese error."""
        orchestrator = SearchOrchestrator()

        result = await orchestrator.search(user_id="123", query="   ", mode="auto")

        assert "Lỗi" in result


class TestInvalidMode:
    """Test invalid mode handling."""

    @pytest.mark.asyncio
    async def test_invalid_mode_returns_error(self):
        """Invalid mode → Vietnamese error."""
        orchestrator = SearchOrchestrator()

        result = await orchestrator.search(user_id="123", query="test", mode="invalid")

        assert "Lỗi" in result
        assert "invalid" in result.lower()
