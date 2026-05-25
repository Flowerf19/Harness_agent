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
    async def get_entries(self, scope: str, scope_id: str | None = None) -> List[MemoryEntry]:
        """Lấy toàn bộ tin nhắn hiện có theo scope theo thứ tự thời gian."""
        pass

    @abstractmethod
    async def get_total_tokens(self, scope: str, scope_id: str | None = None) -> int:
        """Lấy tổng số token hiện đang chiếm dụng của một scope."""
        pass

    @abstractmethod
    async def delete_entries(
        self, scope: str, scope_id: str | None = None, entry_ids: List[str] | None = None
    ) -> None:
        """Xóa danh sách các tin nhắn cụ thể (Dùng cho Smart Cleanup)."""
        pass

    @abstractmethod
    async def clear_all(self, scope: str, scope_id: str | None = None) -> None:
        """Xóa sạch bộ nhớ của scope (Dùng khi Timeout hết phiên)."""
        pass
