import asyncio
import logging
from typing import Dict, List, Tuple

from langsmith import traceable
from langsmith.run_helpers import tracing_context

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

# --- IMPORTS TẦNG 2 (Episodic Memory) ---
# Giả định bạn đã gói các class T2 vào EpisodicManager
import contextvars
from src.services.memories.episodic_memory.episodic_manager import EpisodicManager

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Trái tim của toàn bộ Hệ thống Trí nhớ 3 Tầng.
    Nơi kết nối RAM (T1), RAG Ổ cứng (T2) và Tiềm thức (T3).
    """

    def __init__(
        self,
        active_memory: ActiveMemoryService,
        episodic_memory: EpisodicManager,
        core_memory: CoreManager,
        event_dispatcher: EventDispatcher,
    ):
        self.t1 = active_memory
        self.t2 = episodic_memory
        self.t3 = core_memory
        self.events = event_dispatcher

        # BƯỚC WIRING QUAN TRỌNG NHẤT: Đăng ký sự kiện (Pub/Sub)
        self._wire_events()
        logger.info(
            "🧠 MemoryManager: Đã khởi tạo và nối dây thành công 3 Tầng Trí Nhớ!"
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
        """Hàm trung gian xử lý luồng khi RAM đầy."""
        snapshot = data.get("snapshot", [])

        # Bước A: Tầng 2 tóm tắt và nhúng Vector vào Qdrant/FAISS
        success = await self.t2.ingest_snapshot(user_id, snapshot)

        if success:
            # Bước B: Gọi Tầng 1 xóa bớt các tin nhắn cũ rác (Smart Cleanup)
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
        Lấy context từ 3 tầng trí nhớ chạy song song.
        Sử dụng tracing_context để preserve parent-child relationship khi chạy asyncio.gather().
        """
        # Lấy parent run_id hiện tại để truyền vào các child tasks
        # Điều này đảm bảo các span con được gắn đúng vào cây trace

        
        # Copy context hiện tại để truyền vào các task chạy song song
        ctx = contextvars.copy_context()
        
        async def _run_t3_system_prompt():
            return await self.t3.get_system_prompt_context(user_id)
        
        async def _run_t1_context():
            return await self.t1.get_context_for_llm(user_id)
        
        async def _run_t2_past_events():
            return await self.t2.retrieve_past_context(user_id, current_query)

        # Chạy 3 task song song với context được preserve
        system_prompt, context_messages, past_events_text = await asyncio.gather(
            _run_t3_system_prompt(),
            _run_t1_context(),
            _run_t2_past_events()
        )

        if past_events_text:
            context_messages.insert(
                0, {"role": "system", "content": past_events_text}
            )

        return system_prompt, context_messages

    async def clear_session(self, user_id: str):
        """Xóa trắng Tầng 1 khi user im lặng quá lâu (Session Timeout)."""
        await self.t1.reset_session(user_id)
