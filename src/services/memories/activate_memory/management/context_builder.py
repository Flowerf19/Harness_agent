import logging
from typing import List

from langsmith import traceable

from ..models import MemoryEntry

logger = logging.getLogger(__name__)


class ContextBuilder:
    """
    Bộ xây dựng Ngữ cảnh Hỗn hợp (Composite Context) để đưa vào Prompt cho LLM.
    """

    @traceable(
        name="T1_Build_Composite_Context",
        run_type="chain",
        tags=["tier_1", "management", "context"],
    )
    def build_context(
        self, entries: List[MemoryEntry], max_recent: int = 4, max_important: int = 2
    ) -> List[dict]:
        """
        Trộn N tin mới nhất + M tin quan trọng nhất.
        Trả về list các dict theo chuẩn {"role": "...", "content": "..."} đã sort theo thời gian.
        """
        if not entries:
            return []

        # Sort cũ -> mới
        sorted_entries = sorted(entries, key=lambda x: x.timestamp)

        # 1. Lấy N tin mới nhất
        recent_entries = (
            sorted_entries[-max_recent:]
            if len(sorted_entries) > max_recent
            else sorted_entries
        )
        recent_ids = {e.entry_id for e in recent_entries}

        # 2. Lấy phần còn lại (không nằm trong list mới nhất)
        remaining_entries = [e for e in sorted_entries if e.entry_id not in recent_ids]

        # 3. Từ phần còn lại, lấy M tin có điểm cao nhất
        remaining_entries.sort(key=lambda x: x.importance_score, reverse=True)
        important_entries = remaining_entries[:max_important]

        # 4. Gộp lại và sort CHUẨN THỜI GIAN một lần nữa để LLM không bị loạn mạch logic
        composite_entries = recent_entries + important_entries
        composite_entries.sort(key=lambda x: x.timestamp)

        # 5. Format lại thành chuẩn JSON Message cho LLM
        # Lược bỏ các metadata không cần thiết (id, tokens) để tiết kiệm băng thông API
        formatted_context = [
            {"role": e.role, "content": e.content} for e in composite_entries
        ]

        return formatted_context
