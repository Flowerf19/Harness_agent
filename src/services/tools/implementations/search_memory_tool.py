"""
SearchMemoryTool - Query Episodic Memory (T2).

Tool for searching past events and preferences from vector database.
Uses EpisodicManager for semantic search.

Migration from ToolManager._search_memory():
- Same logic, now encapsulated in a class
- Dependency injection via constructor
- Self-contained schema definition
"""

import logging
from typing import Dict, Any, Optional

from src.services.tools.base_tool import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)


class SearchMemoryTool(BaseTool):
    """
    Tool for searching Episodic Memory (T2).
    
    Searches past events, preferences, and context from vector database.
    Uses semantic search with Qwen3-Embedding-0.6B.
    
    Attributes:
        episodic_manager: EpisodicManager instance for T2 access
    
    Example:
        tool = SearchMemoryTool(episodic_manager)
        result = await tool.execute(user_id="123", query="sở thích")
    """
    
    def __init__(self, episodic_manager: Optional[Any] = None):
        """
        Initialize SearchMemoryTool.
        
        Args:
            episodic_manager: EpisodicManager (T2) for memory search
        """
        self.episodic_manager = episodic_manager
        logger.info(f"SearchMemoryTool initialized with episodic_manager={episodic_manager is not None}")
    
    # ==========================================
    # BASE TOOL PROPERTIES
    # ==========================================
    
    @property
    def name(self) -> str:
        return "search_memory"
    
    @property
    def description(self) -> str:
        return (
            "Tìm kiếm ký ức cũ của user từ Episodic Memory (T2). "
            "Dùng khi user nhắc chuyện quá khứ, hỏi về sở thích/sự kiện cũ, "
            "hoặc cần context từ lịch sử hội thoại."
        )
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "Discord user ID (số) của user đang chat. VD: '726302130318868500'"
                },
                "query": {
                    "type": "string",
                    "description": "Từ khóa hoặc câu hỏi để tìm kiếm trong ký ức. VD: 'sở thích', 'chuyện hôm qua'"
                }
            },
            "required": ["user_id", "query"]
        }
    
    # ==========================================
    # EXECUTION
    # ==========================================
    
    async def execute(self, user_id: str, query: str) -> str:
        """
        Search Episodic Memory for past context.
        
        Args:
            user_id: Discord user ID (must be numeric)
            query: Search query string
            
        Returns:
            str: Search results or error message
        """
        # Validate inputs
        if not user_id or not query:
            return "Lỗi: Thiếu user_id hoặc query."
        
        # Validate user_id format (Discord ID must be numeric)
        if not user_id.isdigit():
            logger.warning(f"⚠️ Invalid user_id: {user_id} - không phải số")
            return f"Lỗi: user_id '{user_id}' không hợp lệ. user_id phải là số ID của Discord user."
        
        # Check if episodic_manager is available
        if not self.episodic_manager:
            return "Lỗi: Hệ thống Episodic Memory chưa sẵn sàng."
        
        # Execute search
        try:
            results = await self.episodic_manager.retrieve_past_context(
                user_id=user_id,
                current_query=query
            )
            
            if not results:
                return f"Không tìm thấy ký ức nào liên quan đến '{query}'."
            
            return f"Đã tìm thấy các ký ức sau:\n{results}"
            
        except Exception as e:
            logger.error(f"Lỗi khi tìm kiếm episodic memory: {e}")
            raise ToolExecutionError(self.name, f"Lỗi khi tìm kiếm ký ức: {e}", original_error=e)
    
    def __repr__(self) -> str:
        return f"<SearchMemoryTool: episodic_manager={self.episodic_manager is not None}>"