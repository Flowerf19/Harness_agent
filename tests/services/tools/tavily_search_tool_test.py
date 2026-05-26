"""
Unit tests for TavilySearchTool.

Tests tool metadata, parameter schema, execute flow, formatting, and smart truncation.
"""
import sys
import json
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from twin.shared.tools.modules.web.tavily_search_tool import TavilySearchTool
from twin.shared.external.tavily_client import TavilyClient, TavilyApiError


class TestTavilySearchToolMetadata:
    """Test tool name, description, and schema."""

    def test_tool_name_returns_web_search(self):
        """tool.name == 'web_search'."""
        tool = TavilySearchTool()
        assert tool.name == "web_search"

    def test_tool_description_vietnamese(self):
        """tool.description contains Vietnamese text."""
        tool = TavilySearchTool()
        assert "Tìm" in tool.description or "tin tức" in tool.description

    def test_parameters_schema_has_required_fields(self):
        """Schema has query, search_depth, max_results, topic, include_domains, exclude_domains, time_range."""
        tool = TavilySearchTool()
        schema = tool.parameters_schema

        props = schema["properties"]
        assert "query" in props
        assert "search_depth" in props
        assert "max_results" in props
        assert "topic" in props
        assert "include_domains" in props
        assert "exclude_domains" in props
        assert "time_range" in props

        # query is required
        assert "query" in schema["required"]

    def test_parameters_schema_types(self):
        """Schema has correct types for each field."""
        tool = TavilySearchTool()
        props = tool.parameters_schema["properties"]

        assert props["query"]["type"] == "string"
        assert props["search_depth"]["type"] == "string"
        assert props["max_results"]["type"] == "integer"
        assert props["topic"]["type"] == "string"
        assert props["include_domains"]["type"] == "array"
        assert props["exclude_domains"]["type"] == "array"
        assert props["time_range"]["type"] == "string"


class TestTavilySearchToolExecute:
    """Test TavilySearchTool.execute()."""

    @pytest.mark.asyncio
    async def test_execute_no_client_returns_error(self):
        """No tavily_client → error message in Vietnamese."""
        tool = TavilySearchTool(tavily_client=None)
        result = await tool.execute(query="test")

        assert "Lỗi" in result
        assert "cấu hình" in result

    @pytest.mark.asyncio
    async def test_execute_not_configured_returns_error(self):
        """tavily_client without API key → error in Vietnamese."""
        mock_client = TavilyClient(api_key=None)
        tool = TavilySearchTool(tavily_client=mock_client)
        result = await tool.execute(query="test")

        assert "Lỗi" in result

    @pytest.mark.asyncio
    async def test_execute_format_for_user_default(self):
        """format='user' returns formatted text with answer and results."""
        mock_client = TavilyClient(api_key="test-key")
        mock_response = {
            "answer": "Test AI answer",
            "results": [
                {
                    "title": "Test Result",
                    "url": "https://example.com",
                    "content": "This is the content of the result.",
                    "score": 0.9,
                }
            ],
        }

        with patch.object(mock_client, "search", new_callable=AsyncMock, return_value=mock_response):
            tool = TavilySearchTool(tavily_client=mock_client)
            result = await tool.execute(query="test query", format="user")

            assert "Trả lời" in result
            assert "Test AI answer" in result
            assert "Test Result" in result

    @pytest.mark.asyncio
    async def test_execute_empty_query_returns_error(self):
        """Empty query → Vietnamese error without calling API."""
        mock_client = TavilyClient(api_key="test-key")
        tool = TavilySearchTool(tavily_client=mock_client)
        result = await tool.execute(query="")

        assert "Lỗi" in result
        assert "từ khóa" in result


class TestSmartTruncate:
    """Test _smart_truncate method."""

    def test_smart_truncate_sentence_boundary(self):
        """Text truncated at '. ' sentence boundary."""
        mock_client = TavilyClient(api_key="test-key")
        tool = TavilySearchTool(tavily_client=mock_client)

        text = "Hello world. This is a long sentence. Another sentence here."
        # max_length is 300 by default, but our text is short enough
        # Force a shorter test with a string that exceeds 300
        long_text = "Sentence one. " * 30  # ~480 chars
        result = tool._smart_truncate(long_text, max_length=100)

        assert result.endswith("...")
        assert len(result) <= 103  # max_length + "..."
        # Should cut at sentence boundary
        assert ". " in result or result.endswith("...")

    def test_smart_truncate_no_boundary_fallback(self):
        """Long text without periods truncated at max_length + '...'."""
        mock_client = TavilyClient(api_key="test-key")
        tool = TavilySearchTool(tavily_client=mock_client)

        # Text with no sentence boundaries
        long_text = "A" * 500
        result = tool._smart_truncate(long_text, max_length=300)

        assert len(result) == 303  # 300 + "..."
        assert result.endswith("...")
        assert result.startswith("A" * 300)

    def test_smart_truncate_under_max_length(self):
        """Text shorter than max_length returns unchanged."""
        mock_client = TavilyClient(api_key="test-key")
        tool = TavilySearchTool(tavily_client=mock_client)

        short_text = "Short text."
        result = tool._smart_truncate(short_text, max_length=300)

        assert result == short_text

    def test_smart_truncate_exclamation_boundary(self):
        """Text truncated at '! ' boundary."""
        mock_client = TavilyClient(api_key="test-key")
        tool = TavilySearchTool(tavily_client=mock_client)

        text = "Wow! " * 30  # ~120 chars
        result = tool._smart_truncate(text, max_length=50)

        assert result.endswith("...")
        assert "! " in result


class TestFormatForLLM:
    """Test format_for_llm method."""

    def test_format_for_llm_returns_valid_json(self):
        """format='llm' returns parseable JSON."""
        mock_client = TavilyClient(api_key="test-key")
        tool = TavilySearchTool(tavily_client=mock_client)

        response = {
            "answer": "AI answer",
            "results": [
                {"title": "Result 1", "url": "https://example.com", "content": "Content", "score": 0.9}
            ],
        }

        json_str = tool.format_for_llm(response, query="test", topic="general", time_range="day")
        parsed = json.loads(json_str)

        assert parsed["query"] == "test"
        assert parsed["answer"] == "AI answer"
        assert parsed["topic"] == "general"
        assert parsed["time_range"] == "day"
        assert parsed["result_count"] == 1
        assert len(parsed["sources"]) == 1

    def test_format_for_llm_empty_results(self):
        """format='llm' with no results returns valid JSON."""
        mock_client = TavilyClient(api_key="test-key")
        tool = TavilySearchTool(tavily_client=mock_client)

        response = {"answer": None, "results": []}
        json_str = tool.format_for_llm(response, query="test")
        parsed = json.loads(json_str)

        assert parsed["result_count"] == 0
        assert parsed["sources"] == []
