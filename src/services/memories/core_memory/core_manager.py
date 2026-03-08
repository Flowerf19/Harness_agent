import logging

from langsmith import traceable

from .smart_updater import SmartUpdater
from .storage.base_core_db import BaseCoreDB

logger = logging.getLogger(__name__)


class CoreManager:
    """
    Facade Tổng Chỉ Huy của Tầng 3 (Core Memory).
    Cung cấp giao diện duy nhất để Tầng 1 và MemoryManager giao tiếp.
    """

    def __init__(self, storage: BaseCoreDB, smart_updater: SmartUpdater):
        self.storage = storage
        self.smart_updater = smart_updater

    @traceable(
        name="T3_Inject_System_Prompt",
        run_type="chain",
        tags=["tier_3", "core_memory", "prompt_injection"],
    )
    async def get_system_prompt_context(self, user_id: str) -> str:
        """
        Lấy Profile của user và biên dịch thành một đoạn văn bản chuẩn mực
        để đính kèm vào System Prompt của LLM.
        """
        profile = await self.storage.get_profile(user_id)

        # Kiểm tra xem profile có hoàn toàn trống không (User mới tinh)
        is_empty = not any(
            [
                profile.name,
                profile.demographics,
                profile.occupation,
                profile.relationships,
                profile.interests,
                profile.goals_and_plans,
                profile.preferences,
                profile.constraints,
                profile.other_facts,
            ]
        )

        if is_empty:
            return ""

        # Dịch JSON thành văn bản Bullet-point cho LLM dễ hiểu
        lines = ["\n[THÔNG TIN VỀ NGƯỜI DÙNG (SHARED CONTEXT)]"]

        if profile.name or profile.demographics:
            ident = []
            if profile.name:
                ident.append(f"Danh xưng: {profile.name}")
            if profile.demographics:
                ident.append(f"Nhân khẩu học: {profile.demographics}")
            lines.append("- " + " | ".join(ident))

        if profile.occupation:
            lines.append(f"- Nghề nghiệp/Vai trò: {profile.occupation}")

        if profile.relationships:
            lines.append(f"- Mối quan hệ: {', '.join(profile.relationships)}")

        if profile.interests:
            lines.append(f"- Sở thích: {', '.join(profile.interests)}")

        if profile.goals_and_plans:
            lines.append(f"- Mục tiêu/Kế hoạch: {', '.join(profile.goals_and_plans)}")

        if profile.preferences:
            lines.append(f"- Thói quen ưa thích: {', '.join(profile.preferences)}")

        if profile.constraints:
            # Nhấn mạnh bằng viết hoa để LLM chú ý không vi phạm
            lines.append(f"- RÀNG BUỘC/CẤM KỴ: {', '.join(profile.constraints)}")

        if profile.other_facts:
            lines.append(f"- Khác: {', '.join(profile.other_facts)}")

        # Chỉ thị ẩn dành cho LLM (Chống lộ nguồn)
        lines.append(
            "*(Chỉ thị: Hãy sử dụng thông tin trên để hiểu ngữ cảnh và cá nhân hóa tự nhiên. "
            "TUYỆT ĐỐI KHÔNG dùng các mẫu câu như 'Theo như hồ sơ của bạn...', 'Tôi nhớ bạn đã nói...'. "
            "Hãy cư xử như thể đây là sự thấu hiểu tự nhiên giữa hai người bạn)*\n"
        )

        return "\n".join(lines)

    @traceable(
        name="T3_Handle_Critical_Info",
        run_type="chain",
        tags=["tier_3", "core_memory", "event_handler"],
    )
    async def handle_critical_info(
        self, event_type: str, user_id: str, data: dict
    ) -> bool:
        """
        Callback (Lỗ tai) lắng nghe sự kiện từ EventDispatcher của Tầng 1.
        Khi Tầng 1 bắn CRITICAL_INFO, hàm này sẽ chạy ngầm.
        """
        logger.info(
            f"⚡ T3 CoreManager: Đã bắt được sự kiện {event_type} cho user {user_id}"
        )

        # Trích xuất nội dung từ data (có thể là dict với entry + context, hoặc chỉ entry)
        if isinstance(data, dict) and "entry" in data:
            # Format mới: có entry và context
            entry = data.get("entry")
            context_entries = data.get("context", [])

            # Lấy content từ entry
            new_fact = (
                entry.get("content", "")
                if isinstance(entry, dict)
                else getattr(entry, "content", "")
            )

            # Build context string từ các tin nhắn trước đó
            context_str = ""
            if context_entries:
                context_lines = []
                for e in context_entries:
                    role = (
                        e.get("role", "")
                        if isinstance(e, dict)
                        else getattr(e, "role", "")
                    )
                    content = (
                        e.get("content", "")
                        if isinstance(e, dict)
                        else getattr(e, "content", "")
                    )
                    if role and content:
                        role_label = "User" if role == "user" else "Bot"
                        context_lines.append(f"[{role_label}]: {content}")
                context_str = "\n".join(context_lines)

        else:
            # Format cũ: chỉ có entry (backward compatible)
            new_fact = (
                data.get("content", "")
                if isinstance(data, dict)
                else getattr(data, "content", "")
            )
            context_str = ""

        if not new_fact:
            return False

        # Giao việc cho Thư ký (Smart Updater) để gọi LLM hợp nhất dữ liệu
        # Truyền cả context để LLM hiểu ngữ cảnh đầy đủ
        success = await self.smart_updater.update_profile_with_fact(
            user_id, new_fact, context_str
        )
        return success
