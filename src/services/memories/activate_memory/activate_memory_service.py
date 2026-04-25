import logging
from typing import Dict, List

from langsmith import traceable

from .constants import MAX_WORKING_TOKENS
from .events.event_dispatcher import ActiveMemoryEvent, EventDispatcher
from .management.context_builder import ContextBuilder
from .management.smart_cleanup import SmartCleanup
from .management.token_counter import TokenCounter
from .models import MemoryEntry, MessageCategory
from .storage.base_storage import BaseStorage

logger = logging.getLogger(__name__)


class ActiveMemoryService:
    """
    Facade Tổng Chỉ Huy Tầng 1 (Active Memory).
    Điều phối luồng dữ liệu: Đánh giá -> Đếm Token -> Lưu trữ -> Phát Sự kiện.
    """

    def __init__(
        self,
        storage: BaseStorage,
        token_counter: TokenCounter,
        smart_cleanup: SmartCleanup,
        context_builder: ContextBuilder,
        event_dispatcher: EventDispatcher,
    ):
        # Dependency Injection: Nhận mọi đồ nghề từ ngoài vào
        self.storage = storage
        self.token_counter = token_counter
        self.smart_cleanup = smart_cleanup
        self.context_builder = context_builder
        self.events = event_dispatcher

    @traceable(
        name="T1_Process_New_Message", run_type="chain", tags=["tier_1", "core_flow"]
    )
    async def add_message(self, user_id: str, role: str, content: str) -> MemoryEntry:
        """Luồng chính: Xử lý khi có tin nhắn mới."""

        # 1. Giá trị mặc định (pipeline đã bị loại bỏ)
        score = 0.0
        category = MessageCategory.GENERAL
        extracted_content = None

        # Nếu có nội dung trích xuất từ lệnh (!note), ta chỉ lưu phần đó
        content_to_save = extracted_content if extracted_content else content

        # 2. Đếm Token (Có tính hao phí)
        tokens = self.token_counter.count_entry_tokens(content_to_save)

        # 3. Tạo Entry chuẩn Pydantic
        entry = MemoryEntry(
            user_id=user_id,
            role=role,
            content=content_to_save,
            tokens=tokens,
            importance_score=score,
            category=category,
        )

        # 4. Lưu vào RAM
        await self.storage.save_entry(entry)

        # === 5. KIỂM TRA & BẮT SỰ KIỆN ===

        # Bắt sự kiện Token (Token Trigger)
        current_tokens = await self.storage.get_total_tokens(user_id)
        if current_tokens >= MAX_WORKING_TOKENS:
            # Lấy bản sao lưu (Snapshot) hiện tại ném cho sự kiện
            snapshot = await self.storage.get_entries(user_id)
            self.events.emit(
                ActiveMemoryEvent.TOKEN_LIMIT_REACHED,
                user_id,
                data={"snapshot": snapshot, "current_tokens": current_tokens},
            )

        logger.debug(
            f"📥 ActiveMemory: Đã lưu tin nhắn (User: {user_id} | Score: {score:.2f} | Tokens: {current_tokens}/{MAX_WORKING_TOKENS})"
        )
        return entry

    @traceable(
        name="T1_Get_Context_For_LLM",
        run_type="chain",
        tags=["tier_1", "active_memory", "read", "context_assembly"]
    )
    async def get_context_for_llm(self, user_id: str) -> List[Dict]:
        """Lấy Composite Context (Ngữ cảnh hỗn hợp) để nạp vào Prompt."""
        entries = await self.storage.get_entries(user_id)
        return self.context_builder.build_context(entries)

    async def force_cleanup(self, user_id: str):
        """Hàm này sẽ được MemoryManager gọi NGƯỢC LẠI sau khi Tầng 2 đã tóm tắt xong (Giải quyết Race Condition)."""
        current_tokens = await self.storage.get_total_tokens(user_id)
        await self.smart_cleanup.execute(user_id, current_tokens)

    async def reset_session(self, user_id: str):
        """Xóa trắng RAM của User khi hết Timeout."""
        await self.storage.clear_all(user_id)
