import asyncio
import logging
from typing import Dict, List, Tuple, TYPE_CHECKING

from langsmith import traceable

# --- IMPORTS TẦNG 1 (Active Memory) ---
from src.services.memories.activate_memory.activate_memory_service import (
    ActiveMemoryService,
)
from src.services.memories.activate_memory.events.event_dispatcher import (
    ActiveMemoryEvent,
    EventDispatcher,
)

# --- IMPORTS TẦNG 3 (Core Memory) ---
from src.services.memories.core_memory.core_manager import CoreManager

# --- IMPORTS TẦNG 2 (Overflow Queue & Evernight) ---
if TYPE_CHECKING:
    from src.services.queue.overflow_queue import OverflowQueue
    from src.agents.evernight.spawner import EvernightSpawner

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Trái tim của toàn bộ Hệ thống Trí nhớ 3 Tầng.
    Nơi kết nối RAM (T1), RAG Ổ cứng (T2) và Tiềm thức (T3).
    """

    def __init__(
        self,
        active_memory: ActiveMemoryService,
        core_memory: CoreManager,
        event_dispatcher: EventDispatcher,
        overflow_queue: "OverflowQueue | None" = None,
        evernight_spawner: "EvernightSpawner | None" = None,
    ):
        self.t1 = active_memory
        self.t3 = core_memory
        self.events = event_dispatcher
        self.overflow_queue = overflow_queue
        self.spawner = evernight_spawner

        # BƯỚC WIRING QUAN TRỌNG NHẤT: Đăng ký sự kiện (Pub/Sub)
        self._wire_events()

        queue_status = "enabled" if overflow_queue else "disabled"
        logger.debug(
            f"🧠 MemoryManager: Đã khởi tạo và nối dây thành công 3 Tầng Trí Nhớ! "
            f"(Overflow queue: {queue_status})"
        )

    def _wire_events(self):
        """
        Cắm dây thần kinh: Khi T1 la lên, T2 sẽ lắng nghe và tự động làm việc.
        Lưu ý: T3 (Core Memory) giờ được cập nhật bởi Agent qua Tool, không còn event-driven.
        """
        # T1 báo tràn RAM -> T2 tóm tắt RAG, sau đó T1 tự dọn dẹp
        self.events.subscribe(
            ActiveMemoryEvent.TOKEN_LIMIT_REACHED, self._handle_memory_overflow
        )

    async def _handle_memory_overflow(self, event_type: str, user_id: str, data: dict):
        """Handle T1 overflow by queueing to Evernight."""
        snapshot = data.get("snapshot", [])

        # Queue snapshot for Evernight processing
        if self.overflow_queue:
            await self.overflow_queue.push(user_id, snapshot)
            logger.debug(f"📤 MemoryManager: Queued overflow for user {user_id}")

        # Spawn Evernight task (fire and forget)
        if self.spawner:
            asyncio.create_task(self.spawner.spawn_for_user(user_id, snapshot))

        # Cleanup T1 immediately to free space
        await self.t1.force_cleanup(user_id)

    # ==========================================
    # CÁC HÀM API PUBLIC CHO DISCORD BOT GỌI VÀO
    # ==========================================

    @traceable(
        name="Master_Add_Message", run_type="chain", tags=["memory_manager", "write"]
    )
    async def add_message(self, user_id: str, role: str, content: str) -> None:
        """
        Hàm ghi: Bot chỉ cần gọi hàm này khi có tin nhắn mới (Của User hoặc của Bot).
        Mọi logic đánh giá, đếm token, bắn sự kiện đã có T1 lo ngầm.
        """
        await self.t1.add_message(user_id, role, content)

    @traceable(
        name="Master_Get_Context",
        run_type="chain",
        tags=["memory_manager", "read", "context_assembly"],
    )
    async def get_context(
        self, user_id: str, current_query: str
    ) -> Tuple[str, List[Dict]]:
        """
        Lấy context từ T1 (Active) và T3 (Core) chạy song song.
        T2 (Episodic) đã được loại bỏ.
        """
        async def _run_t3_system_prompt():
            return await self.t3.get_system_prompt_context(user_id)

        async def _run_t1_context():
            return await self.t1.get_context_for_llm(user_id)

        # Chạy 2 task song song
        system_prompt, context_messages = await asyncio.gather(
            _run_t3_system_prompt(),
            _run_t1_context()
        )

        return system_prompt, context_messages

    async def clear_session(self, user_id: str):
        """Xóa trắng Tầng 1 khi user im lặng quá lâu (Session Timeout)."""
        await self.t1.reset_session(user_id)