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
from typing import Dict, Any, Optional

from src.services.tools.base_tool import BaseTool, ToolExecutionError
from src.services.external.tavily_client import TavilyClient, TavilyApiError

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
        logger.info(f"TavilySearchTool initialized - client: {tavily_client is not None}")

    # ==========================================
    # BASE TOOL PROPERTIES
    # ==========================================

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Tìm kiếm thông tin real-time trên internet. "
            "Dùng khi cần thông tin mới nhất, tin tức, sự kiện hiện tại, "
            "hoặc kiến thức ngoài training data. "
            "Ví dụ: 'tin tức AI hôm nay', 'giá Bitcoin hiện tại', 'thời tiết Hà Nội'."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Từ khóa hoặc câu hỏi để tìm kiếm. VD: 'tin tức AI 2024', 'cách nấu phở'"
                },
                "search_depth": {
                    "type": "string",
                    "enum": ["basic", "advanced"],
                    "description": "Độ sâu tìm kiếm. 'basic' nhanh, 'advanced' chi tiết hơn. Mặc định: 'basic'"
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "description": "Số kết quả tối đa trả về. Mặc định: 5"
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
    ) -> str:
        """
        Execute web search via Tavily API.

        Args:
            query: Search query string
            search_depth: "basic" or "advanced"
            max_results: Number of results (1-10)

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

        # Execute search
        try:
            logger.info(f"🌐 Web search: query='{query[:50]}...', depth={search_depth}")

            response = await self.tavily_client.search(
                query=query.strip(),
                search_depth=search_depth,
                max_results=max_results,
                include_answer=True,
            )

            # Format results
            return self._format_results(response)

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
                # Truncate long content
                if len(content) > 300:
                    content = content[:300] + "..."
                lines.append(f"   📝 {content}")
            lines.append("")

        return "\n".join(lines).strip()

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