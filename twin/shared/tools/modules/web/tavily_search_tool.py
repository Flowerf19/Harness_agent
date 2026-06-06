"""
TavilySearchTool - Web Search MCP Tool.

Tool for searching the web via Tavily API.
Provides real-time web search capabilities for the AI agent.

Architecture:
- Inherits from BaseTool
- Uses TavilyClient for API communication
- Graceful degradation when API unavailable
"""

import logging
import json
from typing import Dict, Any, Optional, List

from twin.shared.tools.registry.base import BaseTool, ToolExecutionError
from twin.shared.external.tavily_client import TavilyClient, TavilyApiError, SearchResult

logger = logging.getLogger(__name__)


class TavilySearchTool(BaseTool):
    """
    Web Search Tool using Tavily API.

    Searches the web for real-time information.
    Useful for current events, facts, or topics not in training data.

    Attributes:
        tavily_client: TavilyClient instance for API calls

    Example:
        tool = TavilySearchTool(tavily_client)
        result = await tool.execute(query="latest AI news")
    """

    def __init__(self, tavily_client: Optional[TavilyClient] = None):
        """
        Initialize TavilySearchTool.

        Args:
            tavily_client: TavilyClient for API calls (can be None for graceful degradation)
        """
        self.tavily_client = tavily_client
        logger.debug(f"TavilySearchTool initialized - client: {tavily_client is not None}")

    # ==========================================
    # BASE TOOL PROPERTIES
    # ==========================================

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Tìm web hiện tại."

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
        Execute web search via Tavily API.

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

        # Check if client is available
        if not self.tavily_client:
            return "Lỗi: Web Search chưa được cấu hình. Vui lòng cấu hình TAVILY_API_KEY."

        # Check if API is configured
        if not self.tavily_client.is_configured():
            return "Lỗi: Web Search chưa được kích hoạt. Vui lòng thêm TAVILY_API_KEY vào cấu hình."

        # Validate parameters
        if search_depth not in ["basic", "advanced"]:
            search_depth = "basic"

        max_results = max(1, min(10, max_results))  # Clamp to 1-10

        if format not in ["user", "llm"]:
            format = "user"

        # Execute search
        try:
            logger.debug(f"🌐 Web search: query='{query[:50]}...', depth={search_depth}")

            response = await self.tavily_client.search(
                query=query.strip(),
                search_depth=search_depth,
                max_results=max_results,
                include_answer=True,
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
            logger.error(f"Tavily API error: {e.message}")
            return f"Lỗi tìm kiếm: {self._user_friendly_error(e)}"

        except Exception as e:
            logger.error(f"Unexpected error in TavilySearchTool: {e}")
            raise ToolExecutionError(self.name, f"Lỗi không xác định: {e}", original_error=e)

    def _format_results(self, response: Dict[str, Any]) -> str:
        """
        Format Tavily API response to human-readable string.

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
        elif "timeout" in error.message.lower():
            return "Không thể kết nối đến server tìm kiếm. Vui lòng thử lại."
        elif "network" in error.message.lower():
            return "Lỗi mạng. Vui lòng kiểm tra kết nối internet."
        else:
            return f"Lỗi hệ thống: {error.message}"

    def __repr__(self) -> str:
        return f"<TavilySearchTool: client={self.tavily_client is not None}>"
