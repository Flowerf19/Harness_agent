# src/services/memories/activate_memory/storage/ram_storage.py
import asyncio
import logging
from collections import defaultdict
from typing import Dict, List

from ..models import MemoryEntry
from .base_storage import BaseStorage

logger = logging.getLogger(__name__)


class RamStorage(BaseStorage):
    def __init__(self):
        # Lưu dữ liệu theo cấu trúc: { user_id: [MemoryEntry,...] }
        self._data: Dict[str, List[MemoryEntry]] = defaultdict(list)
        # Hệ thống khóa (Lock) theo từng user để chống Race Condition
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def _get_lock(self, user_id: str) -> asyncio.Lock:
        """Lấy ổ khóa riêng cho từng user."""
        return self._locks[user_id]

    async def save_entry(self, entry: MemoryEntry) -> None:
        async with await self._get_lock(entry.user_id):
            self._data[entry.user_id].append(entry)

    async def get_entries(self, user_id: str) -> List[MemoryEntry]:
        async with await self._get_lock(user_id):
            # Luôn trả về Shallow Copy để bảo vệ dữ liệu gốc trên RAM
            return list(self._data[user_id])

    async def get_total_tokens(self, user_id: str) -> int:
        async with await self._get_lock(user_id):
            return sum(entry.tokens for entry in self._data[user_id])

    async def delete_entries(self, user_id: str, entry_ids: List[str]) -> None:
        """Xóa an toàn bằng cách khóa lại mảng trước khi ghi đè."""
        if user_id not in self._data:
            return

        async with await self._get_lock(user_id):
            initial_count = len(self._data[user_id])

            # Thuật toán lọc
            ids_to_remove = set(entry_ids)
            self._data[user_id] = [
                entry
                for entry in self._data[user_id]
                if entry.entry_id not in ids_to_remove
            ]

            deleted = initial_count - len(self._data[user_id])
            if deleted > 0:
                logger.debug(f"🗑️ RAM Storage: Xóa {deleted} tin nhắn (User: {user_id})")

    async def clear_all(self, user_id: str) -> None:
        async with await self._get_lock(user_id):
            if user_id in self._data:
                del self._data[user_id]
            # Xóa luôn ổ khóa để giải phóng bộ nhớ hệ thống
            if user_id in self._locks:
                del self._locks[user_id]
            logger.debug(f"🧹 RAM Storage: Reset trắng bộ nhớ (User: {user_id})")
