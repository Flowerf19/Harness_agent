"""
Unit tests for TavilySearchTool.

Tests tool metadata, parameter schema, execute flow, formatting, and smart truncation.
"""
import sys
import json
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from twin.shared.tools.modules.web.tavily_search_tool import TavilySearchTool, TavilyApiError


class FakeMCPClient:
    def __init__(self, result_text):
        self.result_text = result_text
        self.calls = []

    async def call_tool(self, tool_name, arguments, timeout=None):
        self.calls.append((tool_name, arguments, timeout))
        return self.result_text


class TestTavilySearchToolMetadata:
    """Test tool name, description, and schema."""

    def test_tool_name_returns_web_search(self):
        """tool.name == 'web_search'."""
        tool = TavilySearchTool()
        assert tool.name == "web_search"

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
        """No Tavily MCP client → error message in Vietnamese."""
        tool = TavilySearchTool()
        result = await tool.execute(query="test")

        assert "Lỗi" in result
        assert "cấu hình" in result

    @pytest.mark.asyncio
    async def test_execute_format_for_user_default(self):
        """format='user' returns formatted text with answer and results."""
        fake_mcp_client = FakeMCPClient(
            """Answer: Test AI answer
Detailed Results:

Title: Test Result
URL: https://example.com
Content: This is the content of the result.
"""
        )
        tool = TavilySearchTool(tavily_mcp_client=fake_mcp_client)
        result = await tool.execute(query="test query", format="user")

        assert "Trả lời" in result
        assert "Test AI answer" in result
        assert "Test Result" in result

    @pytest.mark.asyncio
    async def test_execute_empty_query_returns_error(self):
        """Empty query → Vietnamese error without calling API."""
        fake_mcp_client = FakeMCPClient("")
        tool = TavilySearchTool(tavily_mcp_client=fake_mcp_client)
        result = await tool.execute(query="")

        assert "Lỗi" in result
        assert "từ khóa" in result
        assert fake_mcp_client.calls == []

    @pytest.mark.asyncio
    async def test_execute_uses_mcp_backend_and_preserves_requested_max_results(self):
        """MCP backend calls tavily_search and trims results to public max_results."""
        mcp_text = """Answer: Test answer
Detailed Results:

Title: First
URL: https://example.com/1
Content: First content

Title: Second
URL: https://example.com/2
Content: Second content
"""
        fake_mcp_client = FakeMCPClient(mcp_text)
        tool = TavilySearchTool(tavily_mcp_client=fake_mcp_client)

        result = await tool.execute(query="test query", max_results=1, format="llm")
        parsed = json.loads(result)

        assert parsed["answer"] == "Test answer"
        assert parsed["result_count"] == 1
        assert parsed["sources"] == [
            {
                "title": "First",
                "url": "https://example.com/1",
                "content": "First content",
                "score": 0,
            }
        ]
        assert fake_mcp_client.calls == [
            (
                "tavily_search",
                {
                    "query": "test query",
                    "search_depth": "basic",
                    "max_results": 5,
                },
                30,
            )
        ]

    def test_build_mcp_arguments_maps_news_to_time_range_without_remote_topic(self):
        tool = TavilySearchTool()

        arguments = tool._build_mcp_arguments(
            query="ai news",
            search_depth="advanced",
            max_results=10,
            topic="news",
            include_domains=["example.com"],
            exclude_domains=None,
            time_range=None,
        )

        assert arguments == {
            "query": "ai news",
            "search_depth": "advanced",
            "max_results": 10,
            "time_range": "week",
            "include_domains": ["example.com"],
        }


class TestSmartTruncate:
    """Test _smart_truncate method."""

    def test_smart_truncate_sentence_boundary(self):
        """Text truncated at '. ' sentence boundary."""
        tool = TavilySearchTool()

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
        tool = TavilySearchTool()

        # Text with no sentence boundaries
        long_text = "A" * 500
        result = tool._smart_truncate(long_text, max_length=300)

        assert len(result) == 303  # 300 + "..."
        assert result.endswith("...")
        assert result.startswith("A" * 300)

    def test_smart_truncate_under_max_length(self):
        """Text shorter than max_length returns unchanged."""
        tool = TavilySearchTool()

        short_text = "Short text."
        result = tool._smart_truncate(short_text, max_length=300)

        assert result == short_text

    def test_smart_truncate_exclamation_boundary(self):
        """Text truncated at '! ' boundary."""
        tool = TavilySearchTool()

        text = "Wow! " * 30  # ~120 chars
        result = tool._smart_truncate(text, max_length=50)

        assert result.endswith("...")
        assert "! " in result


class TestFormatForLLM:
    """Test format_for_llm method."""

    def test_format_for_llm_returns_valid_json(self):
        """format='llm' returns parseable JSON."""
        tool = TavilySearchTool()

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
        tool = TavilySearchTool()

        response = {"answer": None, "results": []}
        json_str = tool.format_for_llm(response, query="test")
        parsed = json.loads(json_str)

        assert parsed["result_count"] == 0
        assert parsed["sources"] == []
