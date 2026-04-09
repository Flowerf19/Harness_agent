# src/services/chat_coordinator.py
import logging
import json
import re

from langsmith import traceable

from src.services.llm.base_llm_service import BaseLLMService
from src.services.llm.llm_response import LLMResponse
from src.services.memories.memory_manager import MemoryManager
from src.services.tools.tool_manager import ToolManager 

logger = logging.getLogger(__name__)


def extract_tool_json(text: str) -> tuple[dict | None, str]:
    """
    Extract tool JSON từ text LLM response.
    Hỗ trợ nhiều format: _____{...}_____, ```tool\n{...}\n```, hoặc raw JSON.
    
    Returns:
        (tool_data, remaining_text) - tool_data là dict nếu tìm thấy, None nếu không.
    """
    # Tìm vị trí bắt đầu của JSON - tìm dấu { đầu tiên có "tool" sau nó
    start_idx = None
    
    # Tìm tất cả các dấu { và kiểm tra xem có "tool" sau đó
    for i, char in enumerate(text):
        if char == '{':
            # Kiểm tra xem từ vị trí này có chứa "tool" trong JSON hợp lệ
            # Đếm bracket để tìm JSON block
            brace_count = 0
            end_idx = None
            for j in range(i, len(text)):
                if text[j] == '{':
                    brace_count += 1
                elif text[j] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = j + 1
                        break
            
            if end_idx:
                json_str = text[i:end_idx]
                try:
                    data = json.loads(json_str)
                    if "tool" in data:
                        return data, text[:i] + text[end_idx:]
                except json.JSONDecodeError as e:
                        # JSON không hợp lệ, log để debug
                        logger.warning(f"⚠️ JSON decode error at pos {i}: {e} - JSON: {json_str[:200]}")
                        continue
    
    return None, text


class ChatCoordinator:
    """
    Nhạc Trưởng Giao Tiếp (Orchestrator).
    Đóng vai trò cầu nối duy nhất giữa Discord Gateway (UI) và Hệ thống Core (Memory + LLM + Tools).
    """

    def __init__(
        self,
        memory_manager: MemoryManager,
        llm_service: BaseLLMService,
        tool_manager: ToolManager = None,
    ):
        self.memory = memory_manager
        self.llm = llm_service
        self.tool_manager = tool_manager

    @traceable(
        name="Full_Chat_Turn", run_type="chain", tags=["coordinator", "chat_cycle"]
    )
    async def process_message(self, user_id: str, content: str) -> str:
        """
        Xử lý trọn vẹn 1 vòng đời của tin nhắn với Vòng lặp Agent.
        """
        try:
            # 1. Ghi nhận tin nhắn của User vào Bộ nhớ
            await self.memory.add_message(user_id=user_id, role="user", content=content)

            # 2. Rút trích Ngữ cảnh
            sys_prompt, context_msgs = await self.memory.get_context(
                user_id=user_id, current_query=content
            )

            # VÒNG LẶP AGENT (Tối đa 3 lần lặp để tránh bot kẹt trong vòng lặp vô tận)
            max_iterations = 3
            for i in range(max_iterations):
                # 3. Giao cho LLM sinh câu trả lời
                llm_response = await self.llm.generate_response(
                    messages=context_msgs, system_prompt=sys_prompt
                )

                # Lấy text để kiểm tra
                response_text = llm_response.content if isinstance(llm_response, LLMResponse) else llm_response

                # 3.5 Kiểm tra xem LLM có muốn dùng Tool không
                # Sử dụng hàm extract_tool_json để parse JSON an toàn
                tool_data, remaining_text = extract_tool_json(response_text)
                
                # Debug: Log raw response để xem format
                if "tool" in response_text:
                    logger.debug(f"🔍 Raw response có 'tool': {response_text[:500]}")

                if tool_data and self.tool_manager:
                    # NẾU LLM MUỐN DÙNG TOOL -> Khoan gửi cho user!
                    logger.info(f"🛠️ Agent muốn dùng tool: {tool_data.get('tool')} (Lần lặp {i+1}/{max_iterations})")
                    
                    try:
                        tool_name = tool_data.get("tool")
                        tool_args = tool_data.get("args", {})
                        
                        # Chạy tool thực tế
                        tool_result = await self.tool_manager.execute_tool(tool_name, tool_args)
                        logger.info(f"✅ Tool executed successfully")
                        
                        # Ghi nhận kết quả vào context_msgs để LLM đọc được ở vòng lặp tiếp theo
                        context_msgs.append({"role": "assistant", "content": f"Đã gọi công cụ: {tool_name}"})
                        context_msgs.append({"role": "system", "content": f"Kết quả từ hệ thống:\n{tool_result}\n\nHãy suy nghĩ tiếp hoặc trả lời user."})
                        
                        # Quay lại đầu vòng lặp để LLM đọc kết quả
                        continue 
                        
                    except Exception as tool_err:
                        logger.error(f"Lỗi khi parse hoặc chạy tool: {tool_err}")
                        break
                
                else:
                    # KHÔNG CÓ TOOL CALL -> Đây là câu trả lời cuối cùng
                    break 

            # KẾT THÚC VÒNG LẶP AGENT

            # 4. Xử lý response và extract token usage
            bot_response: str
            if isinstance(llm_response, LLMResponse):
                bot_response = llm_response.content
                logger.info(
                    f"📊 Token Usage for user {user_id}: "
                    f"Input={llm_response.input_tokens}, "
                    f"Output={llm_response.output_tokens}, "
                    f"Total={llm_response.total_tokens}"
                )
            else:
                bot_response = llm_response

            # Dọn dẹp thẻ _____ hoặc ```tool``` bị sót trước khi gửi user
            bot_response = re.sub(r'_____.*?_____```tool.*?```', "", bot_response, flags=re.DOTALL).strip()

            # 5. Ghi nhận câu trả lời của Bot vào Bộ nhớ
            if bot_response and not bot_response.startswith("Error:"):
                await self.memory.add_message(
                    user_id=user_id, role="assistant", content=bot_response
                )

            return bot_response

        except Exception as e:
            logger.error(f"❌ ChatCoordinator: Lỗi nghiêm trọng khi xử lý tin nhắn: {e}")
            return "Xin lỗi, hệ thống não bộ của tôi đang gặp chút trục trặc. Bạn chờ xíu nhé!"

    async def clear_chat_history(self, user_id: str):
        """Xóa bộ nhớ tạm (Tầng 1) của User."""
        await self.memory.clear_session(user_id)