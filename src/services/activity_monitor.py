import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)


@dataclass
class TriggerCondition:
    user_id: str
    last_activity: datetime
    message_count: int
    session_start: datetime


class ActivityMonitor:
    """
    Theo dõi hoạt động người dùng và kích hoạt các trigger
    """

    def __init__(
        self,
        message_threshold: int = 20,
        inactivity_timeout: int = 600,  # 10 minutes
        check_interval: int = 30,
    ):  # 30 seconds
        self.message_threshold = message_threshold
        self.inactivity_timeout = inactivity_timeout
        self.check_interval = check_interval

        # Theo dõi trạng thái người dùng
        self.user_conditions: Dict[str, TriggerCondition] = {}

        # Callback cho các loại trigger
        self.message_count_callbacks: list[Callable] = []
        self.timeout_callbacks: list[Callable] = []
        self.priority_event_callbacks: list[Callable] = []

        # Cờ cho vòng lặp
        self.running = False
        self.monitor_task = None

    def start_monitoring(self):
        """Bắt đầu theo dõi hoạt động"""
        if not self.running:
            self.running = True
            self.monitor_task = asyncio.create_task(self._monitor_loop())
            logger.info(
                f"👀 Activity monitor started (interval: {self.check_interval}s)"
            )

    def stop_monitoring(self):
        """Dừng theo dõi hoạt động"""
        if self.running:
            self.running = False
            if self.monitor_task:
                self.monitor_task.cancel()
            logger.info("👀 Activity monitor stopped")

    async def _monitor_loop(self):
        """Vòng lặp theo dõi chính"""
        while self.running:
            try:
                await self._check_all_conditions()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                logger.info("👀 Monitor loop cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Error in monitor loop: {e}")
                await asyncio.sleep(self.check_interval)

    def record_activity(self, user_id: str):
        """Ghi nhận hoạt động của người dùng"""
        current_time = datetime.now()

        if user_id not in self.user_conditions:
            self.user_conditions[user_id] = TriggerCondition(
                user_id=user_id,
                last_activity=current_time,
                message_count=0,
                session_start=current_time,
            )
        else:
            self.user_conditions[user_id].last_activity = current_time
            self.user_conditions[user_id].message_count += 1

    async def record_priority_event(
        self, user_id: str, event_type: str, event_data: Any = None
    ):
        """Ghi nhận sự kiện ưu tiên cần xử lý ngay"""
        self.record_activity(user_id)  # Cập nhật thời gian hoạt động

        # Gọi các callback cho sự kiện ưu tiên
        for callback in self.priority_event_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(user_id, event_type, event_data)
                else:
                    callback(user_id, event_type, event_data)
            except Exception as e:
                logger.error(f"❌ Error in priority event callback: {e}")

    async def _check_all_conditions(self):
        """Kiểm tra điều kiện cho tất cả người dùng"""
        current_time = datetime.now()
        users_to_check = list(self.user_conditions.keys())

        for user_id in users_to_check:
            if user_id not in self.user_conditions:
                continue

            condition = self.user_conditions[user_id]

            # Kiểm tra điều kiện số lượng tin nhắn
            if condition.message_count >= self.message_threshold:
                await self._trigger_message_count(user_id, condition)

            # Kiểm tra điều kiện timeout
            time_since_activity = current_time - condition.last_activity
            if time_since_activity.total_seconds() >= self.inactivity_timeout:
                await self._trigger_timeout(user_id, condition)

    async def _trigger_message_count(self, user_id: str, condition: TriggerCondition):
        """Kích hoạt trigger khi đạt ngưỡng tin nhắn"""
        logger.info(
            f"📈 Message count trigger for {user_id}: {condition.message_count}/{self.message_threshold}"
        )

        # Gọi các callback
        for callback in self.message_count_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(user_id, condition)
                else:
                    callback(user_id, condition)
            except Exception as e:
                logger.error(f"❌ Error in message count callback: {e}")

        # Reset bộ đếm tin nhắn sau khi kích hoạt
        condition.message_count = 0  # Có thể giữ lại một số tin nhắn gần nhất

    async def _trigger_timeout(self, user_id: str, condition: TriggerCondition):
        """Kích hoạt trigger khi timeout"""
        logger.info(
            f"⏰ Timeout trigger for {user_id}: inactive for {self.inactivity_timeout}s"
        )

        # Gọi các callback
        for callback in self.timeout_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(user_id, condition)
                else:
                    callback(user_id, condition)
            except Exception as e:
                logger.error(f"❌ Error in timeout callback: {e}")

        # Xóa condition sau khi xử lý (hoặc có thể giữ lại để theo dõi lâu dài)
        # del self.user_conditions[user_id]

    def add_message_count_callback(self, callback: Callable):
        """Thêm callback cho trigger số lượng tin nhắn"""
        self.message_count_callbacks.append(callback)

    def add_timeout_callback(self, callback: Callable):
        """Thêm callback cho trigger timeout"""
        self.timeout_callbacks.append(callback)

    def add_priority_event_callback(self, callback: Callable):
        """Thêm callback cho trigger sự kiện ưu tiên"""
        self.priority_event_callbacks.append(callback)

    def get_user_status(self, user_id: str) -> Dict[str, Any]:
        """Lấy trạng thái trigger của người dùng"""
        if user_id not in self.user_conditions:
            return {
                "active": False,
                "message_count": 0,
                "time_since_activity": None,
                "next_trigger": None,
            }

        condition = self.user_conditions[user_id]
        time_since_activity = datetime.now() - condition.last_activity

        next_trigger = None
        if condition.message_count >= self.message_threshold:
            next_trigger = "message_count"
        elif time_since_activity.total_seconds() >= self.inactivity_timeout:
            next_trigger = "timeout"

        return {
            "active": True,
            "message_count": condition.message_count,
            "time_since_activity": time_since_activity.total_seconds(),
            "next_trigger": next_trigger,
            "session_duration": (
                datetime.now() - condition.session_start
            ).total_seconds(),
        }
