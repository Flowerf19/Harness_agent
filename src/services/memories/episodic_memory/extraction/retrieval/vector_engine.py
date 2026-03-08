# src/services/episodic_memory/retrieval/vector_engine.py
import logging
from typing import List, Optional

from Arize_Phoenix_tool_kit import track_general_step

from ..models import EpisodicPayload, EpisodicRecord

logger = logging.getLogger(__name__)


class VectorEngine:
    """
    Động cơ xử lý Vector.
    Chịu trách nhiệm nhúng (Embed) văn bản thành mảng số thực.
    """

    def __init__(self, embedding_service):
        """
        :param embedding_service: Service chứa hàm `get_embedding(text) -> List[float]`
        """
        self.embedding_service = embedding_service

    @track_general_step(
        step_name="T2_Embed_Event_Payload", tags=["tier_2", "embedding", "ingestion"]
    )
    async def create_record(self, payload: EpisodicPayload) -> Optional[EpisodicRecord]:
        """
        Lấy phần `detailed_summary` đi nhúng.
        Tại sao chỉ nhúng summary? Vì nó chứa ngữ cảnh đầy đủ nhất.
        """
        try:
            # Gọi LLM (Qwen) nhúng text
            vector = await self.embedding_service.get_embedding(
                payload.detailed_summary
            )

            if not vector or len(vector) == 0:
                logger.error("❌ VectorEngine: Qwen trả về vector rỗng!")
                return None

            # Đóng gói thành Record hoàn chỉnh có chứa Vector
            record = EpisodicRecord(payload=payload, embedding=vector)
            return record

        except Exception as e:
            logger.error(f"❌ VectorEngine: Lỗi khi nhúng payload: {e}")
            return None

    @track_general_step(
        step_name="T2_Embed_User_Query", tags=["tier_2", "embedding", "retrieval"]
    )
    async def embed_query(self, query_text: str) -> Optional[List[float]]:
        """Nhúng câu hỏi của user để đi tìm kiếm trong DB."""
        try:
            vector = await self.embedding_service.get_embedding(query_text)
            if not vector:
                return None
            return vector
        except Exception as e:
            logger.error(f"❌ VectorEngine: Lỗi khi nhúng câu truy vấn: {e}")
            return None
