import asyncio
import logging
from typing import Any, Dict, List, Tuple

from langsmith import traceable

from twin.evernight.memories.activate_memory.activate_memory_service import (
    ActiveMemoryService,
)
from twin.evernight.memories.activate_memory.events.event_dispatcher import (
    ActiveMemoryEvent,
    EventDispatcher,
)
from twin.evernight.memories.activate_memory.management.state_repository import (
    SummaryStateRepository,
)
from twin.evernight.memories.activate_memory.constants import (
    KEEP_RECENT_MESSAGES_AFTER_SUMMARY,
)
from twin.evernight.memories.core_memory.core_manager import CoreManager

logger = logging.getLogger(__name__)


class MemoryManager:
    """Evernight memory manager — owns DM/!9 conversation context.

    Channel observe stays at March7 (Gap #1). Evernight only needs the
    user-scope summary flow: SUMMARY_REQUESTED -> consolidate -> COMPLETED -> cleanup.
    """

    def __init__(
        self,
        active_memory: ActiveMemoryService,
        core_memory: CoreManager,
        event_dispatcher: EventDispatcher,
        state_repo: SummaryStateRepository | None = None,
        consolidator: Any = None,
    ):
        self.t1 = active_memory
        self.t3 = core_memory
        self.events = event_dispatcher
        self.state_repo = state_repo
        self.consolidator = consolidator

        self.events.subscribe(
            ActiveMemoryEvent.SUMMARY_REQUESTED, self._handle_summary_requested
        )
        self.events.subscribe(
            ActiveMemoryEvent.SUMMARY_COMPLETED, self._handle_summary_completed
        )
        self.events.subscribe(
            ActiveMemoryEvent.SUMMARY_FAILED, self._handle_summary_failed
        )

        logger.debug("Evernight MemoryManager: initialized")

    async def _handle_summary_requested(
        self, event_type: str, scope_id: str, data: dict
    ) -> None:
        if self.consolidator is None:
            logger.warning(
                "Evernight MemoryManager: no consolidator configured; preserving T1 scope=%s scope_id=%s",
                data.get("scope"),
                data.get("scope_id", scope_id),
            )
            return

        result = await self.consolidator.consolidate(data)
        status = result.get("status")
        if status in ("ok", "skipped"):
            self.events.emit(
                ActiveMemoryEvent.SUMMARY_COMPLETED,
                data.get("scope_id", scope_id),
                data=result,
            )
        else:
            self.events.emit(
                ActiveMemoryEvent.SUMMARY_FAILED,
                data.get("scope_id", scope_id),
                data=result,
            )

    async def _handle_summary_completed(
        self, event_type: str, scope_id: str, data: dict
    ) -> None:
        await self.t1.cleanup_summarized(
            scope=data["scope"],
            scope_id=data["scope_id"],
            summarized_entry_ids=data.get("summarized_entry_ids", []),
            keep_recent=KEEP_RECENT_MESSAGES_AFTER_SUMMARY,
        )
        if self.state_repo is not None:
            await self.state_repo.mark_completed(data)

    async def _handle_summary_failed(
        self, event_type: str, scope_id: str, data: dict
    ) -> None:
        if self.state_repo is not None:
            await self.state_repo.mark_failed(data)

    @traceable(
        name="Master_Add_Message", run_type="chain", tags=["memory_manager", "write"]
    )
    async def add_message(self, user_id: str, role: str, content: str) -> None:
        await self.t1.observe_user_message(user_id, role, content)

    async def observe_user_message(
        self, user_id: str, role: str, content: str
    ) -> None:
        await self.t1.observe_user_message(user_id, role, content)

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
