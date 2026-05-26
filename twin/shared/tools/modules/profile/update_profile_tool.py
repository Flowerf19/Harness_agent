"""
UpdateUserProfileTool - Update Core Memory (T3).

Tool for saving the complete user profile markdown to T3 storage.
Agent handles fact detection and merge logic. Tool is storage-only.
"""

import logging
from typing import Dict, Any, Optional

from twin.shared.tools.registry.base import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)

class UpdateUserProfileTool(BaseTool):
    """
    Tool for saving Core Memory (T3) user profile.
    
    Agent orchestrates: detect new facts → merge into profile → call this tool to persist.
    Tool only validates and writes markdown to storage.
    
    Attributes:
        core_manager: CoreManager instance for T3 access
    """
    
    def __init__(self, core_manager: Optional[Any] = None):
        self.core_manager = core_manager
        logger.debug(f"UpdateUserProfileTool initialized with core_manager={core_manager is not None}")
    
    @property
    def name(self) -> str:
        return "update_user_profile"
    
    @property
    def description(self) -> str:
        return "Lưu toàn bộ hồ sơ user (markdown) vào Core Memory (T3). Chi tiết cách dùng xem TOOL.md."
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "Discord user ID (số) của user đang chat. VD: '726302130318868500'"
                },
                "new_profile_markdown": {
                    "type": "string",
                    "description": "Toàn bộ nội dung markdown mới của hồ sơ user. Agent tự merge fact mới vào profile cũ trước khi gọi tool này. VD: '## Thông tin cơ bản\n- Danh xưng: Hoàng\n...'"
                }
            },
            "required": ["user_id", "new_profile_markdown"]
        }
    
    async def execute(self, user_id: str, new_profile_markdown: str) -> str:
        """
        Save complete user profile markdown to T3 storage.
        
        Args:
            user_id: Discord user ID (must be numeric)
            new_profile_markdown: Full markdown content to overwrite the profile
            
        Returns:
            str: Success or error message
        """
        if not user_id or not new_profile_markdown:
            return "Lỗi: Thiếu user_id hoặc nội dung hồ sơ."
        
        if not user_id.isdigit():
            logger.warning(f"⚠️ Invalid user_id: {user_id}")
            return f"Lỗi: user_id '{user_id}' không hợp lệ. Phải là số ID Discord."
        
        if not self.core_manager:
            return "Lỗi: Hệ thống Core Memory (T3) chưa sẵn sàng."
        
        try:
            success = self.core_manager.save_profile(user_id, new_profile_markdown)
            
            if success:
                logger.info(f"✅ UpdateUserProfileTool: Đã lưu T3 cho user {user_id}")
                return f"Đã lưu hồ sơ thành công cho user {user_id}."
            else:
                return f"Lỗi: Không thể lưu hồ sơ cho user {user_id}."
                
        except Exception as e:
            logger.error(f"Lỗi khi lưu T3: {e}")
            raise ToolExecutionError(self.name, f"Lỗi hệ thống khi lưu hồ sơ: {e}", original_error=e)
    
    def __repr__(self) -> str:
        return f"<UpdateUserProfileTool: core_manager={self.core_manager is not None}>"
