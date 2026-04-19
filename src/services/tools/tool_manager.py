"""
ToolManager - Quản lý các công cụ (Tools) cho Agent.
Bao gồm việc cung cấp mô tả công cụ cho LLM và thực thi chúng.
"""

import logging
import os
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ToolManager:
    """
    Quản lý các công cụ (Tools) cho Agent.
    Cho phép LLM tự động tìm kiếm ký ức, cập nhật hồ sơ user và điều chỉnh tính cách.
    
    Note: Đây là legacy adapter. Hãy dùng MCP architecture (mcp_client.py) thay vì ToolManager.
    """

    def __init__(
        self,
        episodic_manager: Optional[Any] = None,
        core_manager: Optional[Any] = None,
        base_memory_path: str = "memories",
    ):
        self.episodic_manager = episodic_manager
        self.core_manager = core_manager
        self.base_memory_path = base_memory_path

        users_path = os.path.join(self.base_memory_path, "users")
        os.makedirs(users_path, exist_ok=True)
        logger.info(f"ToolManager: Đã khởi tạo với base_path={base_memory_path}")

    def get_native_tool_schemas(self) -> list:
        """
        Trả về danh sách tool schemas theo chuẩn OpenAI JSON Schema.
        Dùng cho Native Function Calling (API Tool Calling).

        Returns:
            List of tool definitions compatible with OpenAI/Qwen/LM Studio APIs.
            Gemini cần map sang functionDeclarations format.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_memory",
                    "description": "Tìm kiếm ký ức cũ của user từ Episodic Memory (T2). Dùng khi user nhắc chuyện quá khứ, hỏi về sở thích/sự kiện cũ, hoặc cần context từ lịch sử hội thoại.",
                    "parameters": {
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
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_user_profile",
                    "description": "Ghi thông tin MỚI về user vào Core Memory (T3). Dùng khi user chia sẻ thông tin cá nhân mới (tên, sở thích, công việc, quan hệ, etc.). KHÔNG dùng cho thông tin đã biết hoặc chung chung.",
                    "parameters": {
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
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_personality",
                    "description": "Thay đổi cách nói chuyện hoặc thêm quy tắc mới vào IDENTITY.md. CHỈ dùng khi user YÊU CẦU bạn thay đổi. KHÔNG tự ý thay đổi.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "instruction": {
                                "type": "string",
                                "description": "Quy tắc hoặc hướng dẫn mới về cách nói chuyện. VD: 'Nói ngắn gọn hơn', 'Dùng emoji nhiều hơn', 'Tránh slang Gen Z'"
                            }
                        },
                        "required": ["instruction"]
                    }
                }
            }
        ]

    async def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        """
        Router điều hướng thực thi tool.

        Args:
            tool_name: Tên tool cần chạy
            args: Dict chứa các tham số cho tool

        Returns:
            Kết quả thực thi (string) để LLM đọc
        """
        logger.info(f"Thực thi Tool: {tool_name} cho user: {args.get('user_id', 'N/A')}")
        try:
            if tool_name == "search_memory":
                return await self._search_memory(
                    str(args.get("user_id", "")), args.get("query", "")
                )
            elif tool_name == "update_user_profile":
                return await self._update_user_profile(
                    str(args.get("user_id", "")), args.get("new_fact", "")
                )
            elif tool_name == "update_personality":
                return await self._update_personality(args.get("instruction", ""))
            else:
                return f"Lỗi: Không tìm thấy công cụ tên '{tool_name}'."
        except Exception as e:
            logger.error(f"Lỗi khi chạy tool {tool_name}: {e}")
            return f"Lỗi hệ thống khi chạy tool: {e}"

    async def _search_memory(self, user_id: str, query: str) -> str:
        """Tìm kiếm ký ức dài hạn từ EpisodicManager (T2)."""
        if not user_id or not query:
            return "Lỗi: Thiếu user_id hoặc query."

        if not user_id.isdigit():
            logger.warning(f"⚠️ Invalid user_id: {user_id} - không phải số")
            return f"Lỗi: user_id '{user_id}' không hợp lệ. user_id phải là số ID của Discord user."

        if self.episodic_manager:
            try:
                results = await self.episodic_manager.retrieve_past_context(
                    user_id=user_id, current_query=query
                )
                if not results:
                    return f"Không tìm thấy ký ức nào liên quan đến '{query}'."
                return f"Đã tìm thấy các ký ức sau:\n{results}"
            except Exception as e:
                logger.error(f"Lỗi khi tìm kiếm episodic memory: {e}")
                return f"Lỗi khi tìm kiếm ký ức: {e}"
        else:
            return "Lỗi: Hệ thống Episodic Memory chưa sẵn sàng."

    async def _update_user_profile(self, user_id: str, new_fact: str) -> str:
        """Ghi thêm fact mới vào hồ sơ user (T3 Core Memory)."""
        if not user_id or not new_fact:
            return "Lỗi: Thiếu thông tin update."

        if not user_id.isdigit():
            logger.warning(f"⚠️ Invalid user_id: {user_id} - không phải số")
            return f"Lỗi: user_id '{user_id}' không hợp lệ. user_id phải là số ID của Discord user."

        if self.core_manager and self.core_manager.updater:
            try:
                success = await self.core_manager.updater.update_profile_with_fact(
                    user_id=user_id,
                    new_fact=new_fact,
                    context=""
                )
                if success:
                    logger.info(f"✅ ToolManager: Đã cập nhật T3 cho user {user_id} qua Agent")
                    return f"Đã ghi nhớ thành công vào hồ sơ user: {new_fact}"
                else:
                    return f"Lỗi: Không thể cập nhật hồ sơ user {user_id}."
            except Exception as e:
                logger.error(f"Lỗi khi gọi T3 updater: {e}")
                return f"Lỗi hệ thống khi cập nhật hồ sơ: {e}"
        else:
            return "Lỗi: Hệ thống Core Memory (T3) chưa sẵn sàng."

    async def _update_personality(self, instruction: str) -> str:
        """Ghi thêm quy tắc mới vào IDENTITY.md."""
        if not instruction:
            return "Lỗi: Thiếu instruction."

        identity_file = os.path.join(self.base_memory_path, "IDENTITY.md")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        append_text = f"\n- [{timestamp}] Cập nhật tính cách: {instruction}"

        def write_file():
            if not os.path.exists(identity_file):
                with open(identity_file, "w", encoding="utf-8") as f:
                    f.write("# NHÂN CÁCH CỦA BẠN\n\n")
                    f.write("## Quy tắc động (Agent tự cập nhật)\n")
            with open(identity_file, "a", encoding="utf-8") as f:
                f.write(append_text)

        await asyncio.to_thread(write_file)
        logger.info(f"Đã cập nhật tính cách: {instruction}")
        return "Đã cập nhật tính cách/luật lệ thành công. Hãy áp dụng ngay từ bây giờ."