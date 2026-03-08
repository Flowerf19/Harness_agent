# src/services/memories/activate_memory/storage/base_storage.py
from abc import ABC, abstractmethod
from typing import List

from ..models import MemoryEntry


class BaseStorage(ABC):
    """Interface tiêu chuẩn cho mọi hệ thống lưu trữ Active Memory."""

    @abstractmethod
    async def save_entry(self, entry: MemoryEntry) -> None:
        """Lưu một tin nhắn mới vào bộ nhớ."""
        pass

    @abstractmethod
    async def get_entries(self, user_id: str) -> List[MemoryEntry]:
        """Lấy toàn bộ tin nhắn hiện có của user theo thứ tự thời gian."""
        pass

    @abstractmethod
    async def get_total_tokens(self, user_id: str) -> int:
        """Lấy tổng số token hiện đang chiếm dụng của một user."""
        pass

    @abstractmethod
    async def delete_entries(self, user_id: str, entry_ids: List[str]) -> None:
        """Xóa danh sách các tin nhắn cụ thể (Dùng cho Smart Cleanup)."""
        pass

    @abstractmethod
    async def clear_all(self, user_id: str) -> None:
        """Xóa sạch bộ nhớ của user (Dùng khi Timeout hết phiên)."""
        pass
