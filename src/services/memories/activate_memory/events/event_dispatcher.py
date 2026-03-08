import asyncio
import logging
from enum import Enum
from typing import Any, Callable, Dict, List

from langsmith import traceable

logger = logging.getLogger(__name__)


class ActiveMemoryEvent(str, Enum):
    CRITICAL_INFO_DETECTED = (
        "critical_info_detected"  # Kích hoạt khi có Semantic > 0.85
    )
    TOKEN_LIMIT_REACHED = "token_limit_reached"  # Kích hoạt khi RAM > MAX_TOKENS
    SESSION_TIMEOUT = "session_timeout"  # Kích hoạt khi user im lặng 30 phút


class EventDispatcher:
    """Bộ phát tín hiệu trung tâm của Active Memory."""

    def __init__(self):
        # Lưu danh sách các hàm callback (async) cho từng loại sự kiện
        self._listeners: Dict[ActiveMemoryEvent, List[Callable]] = {
            event: [] for event in ActiveMemoryEvent
        }

    def subscribe(self, event_type: ActiveMemoryEvent, callback: Callable):
        """Đăng ký một 'lỗ tai' để nghe sự kiện."""
        if callback not in self._listeners[event_type]:
            self._listeners[event_type].append(callback)

    @traceable(name="T1_Event_Emitted", run_type="chain", tags=["tier_1", "events"])
    def emit(self, event_type: ActiveMemoryEvent, user_id: str, data: Any = None):
        """
        Phát sự kiện. Chạy các callback dạng Fire-and-Forget (Bắn và Quên)
        để không làm chậm luồng chat chính.
        """
        listeners = self._listeners.get(event_type, [])
        if not listeners:
            return

        logger.info(f"🔔 Event Bắn ra: {event_type.value} (User: {user_id})")

        for callback in listeners:
            # Chạy async task ngầm, không block Tầng 1
            asyncio.create_task(self._safe_execute(callback, event_type, user_id, data))

    async def _safe_execute(
        self, callback: Callable, event_type: ActiveMemoryEvent, user_id: str, data: Any
    ):
        """Bọc try/catch để nếu callback (Tầng 2/3) lỗi thì Tầng 1 không bị crash theo."""
        try:
            await callback(event_type, user_id, data)
        except Exception as e:
            logger.error(
                f"❌ Lỗi khi thực thi callback cho event {event_type.value}: {e}"
            )
