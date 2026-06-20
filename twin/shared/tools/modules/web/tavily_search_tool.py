"""
TavilySearchTool - Web Search Tool.

Tool for searching the web via Tavily remote MCP.
Provides real-time web search capabilities for the AI agent.

Architecture:
- Inherits from BaseTool
- Uses Tavily MCP as the remote backend
- Graceful degradation when API unavailable
"""

import logging
import json
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

from twin.shared.tools.registry.base import BaseTool, ToolExecutionError
from twin.shared.tools.mcp_client import MCPClient

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Structured search result for LLM consumption."""
    query: str
    answer: Optional[str]
    sources: List[dict]
    topic: Optional[str]
    time_range: Optional[str]
    result_count: int


class TavilyApiError(Exception):
    """Exception raised when Tavily MCP search fails."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        original_error: Optional[Exception] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.original_error = original_error
        super().__init__(f"Tavily MCP Error: {message}")


class TavilySearchTool(BaseTool):
    """
    Web Search Tool using Tavily.

    Searches the web for real-time information.
    Useful for current events, facts, or topics not in training data.

    Attributes:
        tavily_mcp_client: MCPClient instance for Tavily remote MCP calls.

    Example:
        tool = TavilySearchTool(tavily_mcp_client)
        result = await tool.execute(query="latest AI news")
    """

    def __init__(
        self,
        tavily_mcp_client: Optional[MCPClient] = None,
    ):
        """
        Initialize TavilySearchTool.

        Args:
            tavily_mcp_client: Remote MCP client for Tavily MCP execution.
        """
        self.tavily_mcp_client = tavily_mcp_client
        logger.debug(
            "TavilySearchTool initialized - mcp_client=%s",
            tavily_mcp_client is not None,
        )

    # ==========================================
    # BASE TOOL PROPERTIES
    # ==========================================

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Truy vấn tìm kiếm."
                },
                "search_depth": {
                    "type": "string",
                    "enum": ["basic", "advanced"],
                    "description": "basic hoặc advanced."
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "description": "Số kết quả, 1-10."
                },
                "topic": {
                    "type": "string",
                    "enum": ["general", "news"],
                    "description": "general hoặc news."
                },
                "include_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Domain được phép."
                },
                "exclude_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Domain loại trừ."
                },
                "time_range": {
                    "type": "string",
                    "enum": ["day", "week", "month", "year"],
                    "description": "day, week, month, year."
                }
            },
            "required": ["query"]
        }

    # ==========================================
    # EXECUTION
    # ==========================================

    async def execute(
        self,
        query: str,
        search_depth: str = "basic",
        max_results: int = 5,
        topic: Optional[str] = None,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        time_range: Optional[str] = None,
        format: str = "user",
    ) -> str:
        """
        Execute web search via Tavily MCP.

        Args:
            query: Search query string
            search_depth: "basic" or "advanced"
            max_results: Number of results (1-10)
            topic: "general" or "news"
            include_domains: Whitelist domains
            exclude_domains: Blacklist domains
            time_range: "day", "week", "month", "year"
            format: Output format - "user" for human-readable, "llm" for JSON

        Returns:
            str: Formatted search results or error message
        """
        # Validate query
        if not query or not query.strip():
            return "Lỗi: Vui lòng nhập từ khóa tìm kiếm."

        # Validate parameters
        if search_depth not in ["basic", "advanced"]:
            search_depth = "basic"

        max_results = max(1, min(10, max_results))  # Clamp to 1-10

        if format not in ["user", "llm"]:
            format = "user"

        try:
            logger.debug(f"🌐 Web search: query='{query[:50]}...', depth={search_depth}")

            response = await self._search_with_mcp(
                query=query.strip(),
                search_depth=search_depth,
                max_results=max_results,
                topic=topic,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
                time_range=time_range,
            )

            # Format results based on requested format
            if format == "llm":
                return self.format_for_llm(response, query, topic, time_range)
            else:
                return self.format_for_user(response)

        except TavilyApiError as e:
            logger.error(f"Tavily MCP error: {e.message}")
            return f"Lỗi tìm kiếm: {self._user_friendly_error(e)}"

        except Exception as e:
            logger.error(f"Unexpected error in TavilySearchTool: {e}")
            raise ToolExecutionError(self.name, f"Lỗi không xác định: {e}", original_error=e)

    async def _search_with_mcp(
        self,
        *,
        query: str,
        search_depth: str,
        max_results: int,
        topic: Optional[str],
        include_domains: Optional[List[str]],
        exclude_domains: Optional[List[str]],
        time_range: Optional[str],
    ) -> Dict[str, Any]:
        if not self.tavily_mcp_client:
            raise TavilyApiError("Tavily MCP client not configured")

        result_text = await self.tavily_mcp_client.call_tool(
            "tavily_search",
            self._build_mcp_arguments(
                query=query,
                search_depth=search_depth,
                max_results=max_results,
                topic=topic,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
                time_range=time_range,
            ),
            timeout=30,
        )
        return self._normalize_mcp_response(
            self._parse_mcp_result(result_text),
            max_results=max_results,
        )

    def _build_mcp_arguments(
        self,
        *,
        query: str,
        search_depth: str,
        max_results: int,
        topic: Optional[str],
        include_domains: Optional[List[str]],
        exclude_domains: Optional[List[str]],
        time_range: Optional[str],
    ) -> Dict[str, Any]:
        arguments: Dict[str, Any] = {
            "query": query,
            "search_depth": search_depth,
            # Tavily MCP currently enforces max_results >= 5.
            "max_results": max(5, min(20, max_results)),
        }
        if topic == "news":
            arguments["time_range"] = time_range or "week"
        elif topic:
            arguments["topic"] = "general"
        if include_domains:
            arguments["include_domains"] = include_domains
        if exclude_domains:
            arguments["exclude_domains"] = exclude_domains
        if time_range:
            arguments["time_range"] = time_range
        return arguments

    def _parse_mcp_result(self, result_text: str) -> Dict[str, Any]:
        if not result_text:
            return {"answer": None, "results": []}
        if result_text.startswith("Lỗi:") or result_text.startswith("Tavily API error:"):
            raise TavilyApiError(result_text)
        try:
            data = json.loads(result_text)
        except json.JSONDecodeError:
            return self._parse_tavily_mcp_text(result_text)
        if not isinstance(data, dict):
            return {"answer": None, "results": []}
        return data

    def _parse_tavily_mcp_text(self, result_text: str) -> Dict[str, Any]:
        answer: Optional[str] = None
        results: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None
        current_field: Optional[str] = None
        in_images = False

        for raw_line in result_text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("Answer:"):
                answer = line.removeprefix("Answer:").strip()
                current_field = None
                continue
            if line == "Detailed Results:":
                current_field = None
                continue
            if line == "Images:":
                in_images = True
                current_field = None
                continue
            if in_images:
                continue
            if line.startswith("Title:"):
                if current:
                    results.append(current)
                current = {
                    "title": line.removeprefix("Title:").strip(),
                    "url": "",
                    "content": "",
                    "score": 0,
                }
                current_field = "title"
                continue
            if current is None:
                continue
            if line.startswith("URL:"):
                current["url"] = line.removeprefix("URL:").strip()
                current_field = "url"
            elif line.startswith("Content:"):
                current["content"] = line.removeprefix("Content:").strip()
                current_field = "content"
            elif line.startswith("Raw Content:"):
                current["raw_content"] = line.removeprefix("Raw Content:").strip()
                current_field = "raw_content"
            elif line.startswith("Favicon:"):
                current["favicon"] = line.removeprefix("Favicon:").strip()
                current_field = "favicon"
            elif current_field in {"content", "raw_content"}:
                current[current_field] = f"{current[current_field]}\n{line}".strip()

        if current:
            results.append(current)
        if not answer and not results:
            return {
                "answer": None,
                "results": [
                    {
                        "title": "Tavily MCP",
                        "url": "",
                        "content": result_text,
                        "score": 0,
                    }
                ],
            }
        return {"answer": answer, "results": results}

    def _normalize_mcp_response(
        self,
        response: Dict[str, Any],
        *,
        max_results: int,
    ) -> Dict[str, Any]:
        results = response.get("results", [])
        if isinstance(results, list):
            response["results"] = results[:max_results]
        else:
            response["results"] = []
        return response

    def _format_results(self, response: Dict[str, Any]) -> str:
        """
        Format Tavily MCP response to human-readable string.

        Args:
            response: API response dict with 'answer' and 'results'

        Returns:
            str: Formatted results
        """
        lines = []

        # Add AI-generated answer if available
        answer = response.get("answer")
        if answer:
            lines.append(f"💡 **Trả lời:** {answer}")
            lines.append("")

        # Add search results
        results = response.get("results", [])
        if not results:
            return "Không tìm thấy kết quả nào."

        lines.append(f"📚 **Kết quả tìm kiếm ({len(results)}):**")
        lines.append("")

        for i, result in enumerate(results, 1):
            title = result.get("title", "Không tiêu đề")
            url = result.get("url", "")
            content = result.get("content", "")
            score = result.get("score", 0)

            lines.append(f"{i}. **{title}**")
            if url:
                lines.append(f"   🔗 {url}")
            if content:
                # Smart truncate with sentence boundary
                lines.append(f"   📝 {self._smart_truncate(content)}")
            lines.append("")

        return "\n".join(lines).strip()

    def _smart_truncate(self, text: str, max_length: int = 300) -> str:
        """
        Truncate text at sentence boundary instead of hard character cut.

        Finds last sentence boundary (`.`, `!`, `?`, `...`, newline) before
        max_length chars. Falls back to hard truncate if no boundary found.

        Args:
            text: Text to truncate
            max_length: Maximum character length

        Returns:
            str: Truncated text with "..." if truncated
        """
        if len(text) <= max_length:
            return text

        truncated = text[:max_length]

        # Find last sentence boundary
        boundaries = [". ", "! ", "? ", "...", "\n"]
        last_boundary_pos = -1
        for boundary in boundaries:
            pos = truncated.rfind(boundary)
            if pos > last_boundary_pos:
                last_boundary_pos = pos

        if last_boundary_pos > 0:
            # Include the boundary character(s)
            end_pos = last_boundary_pos + len(boundaries[0])  # use ". " length
            # Find which boundary matched and use its length
            for b in boundaries:
                if truncated.rfind(b) == last_boundary_pos:
                    end_pos = last_boundary_pos + len(b)
                    break
            return truncated[:end_pos].rstrip() + "..."
        else:
            # No sentence boundary found, hard truncate
            return truncated + "..."

    def format_for_llm(self, response: Dict[str, Any], query: str,
                       topic: Optional[str] = None,
                       time_range: Optional[str] = None) -> str:
        """
        Format search results as JSON for LLM consumption.

        Args:
            response: API response dict with 'answer' and 'results'
            query: Original search query
            topic: Search topic ("general" or "news")
            time_range: Time range ("day", "week", "month", "year")

        Returns:
            str: JSON string of SearchResult
        """
        results = response.get("results", [])
        sources = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score", 0),
            }
            for r in results
        ]

        search_result = SearchResult(
            query=query,
            answer=response.get("answer"),
            sources=sources,
            topic=topic,
            time_range=time_range,
            result_count=len(results),
        )

        return json.dumps(search_result.__dict__, ensure_ascii=False, indent=2)

    def format_for_user(self, response: Dict[str, Any]) -> str:
        """
        Format search results as human-readable Vietnamese text.

        Uses smart truncation for long content.

        Args:
            response: API response dict with 'answer' and 'results'

        Returns:
            str: Human-readable formatted text
        """
        return self._format_results(response)

    def _user_friendly_error(self, error: TavilyApiError) -> str:
        """
        Convert API error to user-friendly Vietnamese message.

        Args:
            error: TavilyApiError instance

        Returns:
            str: User-friendly error message
        """
        if error.status_code == 401:
            return "API key không hợp lệ. Vui lòng kiểm tra TAVILY_API_KEY."
        elif error.status_code == 429:
            return "Đã vượt quá giới hạn request. Vui lòng thử lại sau."
        elif "not configured" in error.message.lower():
            return "Web Search chưa được cấu hình. Vui lòng cấu hình TAVILY_API_KEY."
        elif "timeout" in error.message.lower():
            return "Không thể kết nối đến server tìm kiếm. Vui lòng thử lại."
        elif "network" in error.message.lower():
            return "Lỗi mạng. Vui lòng kiểm tra kết nối internet."
        else:
            return f"Lỗi hệ thống: {error.message}"

    def __repr__(self) -> str:
        return f"<TavilySearchTool: mcp_client={self.tavily_mcp_client is not None}>"
