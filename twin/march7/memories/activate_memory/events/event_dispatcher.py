import asyncio
import logging
import contextvars
from enum import Enum
from typing import Any, Callable, Dict, List

from langsmith import traceable

logger = logging.getLogger(__name__)


class ActiveMemoryEvent(str, Enum):
    """Events for T1 Active Memory overflow handling."""
    TOKEN_LIMIT_REACHED = "token_limit_reached"  # Kích hoạt khi RAM > MAX_TOKENS → OverflowQueue


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
        
        Sử dụng contextvars.copy_context() để preserve tracing context
        cho các async task chạy ngầm.
        """
        listeners = self._listeners.get(event_type, [])
        if not listeners:
            return

        logger.info(f"🔔 Event Bắn ra: {event_type.value} (User: {user_id})")

        # Copy context hiện tại để truyền vào các task con
        # Điều này đảm bảo tracing context được preserve
        ctx = contextvars.copy_context()

        for callback in listeners:
            # Chạy async task ngầm với context được preserve
            # Sử dụng context.run để wrap task creation
            task = asyncio.create_task(
                self._safe_execute_with_context(
                    callback, event_type, user_id, data, ctx
                )
            )

    async def _safe_execute_with_context(
        self,
        callback: Callable,
        event_type: ActiveMemoryEvent,
        user_id: str,
        data: Any,
        ctx: contextvars.Context,
    ):
        """
        Wrapper để chạy callback với context đã được preserve.
        Bọc try/catch để nếu callback (Tầng 2/3) lỗi thì Tầng 1 không bị crash theo.
        """
        try:
            # Chạy callback trong context đã copy
            await ctx.run(self._execute_callback, callback, event_type, user_id, data)
        except Exception as e:
            logger.error(
                f"❌ Lỗi khi thực thi callback cho event {event_type.value}: {e}"
            )

    async def _execute_callback(
        self, callback: Callable, event_type: ActiveMemoryEvent, user_id: str, data: Any
    ):
        """Thực thi callback thực sự."""
        await callback(event_type, user_id, data)
