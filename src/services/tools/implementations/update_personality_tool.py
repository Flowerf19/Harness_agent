"""
UpdatePersonalityTool - Update IDENTITY.md.

Tool for adding new personality rules to IDENTITY.md file.
Used when user explicitly requests behavior changes.

Migration from ToolManager._update_personality():
- Same logic, now encapsulated in a class
- Dependency injection via constructor
- Self-contained schema definition
"""

import logging
import os
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

from src.services.tools.base_tool import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)


class UpdatePersonalityTool(BaseTool):
    """
    Tool for updating personality rules in IDENTITY.md.
    
    Appends new rules/guidelines to the bot's personality file.
    Only used when user explicitly requests behavior changes.
    
    Attributes:
        base_memory_path: Path to memories directory
    
    Example:
        tool = UpdatePersonalityTool(base_memory_path="memories")
        result = await tool.execute(instruction="Nói ngắn gọn hơn")
    """
    
    def __init__(self, base_memory_path: str = "memories"):
        """
        Initialize UpdatePersonalityTool.
        
        Args:
            base_memory_path: Path to memories directory (default: "memories")
        """
        self.base_memory_path = base_memory_path
        logger.info(f"UpdatePersonalityTool initialized with base_path={base_memory_path}")
    
    # ==========================================
    # BASE TOOL PROPERTIES
    # ==========================================
    
    @property
    def name(self) -> str:
        return "update_personality"
    
    @property
    def description(self) -> str:
        return (
            "Thay đổi cách nói chuyện hoặc thêm quy tắc mới vào IDENTITY.md. "
            "CHỈ dùng khi user YÊU CẦU bạn thay đổi. KHÔNG tự ý thay đổi."
        )
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": "Quy tắc hoặc hướng dẫn mới về cách nói chuyện. VD: 'Nói ngắn gọn hơn', 'Dùng emoji nhiều hơn', 'Tránh slang Gen Z'"
                }
            },
            "required": ["instruction"]
        }
    
    # ==========================================
    # EXECUTION
    # ==========================================
    
    async def execute(self, instruction: str) -> str:
        """
        Update personality with new instruction.
        
        Args:
            instruction: New rule/guideline to add
            
        Returns:
            str: Success message
        """
        # Validate input
        if not instruction:
            return "Lỗi: Thiếu instruction."
        
        # Get identity file path
        identity_file = os.path.join(self.base_memory_path, "IDENTITY.md")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Prepare append text
        append_text = f"\n- [{timestamp}] Cập nhật tính cách: {instruction}"
        
        # Write to file (async)
        def write_file():
            # If file doesn't exist, create with header
            if not os.path.exists(identity_file):
                with open(identity_file, "w", encoding="utf-8") as f:
                    f.write("# NHÂN CÁCH CỦA BẠN\n\n")
                    f.write("## Quy tắc động (Agent tự cập nhật)\n")
            
            # Append new rule
            with open(identity_file, "a", encoding="utf-8") as f:
                f.write(append_text)
        
        try:
            await asyncio.to_thread(write_file)
            logger.info(f"✅ UpdatePersonalityTool: Đã cập nhật tính cách: {instruction}")
            return "Đã cập nhật tính cách/luật lệ thành công. Hãy áp dụng ngay từ bây giờ."
            
        except Exception as e:
            logger.error(f"Lỗi khi ghi IDENTITY.md: {e}")
            raise ToolExecutionError(self.name, f"Lỗi khi ghi file: {e}", original_error=e)
    
    def __repr__(self) -> str:
        return f"<UpdatePersonalityTool: base_path={self.base_memory_path}>"