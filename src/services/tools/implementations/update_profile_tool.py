"""
UpdateUserProfileTool - Update Core Memory (T3).

Tool for writing new facts to user profile in YAML database.
Uses CoreManager's SmartUpdater for intelligent profile updates.

Migration from ToolManager._update_user_profile():
- Same logic, now encapsulated in a class
- Dependency injection via constructor
- Self-contained schema definition
"""

import logging
from typing import Dict, Any, Optional

from src.services.tools.base_tool import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)


class UpdateUserProfileTool(BaseTool):
    """
    Tool for updating Core Memory (T3) user profile.
    
    Writes new facts to user's YAML profile file.
    Uses SmartUpdater to intelligently process and integrate facts.
    
    Attributes:
        core_manager: CoreManager instance for T3 access
    
    Example:
        tool = UpdateUserProfileTool(core_manager)
        result = await tool.execute(user_id="123", new_fact="Tên là Hoàng")
    """
    
    def __init__(self, core_manager: Optional[Any] = None):
        """
        Initialize UpdateUserProfileTool.
        
        Args:
            core_manager: CoreManager (T3) for profile updates
        """
        self.core_manager = core_manager
        logger.info(f"UpdateUserProfileTool initialized with core_manager={core_manager is not None}")
    
    # ==========================================
    # BASE TOOL PROPERTIES
    # ==========================================
    
    @property
    def name(self) -> str:
        return "update_user_profile"
    
    @property
    def description(self) -> str:
        return "Ghi info MỚI về user vào Core Memory (T3). Chi tiết cách dùng xem TOOL.md."
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "Discord user ID (số) của user đang chat. VD: '726302130318868500'"
                },
                "new_fact": {
                    "type": "string",
                    "description": "Thông tin cụ thể cần ghi nhớ. VD: 'Tên là Hoàng', 'Sở thích chơi game', 'Làm việc tại công ty ABC'"
                }
            },
            "required": ["user_id", "new_fact"]
        }
    
    # ==========================================
    # EXECUTION
    # ==========================================
    
    async def execute(self, user_id: str, new_fact: str) -> str:
        """
        Update user profile with new fact.
        
        Args:
            user_id: Discord user ID (must be numeric)
            new_fact: New information to add to profile
            
        Returns:
            str: Success or error message
        """
        # Validate inputs
        if not user_id or not new_fact:
            return "Lỗi: Thiếu thông tin update."
        
        # Validate user_id format (Discord ID must be numeric)
        if not user_id.isdigit():
            logger.warning(f"⚠️ Invalid user_id: {user_id} - không phải số")
            return f"Lỗi: user_id '{user_id}' không hợp lệ. user_id phải là số ID của Discord user."
        
        # Check if core_manager is available
        if not self.core_manager:
            return "Lỗi: Hệ thống Core Memory (T3) chưa sẵn sàng."
        
        # Check if updater is available
        if not hasattr(self.core_manager, 'updater') or not self.core_manager.updater:
            return "Lỗi: SmartUpdater của Core Memory chưa sẵn sàng."
        
        # Execute update
        try:
            success = await self.core_manager.updater.update_profile_with_fact(
                user_id=user_id,
                new_fact=new_fact,
                context=""  # Agent tự quyết định fact, không cần context từ T1
            )
            
            if success:
                logger.info(f"✅ UpdateUserProfileTool: Đã cập nhật T3 cho user {user_id}")
                return f"Đã ghi nhớ thành công vào hồ sơ user: {new_fact}"
            else:
                return f"Lỗi: Không thể cập nhật hồ sơ user {user_id}."
                
        except Exception as e:
            logger.error(f"Lỗi khi gọi T3 updater: {e}")
            raise ToolExecutionError(self.name, f"Lỗi hệ thống khi cập nhật hồ sơ: {e}", original_error=e)
    
    def __repr__(self) -> str:
        return f"<UpdateUserProfileTool: core_manager={self.core_manager is not None}>"