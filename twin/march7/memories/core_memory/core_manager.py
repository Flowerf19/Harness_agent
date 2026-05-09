# src/services/memories/core_memory/core_manager.py
import logging

from langsmith import traceable

logger = logging.getLogger(__name__)


class CoreManager:
    """T3 Core Memory Manager - reads/writes user profile (IDENTITY.md)."""

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

        # Luôn include user_id để LLM biết ID của user đang chat (dùng cho tool calls)
        user_id_context = f"ID Discord của user đang chat: {user_id}"

        # Nếu chưa có thông tin gì thì chỉ return user_id
        if not profile_md or "Chưa có thông tin" in profile_md:
            return f"\n=== THÔNG TIN NGƯỜI DÙNG ===\n{user_id_context}\n"

        return f"\n=== THÔNG TIN NGƯỜI DÙNG ===\n{user_id_context}\n{profile_md}\n"