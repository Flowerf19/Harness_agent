# src/services/episodic_memory/retrieval/context_formatter.py
from typing import List, Tuple

from ...models import EpisodicRecord


class ContextFormatter:
    """Định dạng các Ký ức truy xuất được thành chuỗi văn bản cho Prompt."""

    @staticmethod
    def format_for_llm(retrieved_events: List[Tuple[EpisodicRecord, float]]) -> str:
        """
        Nhận vào danh sách (Record, Score). Trả về String.
        """
        if not retrieved_events:
            return "Không tìm thấy ký ức nào trong quá khứ liên quan đến vấn đề này."

        formatted_blocks = []
        formatted_blocks.append("--- [TRÍCH XUẤT KÝ ỨC QUÁ KHỨ] ---")

        for idx, (record, score) in enumerate(retrieved_events, 1):
            p = record.payload
            time_str = record.timestamp.strftime("%Y-%m-%d %H:%M")

            # Format từng block rõ ràng cho AI đọc
            block = (
                f"Sự kiện {idx}: {p.event_title}\n"
                f"Thời gian: {time_str} (Độ liên quan: {score:.2f})\n"
                f"Chi tiết: {p.detailed_summary}\n"
                f"Trạng thái: {p.resolution_status} | Cảm xúc: {p.user_sentiment}"
            )
            formatted_blocks.append(block)

        formatted_blocks.append("-----------------------------------")

        return "\n\n".join(formatted_blocks)
