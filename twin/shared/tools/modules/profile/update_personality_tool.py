"""
UpdatePersonalityTool - Rewrite IDENTITY.md or SOUL.md.

Tool for updating bot's personality/behavior files.
OVERWRITES entire file - bot must provide full merged content.

Bot workflow:
1. Read current content from system prompt (=== NHÂN CÁCH === / === HƯỚNG DẪN ===)
2. Merge with new info
3. Call this tool with full Markdown content

Auto-routes to correct file based on content keywords.
"""

import logging
import os
import asyncio
from typing import Dict, Any, Literal

from twin.shared.tools.registry.base import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)

# Keywords for auto-routing
IDENTITY_KEYWORDS = [
    "tên", "name", "danh tính", "identity", "xưng hô", "tự xưng",
    "tính cách", "trait", "personality", "ngoại hình", "appearance",
    "xuất thân", "backstory", "origin", "sở thích", "interest",
    "động lực", "motivation", "câu nói đặc trưng", "catchphrase",
    "role", "vai trò", "character", "nhân vật", "la ai", "là ai"
]

SOUL_KEYWORDS = [
    "nói", "cách nói", "phong cách", "style", "ngắn", "dài", "gọn",
    "emoji", "icon", "slang", "gen z", "từ lóng", "giao tiếp",
    "phản hồi", "respond", "chat", "hội thoại", "quy tắc", "nguyên tắc",
    "tone", "giọng", "văn phong", "xuống dòng", "format",
    "trả lời", "reply", "đáp", "alo", "hi", "chào"
]


class UpdatePersonalityTool(BaseTool):
    """
    Tool for updating bot's personality files with auto-routing.

    Routes instruction to correct file:
    - IDENTITY.md: Character identity (who the bot is)
    - SOUL.md: Communication rules (how the bot talks)

    Attributes:
        base_memory_path: Path to memories directory

    Example:
        tool = UpdatePersonalityTool()
        # "Tên là ABC" → IDENTITY.md
        # "Nói ngắn hơn" → SOUL.md
    """

    def __init__(self, base_memory_path: str = "memories"):
        self.base_memory_path = base_memory_path
        logger.debug(f"UpdatePersonalityTool initialized with base_path={base_memory_path}")

    # ==========================================
    # BASE TOOL PROPERTIES
    # ==========================================

    @property
    def name(self) -> str:
        return "update_personality"

    @property
    def description(self) -> str:
        return "Viết lại IDENTITY.md hoặc SOUL.md. OVERWRITE toàn bộ file. Chi tiết cách dùng xem TOOL.md."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": (
                        "NỘI DUNG TOÀN BỘ file mới (Markdown format).\n"
                        "Bot phải đọc file cũ, merge với info mới, provide full content.\n"
                        "VD: '# NHÂN CÁCH\\n## Tên: March 7th\\n## Tính cách: ...'"
                    )
                }
            },
            "required": ["instruction"]
        }

    # ==========================================
    # AUTO-ROUTING
    # ==========================================

    def _classify_instruction(self, instruction: str) -> Literal["identity", "soul"]:
        """
        Classify instruction to determine target file.

        Args:
            instruction: The instruction text

        Returns:
            "identity" or "soul"
        """
        instruction_lower = instruction.lower()

        # Count keyword matches for each category
        identity_score = sum(1 for kw in IDENTITY_KEYWORDS if kw in instruction_lower)
        soul_score = sum(1 for kw in SOUL_KEYWORDS if kw in instruction_lower)

        # Default to soul (communication rules are more common requests)
        if identity_score > soul_score:
            return "identity"
        return "soul"

    def _get_file_path(self, target: Literal["identity", "soul"]) -> str:
        """Get file path for target."""
        filename = "IDENTITY.md" if target == "identity" else "SOUL.md"
        return os.path.join(self.base_memory_path, filename)

    def _get_file_header(self, target: Literal["identity", "soul"]) -> str:
        """Get header content for new file."""
        if target == "identity":
            return "# NHÂN CÁCH CỦA BẠN\n\n"
        return "# HƯỚNG DẪN HỘI THOẠI\n\n"

    def _read_current_content(self, file_path: str) -> str:
        """Read current file content for bot to merge."""
        try:
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read()
            return ""
        except Exception as e:
            logger.warning(f"Không thể đọc file {file_path}: {e}")
            return ""

    # ==========================================
    # EXECUTION
    # ==========================================

    async def execute(self, instruction: str) -> str:
        """
        Rewrite personality file with new content.

        Args:
            instruction: Full content for the file (Markdown)

        Returns:
            str: Success message with target file info
        """
        if not instruction:
            return "Lỗi: Thiếu instruction."

        # Auto-route based on instruction content
        target = self._classify_instruction(instruction)
        file_path = self._get_file_path(target)

        # Write to file (async) - OVERWRITE mode
        def write_file():
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(instruction)

        try:
            await asyncio.to_thread(write_file)
            target_display = "IDENTITY (danh tính)" if target == "identity" else "SOUL (cách nói)"
            logger.info(f"✅ UpdatePersonalityTool: Đã viết lại {target}")
            return f"Đã cập nhật {target_display} thành công. Áp dụng ngay từ tin nhắn tiếp theo."

        except Exception as e:
            logger.error(f"Lỗi khi ghi file {target}: {e}")
            raise ToolExecutionError(self.name, f"Lỗi khi ghi file: {e}", original_error=e)

    def __repr__(self) -> str:
        return f"<UpdatePersonalityTool: base_path={self.base_memory_path}>"