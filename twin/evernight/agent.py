"""EvernightAgent - consolidation + chat agent."""
import logging
from typing import Any, Dict, List, Optional

from langsmith import traceable

from twin.shared.llm.base_llm_service import BaseLLMService, LLM_ERROR_RESPONSES
from twin.shared.llm.llm_response import LLMResponse
from twin.shared.llm.tool_loop import run_strict_tool_loop
from twin.shared.tools.registry import ToolRegistry
from twin.shared.a2a.types import AgentCard, A2AMessage, Part, TaskStatus
from twin.shared.memory import SharedMemoryManager

logger = logging.getLogger(__name__)

TOOL_EXECUTION_TIMEOUT = 60

# Shown to the user when the LLM endpoint fails — keeps the raw
# "Error generating response." sentinel from leaking into the chat.
LLM_FAILURE_REPLY = "Xin lỗi, tôi đang gặp chút trục trặc với hệ thống ký ức."

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

            llm_response = await run_strict_tool_loop(
                llm=self.llm,
                tool_registry=self.tool_registry,
                tool_prompt_catalog=getattr(self.llm, "tool_prompt_catalog", None),
                messages=context_msgs,
                system_prompt=sys_prompt,
                use_native_tools=self.use_native_tools,
                llm_type=self._llm_type,
                logger=logger,
                max_iterations=10,
                tool_timeout=TOOL_EXECUTION_TIMEOUT,
            )

            bot_response: str
            if isinstance(llm_response, LLMResponse):
                bot_response = llm_response.content
            else:
                bot_response = llm_response

            # LLM hard-failure sentinel: never relay it to the user or persist it
            # to memory — surface a friendly retry message instead.
            if isinstance(bot_response, str) and bot_response in LLM_ERROR_RESPONSES:
                logger.error(
                    "LLM returned error sentinel for user=%s: %s", user_id, bot_response
                )
                return LLM_FAILURE_REPLY

            is_reasoning_only = isinstance(llm_response, LLMResponse) and llm_response.reasoning_only
            if bot_response and not bot_response.startswith("Error:") and not is_reasoning_only:
                await self.memory.add_message(
                    user_id=user_id, role="assistant", content=bot_response
                )

            return bot_response

        except Exception as e:
            logger.error(f"EvernightAgent chat error: {e}")
            return LLM_FAILURE_REPLY

    async def clear_chat_history(self, user_id: str):
        await self.memory.clear_session(user_id)
