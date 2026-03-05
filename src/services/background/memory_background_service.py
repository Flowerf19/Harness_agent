import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

from .activity_monitor import ActivityMonitor
from .cleanup_service import CleanupService
from .memory_decay_service import MemoryDecayService
from .scheduler_service import SchedulerService
from .summary_scheduler import SummaryScheduler

logger = logging.getLogger(__name__)


class MemoryBackgroundService:
    """
    Dịch vụ chạy nền để xử lý cập nhật Episodic Memory và Core Persona
    (Backward compatible wrapper for the new background services)
    """

    def __init__(
        self,
        llm_service,
        data_dir: str,
        relationship_service=None,
        working_memory_service=None,
    ):
        self.llm_service = llm_service
        self.data_dir = data_dir
        self.relationship_service = relationship_service
        self.working_memory_service = working_memory_service

        # Tạo các service con
        self.cleanup_service = CleanupService(data_dir)
        self.summary_scheduler = SummaryScheduler(
            llm_service, data_dir, relationship_service, None
        )
        self.memory_decay_service = MemoryDecayService(
            llm_service,
            data_dir,
            relationship_service,
            working_memory_service,
            self.cleanup_service,
            None,  # scheduler_service will be set below
        )
        self.scheduler_service = SchedulerService(
            data_dir,
            self.memory_decay_service,
            self.summary_scheduler,
            self.cleanup_service,
        )

        # Set scheduler_service reference in memory_decay_service
        self.memory_decay_service.scheduler_service = self.scheduler_service

        # Đường dẫn lưu trữ
        self.user_summaries_dir = os.path.join(data_dir, "user_summaries")

        # Cài đặt callback cho các trigger (đã được thiết lập trong scheduler_service)
        # Theo dõi thời gian hoạt động của người dùng
        self.last_activity = {}
        self.working_memory_threshold = 20  # Số lượng tin nhắn trước khi cập nhật
        self.inactivity_timeout = 600  # 10 phút không hoạt động (tính bằng giây)

        # Cờ để kiểm soát vòng lặp
        self.running = False

        # Task 5: Thêm biến lưu vết cho Overlapping Window
        self.last_processed_index = self.scheduler_service.last_processed_index

    def _apply_delta(self, current: dict, delta: dict) -> dict:
        """Áp dụng delta vào persona hiện tại."""
        return self.memory_decay_service._apply_delta(current, delta)

    async def _get_semantic_memory(self, user_id: str) -> dict:
        """Lấy semantic memory (persona) hiện tại của người dùng."""
        return await self.memory_decay_service._get_semantic_memory(user_id)

    async def _save_semantic_memory(self, user_id: str, persona: dict):
        """Lưu semantic memory (persona) của người dùng."""
        await self.memory_decay_service._save_semantic_memory(user_id, persona)

    async def _call_llm(self, prompt: str, user_id: str = None) -> dict:
        """Gọi LLM và parse kết quả."""
        return await self.memory_decay_service._call_llm(prompt, user_id)

    def ensure_user_files_exist(self, user_id: str):
        """Ensure user data files exist"""
        self.memory_decay_service.ensure_user_files_exist(user_id)

    def start(self):
        """Khởi động dịch vụ nền và activity monitor"""
        self.running = True
        self.scheduler_service.start()
        logger.info("🔄 MemoryBackgroundService started with activity monitoring")

    def stop(self):
        """Dừng dịch vụ nền và activity monitor"""
        self.running = False
        self.scheduler_service.stop()
        logger.info("🔄 MemoryBackgroundService stopped")

    def record_user_activity(self, user_id: str):
        """Ghi nhận hoạt động của người dùng"""
        self.scheduler_service.record_user_activity(user_id)

    async def record_priority_event(
        self, user_id: str, event_type: str, event_data: Any = None
    ):
        """Ghi nhận sự kiện ưu tiên"""
        await self.scheduler_service.record_priority_event(
            user_id, event_type, event_data
        )

    async def _on_message_count_trigger(self, user_id: str, condition):
        """Xử lý khi đạt ngưỡng tin nhắn"""
        await self.memory_decay_service.on_message_count_trigger(user_id, condition)

    async def _on_timeout_trigger(self, user_id: str, condition):
        """Xử lý khi timeout (hội thoại dừng)"""
        await self.memory_decay_service.on_timeout_trigger(user_id, condition)

    async def _on_priority_event_trigger(
        self, user_id: str, event_type: str, event_data: Any
    ):
        """Xử lý khi có sự kiện ưu tiên"""
        await self.memory_decay_service.on_priority_event_trigger(
            user_id, event_type, event_data
        )

    def _get_messages_for_processing(
        self, user_id: str, all_messages: list, window_size: int = 20, overlap: int = 5
    ) -> list:
        """
        Lấy messages để xử lý với overlapping window.
        """
        return self.scheduler_service.get_messages_for_processing(
            user_id, all_messages, window_size, overlap
        )

    async def _update_episodic_memory(self, user_id: str, messages: list = None):
        """Cập nhật episodic memory cho người dùng với cơ chế 'Xóa An Toàn'"""
        return await self.memory_decay_service._update_episodic_memory(
            user_id, messages
        )

    def _parse_llm_response(self, response: str) -> dict:
        """Parse JSON response từ LLM."""
        return self.memory_decay_service._parse_llm_response(response)

    async def _get_user_history(self, user_id: str) -> List[Dict]:
        return await self.memory_decay_service._get_user_history(user_id)

    async def _append_to_episodic_memory(self, user_id: str, events: List[Dict]):
        """Thêm các sự kiện vào episodic memory (file nhật ký)"""
        return await self.memory_decay_service._append_to_episodic_memory(
            user_id, events
        )

    async def _cleanup_working_memory(self, user_id: str, messages_to_remove: list):
        """Dọn dẹp working memory sau khi đã trích xuất - chỉ xóa các tin nhắn cụ thể"""
        await self.cleanup_service.cleanup_working_memory(user_id, messages_to_remove)

    async def _check_and_update_core_personas(self):
        """Kiểm tra và cập nhật core personas định kỳ"""
        await self.summary_scheduler.check_and_update_core_personas()

    async def _should_update_core_persona(self, user_id: str) -> bool:
        """Kiểm tra xem có nên cập nhật core persona không"""
        return await self.summary_scheduler._should_update_core_persona(user_id)

    async def _update_core_persona(self, user_id: str):
        """Cập nhật core persona cho người dùng"""
        await self.summary_scheduler.update_core_persona(user_id)

    async def _get_current_summary(self, user_id: str) -> str:
        """Lấy summary hiện tại của người dùng"""
        return await self.summary_scheduler._get_current_summary(user_id)

    async def _save_summary(self, user_id: str, summary: str):
        """Lưu summary của người dùng"""
        await self.summary_scheduler._save_summary(user_id, summary)

    async def _mark_persona_updated(self, user_id: str):
        """Đánh dấu thời gian cập nhật core persona"""
        await self.summary_scheduler._mark_persona_updated(user_id)

    def _get_empty_summary(self) -> str:
        """Get empty summary template"""
        return self.summary_scheduler._get_empty_summary()
