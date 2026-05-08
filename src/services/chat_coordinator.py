# src/services/chat_coordinator.py
import logging
import asyncio
import uuid
import json
from typing import Dict, List, Any, Optional

from langsmith import traceable

from src.services.llm.base_llm_service import BaseLLMService
from src.services.llm.llm_response import LLMResponse
from src.services.memories.memory_manager import MemoryManager
from src.services.tools.mcp_client import MCPClient
from src.services.tools.exceptions import BashExecutorUnavailableError

logger = logging.getLogger(__name__)

# Timeout cho mỗi tool execution (seconds)
TOOL_EXECUTION_TIMEOUT = 60


class ChatCoordinator:
    """
    Nhạc Trưởng Giao Tiếp (Orchestrator).
    Đóng vai trò cầu nối duy nhất giữa Discord Gateway (UI) và Hệ thống Core (Memory + LLM + Tools).

    [MỚI] Hỗ trợ Native Function Calling (API Tool Calling):
    - Sử dụng llm_response.tool_calls thay vì regex parsing
    - Hỗ trợ multiple tool calls trong 1 response
    - Timeout cho mỗi tool execution
    - Format context messages đúng chuẩn API (Qwen/Gemini)
    """

    def __init__(
        self,
        memory_manager: MemoryManager,
        llm_service: BaseLLMService,
        mcp_client: Optional[MCPClient] = None,
        use_native_tools: bool = True,  # [MỚI] Enable native tool calling by default
    ):
        self.memory = memory_manager
        self.llm = llm_service
        self.mcp_client = mcp_client
        self.use_native_tools = use_native_tools

        # Detect LLM service type for context message formatting
        self._llm_type = self._detect_llm_type()

        # Get model name from LLM service
        self._model_name = getattr(self.llm, 'model', 'unknown')

        # Log initialization
        tool_mode = "MCP Client" if mcp_client else "No tools"
        logger.debug(f"🔧 ChatCoordinator initialized: use_native_tools={self.use_native_tools}, llm_type={self._llm_type}, model={self._model_name}, tool_mode={tool_mode}")

    def _detect_llm_type(self) -> str:
        """Detect LLM service type for proper context message formatting."""
        class_name = self.llm.__class__.__name__
        if "Gemini" in class_name:
            return "gemini"
        elif "Qwen" in class_name or "LMStudio" in class_name:
            return "openai"  # Qwen and LM Studio use OpenAI format
        else:
            return "openai"  # Default to OpenAI format

    def _format_tool_call_message(self, tool_calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Format assistant message with tool calls for context.

        Args:
            tool_calls: List of tool call dicts with id, name, arguments

        Returns:
            Message dict in proper format for the LLM API
        """
        if self._llm_type == "gemini":
            # Gemini format: {"role": "model", "parts": [{"functionCall": {...}}]}
            parts = []
            for tc in tool_calls:
                parts.append({
                    "functionCall": {
                        "name": tc["name"],
                        "args": tc["arguments"]
                    }
                })
            return {"role": "model", "parts": parts}
        else:
            # OpenAI/Qwen/LM Studio format
            # IMPORTANT: arguments must be JSON string, not dict!
            formatted_tool_calls = []
            for tc in tool_calls:
                formatted_tool_calls.append({
                    "id": tc.get("id", str(uuid.uuid4())),
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"])  # Convert dict to JSON string
                    }
                })
            return {"role": "assistant", "content": "", "tool_calls": formatted_tool_calls}

    def _format_tool_result_message(self, tool_call_id: str, tool_name: str, result: str) -> Dict[str, Any]:
        """
        Format tool result message for context.

        Args:
            tool_call_id: ID of the tool call (for OpenAI format)
            tool_name: Name of the tool
            result: Result string from tool execution

        Returns:
            Message dict in proper format for the LLM API
        """
        if self._llm_type == "gemini":
            # Gemini format: {"role": "user", "parts": [{"functionResponse": {...}}]}
            return {
                "role": "user",
                "parts": [{
                    "functionResponse": {
                        "name": tool_name,
                        "response": {"result": result}
                    }
                }]
            }
        else:
            # OpenAI/Qwen/LM Studio format
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": result
            }

    @traceable(
        name="Full_Chat_Turn", run_type="chain", tags=["coordinator", "chat_cycle"]
    )
    async def process_message(self, user_id: str, content: str) -> str:
        """
        Xử lý trọn vẹn 1 vòng đời của tin nhắn với Vòng lặp Agent.
        [MỚI] Sử dụng Native Function Calling thay vì regex parsing.
        """
        try:
            # 1. Ghi nhận tin nhắn của User vào Bộ nhớ
            await self.memory.add_message(user_id=user_id, role="user", content=content)

            # 2. Rút trích Ngữ cảnh
            sys_prompt, context_msgs = await self.memory.get_context(
                user_id=user_id, current_query=content
            )

            # VÒNG LẶP AGENT (Tối đa 10 lần lặp để tránh bot kẹt trong vòng lặp vô tận)
            max_iterations = 10
            for i in range(max_iterations):
                # 3. Giao cho LLM sinh câu trả lời
                # [MỚI] Pass use_native_tools flag
                llm_response = await self.llm.generate_response(
                    messages=context_msgs,
                    system_prompt=sys_prompt,
                    use_native_tools=self.use_native_tools
                )

                # [MỚI] Kiểm tra tool_calls từ LLMResponse
                if isinstance(llm_response, LLMResponse) and llm_response.has_tool_calls():
                    # NẾU LLM MUỐN DÙNG TOOL -> Khoan gửi cho user!
                    tool_calls = llm_response.tool_calls
                    logger.debug(f"🛠️ Agent wants to use {len(tool_calls)} tools: {[tc['name'] for tc in tool_calls]} (iteration {i+1}/{max_iterations})")

                    # Format assistant message with tool calls
                    tool_call_msg = self._format_tool_call_message(tool_calls)
                    context_msgs.append(tool_call_msg)

                    # [MỚI] Hỗ trợ multiple tool calls - chạy sequential
                    remaining_calls = max_iterations - i - 1  # Số lần gọi còn lại
                    for tc in tool_calls:
                        tool_name = tc["name"]
                        tool_args = tc["arguments"]
                        tool_call_id = tc.get("id", str(uuid.uuid4()))

                        try:
                            # MCP Architecture
                            tool_result = await asyncio.wait_for(
                                self.mcp_client.execute_tool(tool_name, tool_args),
                                timeout=TOOL_EXECUTION_TIMEOUT
                            )

                            logger.debug(f"✅ Tool '{tool_name}' executed successfully")

                        except BashExecutorUnavailableError:
                            raise

                        except asyncio.TimeoutError:
                            logger.warning(f"⚠️ Tool '{tool_name}' timeout after {TOOL_EXECUTION_TIMEOUT}s")
                            tool_result = f"Lỗi: Tool '{tool_name}' đã timeout sau {TOOL_EXECUTION_TIMEOUT} giây."

                        except Exception as tool_err:
                            logger.error(f"❌ Lỗi khi chạy tool '{tool_name}': {tool_err}")
                            tool_result = f"Lỗi hệ thống khi chạy tool '{tool_name}': {tool_err}"

                        # [MỚI] Thêm info về remaining calls vào tool result
                        tool_result_with_info = f"{tool_result}\n\n[INFO: Còn {remaining_calls} lần gọi tool. Nếu cần thêm tool, hãy gọi ngay.]"

                        # Format tool result message
                        tool_result_msg = self._format_tool_result_message(tool_call_id, tool_name, tool_result_with_info)
                        context_msgs.append(tool_result_msg)

                    # Quay lại đầu vòng lặp để LLM đọc kết quả
                    continue

                else:
                    # KHÔNG CÓ TOOL CALL -> Đây là câu trả lời cuối cùng
                    break

            # KẾT THÚC VÒNG LẶP AGENT

            # 4. Xử lý response và extract token usage
            bot_response: str
            if isinstance(llm_response, LLMResponse):
                bot_response = llm_response.content
                logger.debug(
                    f"📊 Token Usage for user {user_id}: "
                    f"Input={llm_response.input_tokens}, "
                    f"Output={llm_response.output_tokens}, "
                    f"Total={llm_response.total_tokens}"
                )
            else:
                bot_response = llm_response

            # 5. Ghi nhận câu trả lời của Bot vào Bộ nhớ
            # [REASONING MODELS] Skip memory if response is reasoning-only (no final answer)
            is_reasoning_only = isinstance(llm_response, LLMResponse) and llm_response.reasoning_only
            if bot_response and not bot_response.startswith("Error:") and not is_reasoning_only:
                await self.memory.add_message(
                    user_id=user_id, role="assistant", content=bot_response
                )

            return bot_response

        except BashExecutorUnavailableError:
            raise
        except Exception as e:
            logger.error(f"❌ ChatCoordinator: Lỗi nghiêm trọng khi xử lý tin nhắn: {e}")
            return "Xin lỗi, hệ thống não bộ của tôi đang gặp chút trục trặc. Bạn chờ xíu nhé!"

    async def clear_chat_history(self, user_id: str):
        """Xóa bộ nhớ tạm (Tầng 1) của User."""
        await self.memory.clear_session(user_id)