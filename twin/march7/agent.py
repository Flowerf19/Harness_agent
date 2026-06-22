"""March7Agent - conversational agent evolved from ChatCoordinator."""
import logging
from typing import Any, List, Optional

from twin.shared.agent import ChatTurnRunner
from twin.shared.llm.base_llm_service import BaseLLMService
from twin.shared.observability import langsmith_extra
from twin.shared.observability.langsmith import traceable
from twin.shared.tools.registry import ToolRegistry
from twin.shared.tools.exceptions import BashExecutorUnavailableError
from twin.shared.a2a.types import AgentCard
from twin.shared.memory import SharedMemoryManager

logger = logging.getLogger(__name__)

TOOL_EXECUTION_TIMEOUT = 60

# Shown to the user when the LLM endpoint fails (reset/timeout/non-200). Keeps
# the raw "Error generating response." sentinel from leaking into the chat.
LLM_FAILURE_REPLY = "Xin lỗi, hệ thống não bộ của tôi đang gặp chút trục trặc. Bạn chờ xíu nhé!"

# Sentinel the model emits to stay silent in a group channel when not addressed.
SILENCE_SENTINEL = "[skip]"
SILENCE_NOTE = (
    "=== NGỮ CẢNH KÊNH ===\n"
    "Tin nhắn này ở kênh chung và KHÔNG nhắc tới bạn. Bạn không bắt buộc phải trả lời. "
    "Nếu không có gì đáng nói, hãy im lặng bằng cách trả lời đúng một dòng `[skip]` và không gì khác."
)


class March7Agent:
    def __init__(
        self,
        memory_manager: SharedMemoryManager,
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

        self._chat_turn = ChatTurnRunner(
            llm=self.llm,
            tool_registry=self.tool_registry,
            use_native_tools=self.use_native_tools,
            logger=logger,
        )
        self._llm_type = self._chat_turn.llm_type
        self._model_name = getattr(self.llm, "model", "unknown")

        logger.debug(
            f"March7Agent initialized: use_native_tools={self.use_native_tools}, "
            f"llm_type={self._llm_type}, model={self._model_name}"
        )

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

    @traceable(name="march7.chat", run_type="chain", tags=["march7"])
    async def handle_chat(
        self,
        user_id: str,
        content: str,
        channel_id: str | None = None,
        observe_input: bool = True,
        guild_id: str | None = None,
        bot_id: str | None = None,
        bot_name: str | None = None,
        allow_silence: bool = False,
        user_name: str | None = None,
        mentioned_users: list[dict[str, Any]] | None = None,
    ) -> str:
        try:
            if observe_input:
                await self.memory.add_message(user_id=user_id, role="user", content=content)
            await self._set_active_marker(user_id)

            sys_prompt, context_msgs = await self.memory.get_context(
                user_id=user_id,
                current_query=content,
                channel_id=channel_id,
                user_name=user_name,
                mentioned_users=mentioned_users,
            )
            if allow_silence:
                sys_prompt = f"{sys_prompt}\n\n{SILENCE_NOTE}"

            turn = await self._chat_turn.run(
                messages=context_msgs,
                system_prompt=sys_prompt,
                max_iterations=10,
                tool_timeout=TOOL_EXECUTION_TIMEOUT,
                raise_bash_unavailable=True,
                trace_metadata={
                    "workflow": "march7.chat",
                    "agent_name": "march7",
                    "provider": self._llm_type,
                    "model": self._model_name,
                    "user_id": user_id,
                    "channel_id": channel_id,
                    "guild_id": guild_id,
                    "allow_silence": allow_silence,
                },
                langsmith_extra=langsmith_extra(
                    tags=[self._llm_type],
                    metadata={
                        "workflow": "march7.chat",
                        "agent_name": "march7",
                        "provider": self._llm_type,
                        "model": self._model_name,
                        "user_id": user_id,
                        "channel_id": channel_id,
                        "guild_id": guild_id,
                        "allow_silence": allow_silence,
                    },
                ),
            )

            bot_response = turn.content
            if turn.is_structured:
                logger.debug(
                    f"Token Usage for user {user_id}: "
                    f"Input={turn.input_tokens}, Output={turn.output_tokens}"
                )

            # LLM hard-failure sentinel: never relay it to the user or persist it
            # to memory — surface a friendly retry message instead.
            if turn.is_failure:
                logger.error("LLM returned error sentinel for user=%s: %s", user_id, bot_response)
                return LLM_FAILURE_REPLY

            if allow_silence and self._is_silence(bot_response):
                logger.info("March7 chose to stay silent (channel=%s, user=%s)", channel_id, user_id)
                return ""

            if bot_response and not bot_response.startswith("Error:") and not turn.reasoning_only:
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
            return LLM_FAILURE_REPLY

    @staticmethod
    def _is_silence(text: str | None) -> bool:
        """True when the model emitted the silence sentinel (tolerant of wrapping)."""
        if not text:
            return False
        cleaned = text.strip().strip("`'\" .").lower()
        return cleaned in {SILENCE_SENTINEL, "skip"}

    async def handle_get_snapshot(self, user_id: str) -> List[dict]:
        try:
            return await self.memory.get_snapshot(user_id)
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
