import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from .context_builder import ContextBuilder
from .context_manager import ContextManager, MessageCategory, WorkingMemoryEntry
from .priority_queue import PriorityQueue
from .token_manager import TokenManager

logger = logging.getLogger(__name__)


class WorkingMemoryService:
    """
    Dịch vụ quản lý Working Memory (Tầng 1 - Ngắn hạn)
    """

    def __init__(self, max_capacity: int = 20, trigger_threshold: int = 20):
        # Initialize sub-services
        self.context_manager = ContextManager(max_capacity, trigger_threshold)
        self.context_builder = ContextBuilder()
        self.priority_queue = PriorityQueue()
        self.token_manager = TokenManager()

        # Maintain backward compatibility references
        self.memories = self.context_manager.memories
        self.trigger_callbacks = self.context_manager.trigger_callbacks
        self.max_capacity = max_capacity
        self.trigger_threshold = trigger_threshold

    def add_message(self, user_id: str, role: str, content: str) -> WorkingMemoryEntry:
        """
        Thêm tin nhắn vào working memory với đánh giá mức độ quan trọng
        """
        # Add message through context manager
        entry = self.context_manager.add_message(user_id, role, content)

        # Update priority using priority queue
        self.priority_queue.update_entry_priority(entry, content, role)

        logger.debug(
            f"📥 Added message to working memory for {user_id}: {content[:50]}..."
        )

        return entry

    def _evaluate_importance(
        self, content: str, role: str
    ) -> tuple[float, MessageCategory]:
        """
        Đánh giá mức độ quan trọng của tin nhắn (delegated to PriorityQueue)
        """
        return self.priority_queue.evaluate_importance(content, role)

    def get_context(
        self, user_id: str, max_entries: int = 5
    ) -> List[WorkingMemoryEntry]:
        """
        Lấy ngữ cảnh gần đây từ working memory theo thứ tự thời gian.
        Trả về các tin nhắn mới nhất theo thứ tự thời gian (cũ → mới).
        """
        return self.context_builder.get_context(self.memories, user_id, max_entries)

    def get_recent_conversation(
        self, user_id: str, max_entries: int = 3
    ) -> List[WorkingMemoryEntry]:
        """
        Lấy cuộc trò chuyện gần đây theo thứ tự thời gian
        """
        return self.context_builder.get_recent_conversation(
            self.memories, user_id, max_entries
        )

    def search_by_category(
        self, user_id: str, category: MessageCategory, limit: int = 5
    ) -> List[WorkingMemoryEntry]:
        """
        Tìm kiếm các entry theo danh mục
        """
        return self.context_builder.search_by_category(
            self.memories, user_id, category, limit
        )

    def _check_trigger_conditions(self, user_id: str):
        """
        Kiểm tra các điều kiện để kích hoạt các hành động
        """
        self.context_manager._check_trigger_conditions(user_id)

    def register_trigger_callback(self, callback_func):
        """
        Đăng ký hàm callback để xử lý các trigger
        """
        self.context_manager.register_trigger_callback(callback_func)

    def _trigger_callback(self, trigger_type: str, user_id: str, data: any):
        """
        Kích hoạt các callback đã đăng ký
        """
        self.context_manager._trigger_callback(trigger_type, user_id, data)

    def cleanup_old_entries(self, user_id: str, max_entries: int = 50) -> int:
        """
        Dọn dẹp entries cũ theo thuật toán FIFO.
        Chỉ giữ lại N tin nhắn mới nhất theo thời gian.
        """
        return self.context_manager.cleanup_old_entries(user_id, max_entries)

    def get_statistics(self, user_id: str) -> Dict:
        """
        Lấy thống kê về working memory của người dùng
        """
        return self.context_manager.get_statistics(user_id)

    def clear_memory(self, user_id: str):
        """
        Xóa toàn bộ working memory của người dùng
        """
        self.context_manager.clear_memory(user_id)

    async def _get_history_path(self, user_id: str):
        """Lấy đường dẫn file history của user."""
        return await self.context_manager._get_history_path(user_id)

    async def save_to_persistent_history(self, user_id: str, messages: list):
        """
        Lưu tin nhắn vào history file với Lock để tránh conflict.
        """
        await self.context_manager.save_to_persistent_history(user_id, messages)

    async def append_message_to_persistent_history(self, user_id: str, message: dict):
        """
        Thêm một tin nhắn vào history.
        """
        await self.context_manager.append_message_to_persistent_history(
            user_id, message
        )

    async def get_persistent_history(self, user_id: str) -> list:
        """
        Đọc history từ file.
        """
        return await self.context_manager.get_persistent_history(user_id)

    def get_persistent_history_sync(self, user_id: str) -> list:
        """
        Đọc history từ file (sync version).
        """
        return self.context_manager.get_persistent_history_sync(user_id)

    def save_to_persistent_history_sync(self, user_id: str, messages: list):
        """
        Lưu tin nhắn vào history file (sync version).
        """
        self.context_manager.save_to_persistent_history_sync(user_id, messages)

    def append_message_to_persistent_history_sync(self, user_id: str, message: dict):
        """
        Thêm một tin nhắn vào history (sync version).
        """
        self.context_manager.append_message_to_persistent_history_sync(user_id, message)
