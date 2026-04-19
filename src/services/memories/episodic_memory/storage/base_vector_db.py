# src/services/episodic_memory/storage/base_vector_db.py
from abc import ABC, abstractmethod
from typing import List, Tuple

from ..models import EpisodicRecord


class BaseVectorDB(ABC):
    """
    Hợp đồng (Interface) bắt buộc đối với mọi loại Vector Database
    được sử dụng cho Episodic Memory.
    """

    @abstractmethod
    async def add_record(self, user_id: str, record: EpisodicRecord) -> None:
        """Lưu một ký ức mới (đã kèm vector) vào DB của user."""
        pass

    @abstractmethod
    async def search_similar(
        self,
        user_id: str,
        query_vector: List[float],
        top_k: int = 3,
        threshold: float = 0.5,
    ) -> List[Tuple[EpisodicRecord, float]]:
        """
        Tìm kiếm Top K ký ức giống với query_vector nhất.
        Trả về danh sách các tuple: (Ký_ức, Điểm_tương_đồng)
        """
        pass

    @abstractmethod
    async def get_recent_records(
        self, user_id: str, limit: int = 5
    ) -> List[EpisodicRecord]:
        """Lấy các ký ức mới nhất theo thời gian (Không dùng vector)."""
        pass

    @abstractmethod
    async def delete_record(self, user_id: str, record_id: str) -> None:
        """Xóa đích danh một ký ức (nếu cần)."""
        pass
