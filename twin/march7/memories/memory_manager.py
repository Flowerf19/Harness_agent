import asyncio
import logging
from typing import Any, Dict, List, Tuple

from langsmith import traceable

from twin.march7.memories.activate_memory.activate_memory_service import (
    ActiveMemoryService,
)
from twin.march7.memories.activate_memory.events.event_dispatcher import (
    ActiveMemoryEvent,
    EventDispatcher,
)
from twin.march7.memories.core_memory.core_manager import CoreManager

logger = logging.getLogger(__name__)


class MemoryManager:
    def __init__(
        self,
        active_memory: ActiveMemoryService,
        core_memory: CoreManager,
        event_dispatcher: EventDispatcher,
        overflow_queue: Any = None,
        evernight_spawner: Any = None,
    ):
        self.t1 = active_memory
        self.t3 = core_memory
        self.events = event_dispatcher
        self.overflow_queue = overflow_queue
        self.evernight_spawner = evernight_spawner

        # Subscribe: when T1 reaches token limit, just clean up to free space
        self.events.subscribe(
            ActiveMemoryEvent.TOKEN_LIMIT_REACHED, self._handle_memory_overflow
        )

        logger.debug("MemoryManager: initialized (overflow/evernight removed)")

    async def _handle_memory_overflow(self, event_type: str, user_id: str, data: dict):
        await self.t1.force_cleanup(user_id)
        logger.debug(f"MemoryManager: T1 cleaned up for user {user_id}")

    @traceable(
        name="Master_Add_Message", run_type="chain", tags=["memory_manager", "write"]
    )
    async def add_message(self, user_id: str, role: str, content: str) -> None:
        await self.t1.add_message(user_id, role, content)

    @traceable(
        name="Master_Get_Context",
        run_type="chain",
        tags=["memory_manager", "read", "context_assembly"],
    )
    async def get_context(
        self, user_id: str, current_query: str
    ) -> Tuple[str, List[Dict]]:
        async def _run_t3_system_prompt():
            return await self.t3.get_system_prompt_context(user_id)

        async def _run_t1_context():
            return await self.t1.get_context_for_llm(user_id)

        system_prompt, context_messages = await asyncio.gather(
            _run_t3_system_prompt(),
            _run_t1_context()
        )

        return system_prompt, context_messages

    async def clear_session(self, user_id: str):
        await self.t1.reset_session(user_id)
