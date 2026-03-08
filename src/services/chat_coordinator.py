# src/services/chat_coordinator.py
import logging

from langsmith import traceable

from src.services.llm.base_llm_service import BaseLLMService
from src.services.memories.memory_manager import MemoryManager

logger = logging.getLogger(__name__)


class ChatCoordinator:
    """
    Nhạc Trưởng Giao Tiếp (Orchestrator).
    Đóng vai trò cầu nối duy nhất giữa Discord Gateway (UI) và Hệ thống Core (Memory + LLM).
    """

    def __init__(self, memory_manager: MemoryManager, llm_service: BaseLLMService):
        self.memory = memory_manager
        self.llm = llm_service

    @traceable(
        name="Full_Chat_Turn", run_type="chain", tags=["coordinator", "chat_cycle"]
    )
    async def process_message(self, user_id: str, content: str) -> str:
        """
        Xử lý trọn vẹn 1 vòng đời của tin nhắn.
        """
        try:
            # 1. Ghi nhận tin nhắn của User vào Bộ nhớ (Tầng 1 tự lo việc phân tích & lưu)
            await self.memory.add_message(user_id=user_id, role="user", content=content)

            # 2. Rút trích Ngữ cảnh (System Prompt từ T3 + Lịch sử từ T1/T2)
            sys_prompt, context_msgs = await self.memory.get_context(
                user_id=user_id, current_query=content
            )

            # 3. Giao cho LLM sinh câu trả lời
            bot_response = await self.llm.generate_response(
                messages=context_msgs, system_prompt=sys_prompt
            )

            # 4. Ghi nhận câu trả lời của Bot vào Bộ nhớ
            if bot_response and not bot_response.startswith("Error:"):
                await self.memory.add_message(
                    user_id=user_id, role="assistant", content=bot_response
                )

            return bot_response

        except Exception as e:
            logger.error(
                f"❌ ChatCoordinator: Lỗi nghiêm trọng khi xử lý tin nhắn: {e}"
            )
            return "Xin lỗi, hệ thống não bộ của tôi đang gặp chút trục trặc. Bạn chờ xíu nhé!"

    async def clear_chat_history(self, user_id: str):
        """Xóa bộ nhớ tạm (Tầng 1) của User."""
        await self.memory.clear_session(user_id)
