# src/services/memories/core_memory/core_manager.py
import logging

from langsmith import traceable

logger = logging.getLogger(__name__)


class CoreManager:
    # Nhận storage và smart_updater từ bên ngoài truyền vào
    def __init__(self, storage, smart_updater):
        self.storage = storage
        self.updater = smart_updater

    @traceable(
        name="T3_Get_System_Prompt",
        run_type="chain",
        tags=["tier_3", "core_memory", "read"]
    )
    async def get_system_prompt_context(self, user_id: str) -> str:
        """Lấy hồ sơ Markdown và nhúng thẳng vào System Prompt cho Bot chat"""
        profile_md = self.storage.get_profile(user_id)
        
        # Nếu chưa có thông tin gì thì không cần nhét vào prompt cho nặng
        if not profile_md or "Chưa có thông tin" in profile_md:
            return ""
            
        return f"\n=== THÔNG TIN NGƯỜI DÙNG (TẦNG 3) ===\n{profile_md}\n"

    @traceable(
        name="T3_Handle_Critical_Info",
        run_type="chain",
        tags=["tier_3", "core_memory", "write", "event_handler"]
    )
    async def handle_critical_info(self, event_type: str, user_id: str, data: dict) -> bool:
        """
        Callback (Lỗ tai) lắng nghe sự kiện từ EventDispatcher của Tầng 1.
        Khi Tầng 1 bắn CRITICAL_INFO, hàm này sẽ chạy ngầm.
        """
        logger.info(f"⚡ T3 CoreManager: Đã bắt được sự kiện {event_type} cho user {user_id}")

        # Trích xuất nội dung từ payload data của Tầng 1 gửi sang
        if isinstance(data, dict) and "entry" in data:
            # Format mới: có entry và context
            entry = data.get("entry")
            context_entries = data.get("context", [])

            # Lấy content từ entry
            new_fact = entry.get("content", "") if isinstance(entry, dict) else getattr(entry, "content", "")

            # Build context string từ các tin nhắn trước đó để LLM hiểu rõ ngữ cảnh
            context_str = ""
            if context_entries:
                context_lines = []
                for e in context_entries:
                    role = e.get("role", "") if isinstance(e, dict) else getattr(e, "role", "")
                    content = e.get("content", "") if isinstance(e, dict) else getattr(e, "content", "")
                    if role and content:
                        role_label = "User" if role == "user" else "Bot"
                        context_lines.append(f"[{role_label}]: {content}")
                context_str = "\n".join(context_lines)
        else:
            # Format cũ: chỉ có data text
            new_fact = data.get("content", "") if isinstance(data, dict) else getattr(data, "content", "")
            context_str = ""

        if not new_fact:
            return False

        # Giao việc cho Thư ký (Smart Updater) để gọi LLM cập nhật file Markdown
        return await self.updater.update_profile_with_fact(user_id, new_fact, context_str)