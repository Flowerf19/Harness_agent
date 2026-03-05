import asyncio
import logging
from typing import Any

from .activity_monitor import ActivityMonitor

logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Dịch vụ quản lý scheduling và background tasks cho memory system.
    """

    def __init__(
        self,
        data_dir: str,
        memory_decay_service=None,
        summary_scheduler=None,
        cleanup_service=None,
    ):
        self.data_dir = data_dir

        # Services dependencies
        self.memory_decay_service = memory_decay_service
        self.summary_scheduler = summary_scheduler
        self.cleanup_service = cleanup_service

        # Tạo activity monitor
        self.activity_monitor = ActivityMonitor()

        # Cài đặt callback cho các trigger
        if self.memory_decay_service:
            self.activity_monitor.add_message_count_callback(
                self.memory_decay_service.on_message_count_trigger
            )
            self.activity_monitor.add_timeout_callback(
                self.memory_decay_service.on_timeout_trigger
            )
            self.activity_monitor.add_priority_event_callback(
                self.memory_decay_service.on_priority_event_trigger
            )

        # Theo dõi thời gian hoạt động của người dùng
        self.last_activity = {}
        self.working_memory_threshold = 20  # Số lượng tin nhắn trước khi cập nhật
        self.inactivity_timeout = 600  # 10 phút không hoạt động (tính bằng giây)

        # Cờ để kiểm soát vòng lặp
        self.running = False
        self.task = None

        # Task 5: Thêm biến lưu vết cho Overlapping Window
        self.last_processed_index: dict[str, int] = {}  # user_id -> index

    def start(self):
        """Khởi động dịch vụ nền và activity monitor"""
        if not self.running:
            self.running = True
            self.task = asyncio.create_task(self._background_worker())
            self.activity_monitor.start_monitoring()  # Bắt đầu theo dõi
            logger.info("🔄 SchedulerService started with activity monitoring")

    def stop(self):
        """Dừng dịch vụ nền và activity monitor"""
        if self.running:
            self.running = False
            if self.task:
                self.task.cancel()
            self.activity_monitor.stop_monitoring()  # Dừng theo dõi
            logger.info("🔄 SchedulerService stopped")

    async def _background_worker(self):
        """Vòng lặp xử lý nền chính"""
        while self.running:
            try:
                # Kiểm tra và cập nhật core personas định kỳ nếu có summary scheduler
                if self.summary_scheduler:
                    await self.summary_scheduler.check_and_update_core_personas()

                # Chờ 60 giây trước lần kiểm tra tiếp theo
                await asyncio.sleep(60)

            except asyncio.CancelledError:
                logger.info("🔄 Background worker cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Error in background worker: {e}")
                await asyncio.sleep(60)  # Chờ 60 giây trước khi thử lại

    def record_user_activity(self, user_id: str):
        """Ghi nhận hoạt động của người dùng"""
        self.activity_monitor.record_activity(user_id)

    async def record_priority_event(
        self, user_id: str, event_type: str, event_data: Any = None
    ):
        """Ghi nhận sự kiện ưu tiên"""
        await self.activity_monitor.record_priority_event(
            user_id, event_type, event_data
        )

    def get_messages_for_processing(
        self, user_id: str, all_messages: list, window_size: int = 20, overlap: int = 5
    ) -> list:
        """
        Lấy messages để xử lý với overlapping window.

        Args:
            user_id: ID người dùng
            all_messages: Tất cả messages hiện có
            window_size: Số lượng messages tối đa để xử lý (default: 20)
            overlap: Số lượng messages lùi lại từ lần trước (default: 5)

        Returns:
            Danh sách messages cần xử lý
        """
        last_index = self.last_processed_index.get(user_id, 0)

        # Lùi lại 'overlap' tin từ lần trước (nhưng không âm)
        start_index = max(0, last_index - overlap)

        # Lấy messages từ start_index
        messages_to_process = all_messages[start_index:]

        # Giới hạn số lượng
        if len(messages_to_process) > window_size:
            messages_to_process = messages_to_process[:window_size]

        return messages_to_process
