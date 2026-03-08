import logging

from langsmith import traceable

from ..constants import CRITICAL_INFO_THRESHOLD, TARGET_SAFE_TOKENS
from ..storage.base_storage import BaseStorage

logger = logging.getLogger(__name__)


class SmartCleanup:
    """
    Bộ dọn dẹp RAM thông minh.
    Mục tiêu: Giảm tổng Token xuống mức an toàn (< TARGET_SAFE_TOKENS)
    nhưng KHÔNG LÀM MẤT các tin nhắn quan trọng.
    """

    def __init__(self, storage: BaseStorage):
        self.storage = storage

    @traceable(
        name="T1_Smart_Cleanup_Execution",
        run_type="chain",
        tags=["tier_1", "management", "cleanup"],
    )
    async def execute(self, user_id: str, current_tokens: int) -> None:
        """Thực thi thuật toán dọn dẹp cho user."""

        # Nếu vẫn ở ngưỡng an toàn, không cần dọn
        if current_tokens <= TARGET_SAFE_TOKENS:
            return

        tokens_to_remove = current_tokens - TARGET_SAFE_TOKENS
        entries = await self.storage.get_entries(user_id)

        if not entries:
            return

        # Sắp xếp theo thời gian (cũ -> mới)
        entries.sort(key=lambda x: x.timestamp)

        # 1. BẢO VỆ: Lấy 3 tin nhắn MỚI NHẤT (để không đứt mạch chat)
        protected_recent = entries[-3:] if len(entries) >= 3 else entries
        protected_ids = {e.entry_id for e in protected_recent}

        # 2. BẢO VỆ: Các tin nhắn có điểm cực cao (Trí nhớ dài hạn trong phiên)
        for e in entries:
            if e.importance_score >= CRITICAL_INFO_THRESHOLD:
                protected_ids.add(e.entry_id)

        # 3. CHỌN LỌC ĐỂ XÓA: Những tin không được bảo vệ
        prunable_entries = [e for e in entries if e.entry_id not in protected_ids]

        # Sắp xếp ưu tiên xóa: Điểm thấp xóa trước, nếu điểm bằng nhau thì Cũ xóa trước
        prunable_entries.sort(key=lambda x: (x.importance_score, x.timestamp))

        ids_to_delete = []
        tokens_deleted = 0

        # Tiến hành trảm từ từ cho đến khi đủ chỉ tiêu Token
        for e in prunable_entries:
            if tokens_deleted >= tokens_to_remove:
                break
            ids_to_delete.append(e.entry_id)
            tokens_deleted += e.tokens

        # Cập nhật xuống Storage
        if ids_to_delete:
            await self.storage.delete_entries(user_id, ids_to_delete)
            logger.info(
                f"🧹 SmartCleanup: Đã xóa {len(ids_to_delete)} tin nhắn rác, "
                f"giải phóng {tokens_deleted} tokens cho user {user_id}."
            )
