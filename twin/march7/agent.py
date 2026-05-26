"""March7Agent - conversational agent evolved from ChatCoordinator."""
import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from langsmith import traceable

from twin.shared.llm.base_llm_service import BaseLLMService
from twin.shared.llm.llm_response import LLMResponse
from twin.shared.tools.registry import ToolRegistry
from twin.shared.tools.exceptions import BashExecutorUnavailableError
from twin.shared.a2a.types import AgentCard, A2AMessage, Part, TaskStatus
from twin.march7.memories.memory_manager import MemoryManager

logger = logging.getLogger(__name__)

TOOL_EXECUTION_TIMEOUT = 60


class March7Agent:
    def __init__(
        self,
        memory_manager: MemoryManager,
        llm_service: BaseLLMService,
        tool_registry: Optional[ToolRegistry] = None,
        use_native_tools: bool = True,
        redis_client: Any = None,
    ):
        self.memory = memory_manager
        self.llm = llm_service
        self.tool_registry = tool_registry
        self.use_native_tools = use_native_tools
        self.redis = redis_client

        self._llm_type = self._detect_llm_type()
        self._model_name = getattr(self.llm, "model", "unknown")

        logger.debug(
            f"March7Agent initialized: use_native_tools={self.use_native_tools}, "
            f"llm_type={self._llm_type}, model={self._model_name}"
        )

    def _detect_llm_type(self) -> str:
        class_name = self.llm.__class__.__name__
        if "Gemini" in class_name:
            return "gemini"
        return "openai"

    def get_agent_card(self) -> AgentCard:
        return AgentCard(
            name="March7",
            description="Conversational AI agent - friendly and helpful companion",
            url="http://march7:8000",
            version="1.0.0",
            capabilities=["chat", "streaming"],
            skills=[
                {"id": "chat", "name": "Chat", "description": "Conversational chat with memory and tools"},
                {"id": "get_snapshot", "name": "Get Snapshot", "description": "Get T1 memory snapshot"},
                {"id": "clear_session", "name": "Clear Session", "description": "Clear T1 memory after successful consolidation"},
            ],
        )

    async def get_status(self) -> dict:
        return {"status": "online", "model": self._model_name}

    async def _set_active_marker(self, user_id: str):
        if self.redis:
            import time
            await self.redis.set(
                f"conversation:{user_id}:last_active",
                str(time.time()),
                ex=7200,
            )
            await self.redis.setex(
                f"agent:march7:heartbeat",
                30,
                "1",
            )

    @traceable(name="March7_Chat", run_type="chain", tags=["march7", "chat"])
    async def handle_chat(
        self,
        user_id: str,
        content: str,
        channel_id: str | None = None,
        observe_input: bool = True,
        guild_id: str | None = None,
        bot_id: str | None = None,
        bot_name: str | None = None,
    ) -> str:
        try:
            if observe_input:
                await self.memory.add_message(user_id=user_id, role="user", content=content)
            await self._set_active_marker(user_id)

            sys_prompt, context_msgs = await self.memory.get_context(
                user_id=user_id, current_query=content, channel_id=channel_id
            )

            max_iterations = 10
            llm_response = None
            for i in range(max_iterations):
                llm_response = await self.llm.generate_response(
                    messages=context_msgs,
                    system_prompt=sys_prompt,
                    use_native_tools=self.use_native_tools,
                )

                if isinstance(llm_response, LLMResponse) and llm_response.has_tool_calls():
                    tool_calls = llm_response.tool_calls
                    logger.info(
                        f"🔧 March7 wants {len(tool_calls)} tools: "
                        f"{[tc['name'] for tc in tool_calls]} (iteration {i+1}/{max_iterations})"
                    )

                    tool_call_msg = self._format_tool_call_message(tool_calls)
                    context_msgs.append(tool_call_msg)

                    for tc in tool_calls:
                        tool_name = tc["name"]
                        tool_args = tc["arguments"]
                        tool_call_id = tc.get("id", str(uuid.uuid4()))

                        try:
                            tool_result = await asyncio.wait_for(
                                self.tool_registry.execute_tool(tool_name, tool_args),
                                timeout=TOOL_EXECUTION_TIMEOUT,
                            )
                            logger.info(f"✅ Tool '{tool_name}' executed successfully")
                        except BashExecutorUnavailableError:
                            raise
                        except asyncio.TimeoutError:
                            tool_result = f"Lỗi: Tool '{tool_name}' timeout."
                            logger.warning(f"⏱️ Tool '{tool_name}' timed out")
                        except Exception as tool_err:
                            tool_result = f"Lỗi: {tool_err}"
                            logger.error(f"❌ Tool '{tool_name}' failed: {tool_err}")

                        tool_result_msg = self._format_tool_result_message(
                            tool_call_id, tool_name, tool_result
                        )
                        context_msgs.append(tool_result_msg)
                    continue
                else:
                    break

            bot_response: str
            if isinstance(llm_response, LLMResponse):
                bot_response = llm_response.content
                logger.debug(
                    f"Token Usage for user {user_id}: "
                    f"Input={llm_response.input_tokens}, Output={llm_response.output_tokens}"
                )
            else:
                bot_response = llm_response

            is_reasoning_only = isinstance(llm_response, LLMResponse) and llm_response.reasoning_only
            if bot_response and not bot_response.startswith("Error:") and not is_reasoning_only:
                await self.memory.add_assistant_message(
                    user_id=user_id,
                    content=bot_response,
                    channel_id=channel_id,
                    guild_id=guild_id,
                    bot_id=bot_id,
                    bot_name=bot_name,
                )

            return bot_response

        except BashExecutorUnavailableError:
            raise
        except Exception as e:
            logger.error(f"March7Agent error: {e}")
            return "Xin lỗi, hệ thống não bộ của tôi đang gặp chút trục trặc. Bạn chờ xíu nhé!"

    async def handle_get_snapshot(self, user_id: str) -> List[dict]:
        try:
            ctx = await self.memory.t1.get_context_for_llm(user_id)
            return ctx
        except Exception as e:
            logger.error(f"Failed to get snapshot for {user_id}: {e}")
            return []

    async def clear_chat_history(self, user_id: str):
        await self.memory.clear_session(user_id)

    async def handle_clear_session(self, user_id: str) -> bool:
        try:
            await self.memory.clear_session(user_id)
            return True
        except Exception as e:
            logger.error(f"Failed to clear session for {user_id}: {e}")
            return False

    def _format_tool_call_message(self, tool_calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        if self._llm_type == "gemini":
            parts = []
            for tc in tool_calls:
                parts.append({
                    "functionCall": {"name": tc["name"], "args": tc["arguments"]}
                })
            return {"role": "model", "parts": parts}
        else:
            formatted = []
            for tc in tool_calls:
                formatted.append({
                    "id": tc.get("id", str(uuid.uuid4())),
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"]),
                    },
                })
            return {"role": "assistant", "content": "", "tool_calls": formatted}

    def _format_tool_result_message(
        self, tool_call_id: str, tool_name: str, result: str
    ) -> Dict[str, Any]:
        if self._llm_type == "gemini":
            return {
                "role": "user",
                "parts": [{
                    "functionResponse": {
                        "name": tool_name,
                        "response": {"result": result},
                    }
                }],
            }
        else:
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": result,
            }
