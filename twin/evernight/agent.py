"""EvernightAgent - consolidation + chat agent."""
import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from langsmith import traceable

from twin.shared.llm.base_llm_service import BaseLLMService
from twin.shared.llm.llm_response import LLMResponse
from twin.shared.tools.registry import ToolRegistry
from twin.shared.a2a.types import AgentCard, A2AMessage, Part, TaskStatus
from twin.shared.memory import SharedMemoryManager

logger = logging.getLogger(__name__)

TOOL_EXECUTION_TIMEOUT = 60

class EvernightAgent:
    def __init__(
        self,
        memory_manager: SharedMemoryManager | None = None,
        episodic_memory: Any = None,
        llm_service: BaseLLMService = None,
        tool_registry: Optional[ToolRegistry] = None,
        use_native_tools: bool = True,
        march7_url: str = "http://march7:8000",
        consolidator: Any = None,
        **kwargs,
    ):
        self.memory = memory_manager
        self.episodic = episodic_memory or self.memory
        self.llm = llm_service or kwargs.pop("llm_client", None)
        self._embedding_service = kwargs.pop("embedding_service", None)
        self.tool_registry = tool_registry
        self.use_native_tools = use_native_tools
        self.march7_url = march7_url
        self.consolidator = consolidator
        self.use_native_tools = use_native_tools
        self.march7_url = march7_url

        self._llm_type = self._detect_llm_type()
        self._model_name = getattr(self.llm, "model", "unknown") if self.llm else "unknown"

        logger.debug(f"EvernightAgent initialized: model={self._model_name}")

    def _detect_llm_type(self) -> str:
        if self.llm is None:
            return "openai"
        class_name = self.llm.__class__.__name__
        if "Gemini" in class_name:
            return "gemini"
        return "openai"

    def get_agent_card(self) -> AgentCard:
        return AgentCard(
            name="Evernight",
            description="Memory consolidation and analysis agent",
            url="http://evernight:8001",
            version="1.0.0",
            capabilities=["chat", "consolidation", "streaming"],
            skills=[
                {"id": "chat", "name": "Chat", "description": "Conversational chat with memory and tools"},
                {"id": "consolidate", "name": "Consolidate", "description": "Consolidate T1 snapshot into T2 timeline"},
                {"id": "consolidate_discussion", "name": "Consolidate Discussion", "description": "Process shared-memory payload into user-centric T2 timeline entries"},
                {"id": "get_snapshot", "name": "Get Snapshot", "description": "Get T1 memory snapshot"},
            ],
        )

    async def get_status(self) -> dict:
        return {"status": "online", "model": self._model_name}

    # ------------------------------------------------------------------
    # Consolidate
    # ------------------------------------------------------------------

    async def consolidate(self, user_id: str, snapshot: List[dict], reason: str = "manual") -> bool:
        logger.info(f"Evernight: Consolidating snapshot for user {user_id}")
        try:
            if not self.consolidator or not hasattr(self.consolidator, "consolidate_snapshot"):
                logger.error("Evernight: Missing shared consolidator")
                return False
            return await self.consolidator.consolidate_snapshot(user_id, snapshot, reason)
        except Exception as e:
            logger.error(f"Evernight: Consolidation failed: {e}", exc_info=True)
            return False

    def _format_snapshot(self, snapshot: List[dict]) -> str:
        lines = []
        for msg in snapshot:
            role = msg.get("role", "unknown") if isinstance(msg, dict) else getattr(msg, "role", "unknown")
            content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            lines.append(f"[{role.upper()}]: {content}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Chat (new capability for Evernight)
    # ------------------------------------------------------------------

    @traceable(name="Evernight_Chat", run_type="chain", tags=["evernight", "chat"])
    async def handle_chat(self, user_id: str, content: str) -> str:
        try:
            await self.memory.add_message(user_id=user_id, role="user", content=content)

            sys_prompt, context_msgs = await self.memory.get_context(
                user_id=user_id, current_query=content
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
                    logger.debug(
                        f"Evernight wants {len(tool_calls)} tools (iteration {i+1}/{max_iterations})"
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
                        except asyncio.TimeoutError:
                            tool_result = f"Lỗi: Tool '{tool_name}' timeout."
                        except Exception as tool_err:
                            tool_result = f"Lỗi: {tool_err}"

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
            else:
                bot_response = llm_response

            is_reasoning_only = isinstance(llm_response, LLMResponse) and llm_response.reasoning_only
            if bot_response and not bot_response.startswith("Error:") and not is_reasoning_only:
                await self.memory.add_message(
                    user_id=user_id, role="assistant", content=bot_response
                )

            return bot_response

        except Exception as e:
            logger.error(f"EvernightAgent chat error: {e}")
            return "Xin lỗi, tôi đang gặp chút trục trặc với hệ thống ký ức."

    async def clear_chat_history(self, user_id: str):
        await self.memory.clear_session(user_id)

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
