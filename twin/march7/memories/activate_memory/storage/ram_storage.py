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
        # Lưu dữ liệu theo cấu trúc: { "scope:scope_id": [MemoryEntry,...] }
        self._data: Dict[str, List[MemoryEntry]] = defaultdict(list)
        # Hệ thống khóa (Lock) theo từng scope để chống Race Condition
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _scope_key(self, scope: str, scope_id: str | None = None) -> str:
        if scope_id is None:
            scope_id = scope
            scope = "user"
        return f"{scope}:{scope_id}"

    async def _get_lock(self, scope: str, scope_id: str | None = None) -> asyncio.Lock:
        """Lấy ổ khóa riêng cho từng scope."""
        return self._locks[self._scope_key(scope, scope_id)]

    async def save_entry(self, entry: MemoryEntry) -> None:
        key = self._scope_key(entry.scope, entry.scope_id)
        async with await self._get_lock(entry.scope, entry.scope_id):
            self._data[key].append(entry)

    async def get_entries(self, scope: str, scope_id: str | None = None) -> List[MemoryEntry]:
        key = self._scope_key(scope, scope_id)
        async with await self._get_lock(scope, scope_id):
            # Luôn trả về Shallow Copy để bảo vệ dữ liệu gốc trên RAM
            return list(self._data[key])

    async def get_total_tokens(self, scope: str, scope_id: str | None = None) -> int:
        key = self._scope_key(scope, scope_id)
        async with await self._get_lock(scope, scope_id):
            return sum(entry.tokens for entry in self._data[key])

    async def delete_entries(
        self, scope: str, scope_id: str | None = None, entry_ids: List[str] | None = None
    ) -> None:
        """Xóa an toàn bằng cách khóa lại mảng trước khi ghi đè."""
        if entry_ids is None:
            entry_ids = scope_id if isinstance(scope_id, list) else []
            scope_id = None
        key = self._scope_key(scope, scope_id)
        if key not in self._data:
            return

        async with await self._get_lock(scope, scope_id):
            initial_count = len(self._data[key])

            # Thuật toán lọc
            ids_to_remove = set(entry_ids)
            self._data[key] = [
                entry
                for entry in self._data[key]
                if entry.entry_id not in ids_to_remove
            ]

            deleted = initial_count - len(self._data[key])
            if deleted > 0:
                logger.debug(f"🗑️ RAM Storage: Xóa {deleted} tin nhắn ({key})")

    async def clear_all(self, scope: str, scope_id: str | None = None) -> None:
        key = self._scope_key(scope, scope_id)
        async with await self._get_lock(scope, scope_id):
            if key in self._data:
                del self._data[key]
            # Xóa luôn ổ khóa để giải phóng bộ nhớ hệ thống
            if key in self._locks:
                del self._locks[key]
            logger.debug(f"🧹 RAM Storage: Reset trắng bộ nhớ ({key})")


# Alias for backward compatibility
LocalMemoryDB = RamStorage
