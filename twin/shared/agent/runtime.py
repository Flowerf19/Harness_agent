"""Shared runtime construction for Twin chat agents.

This module builds infrastructure that March7 and Evernight both use. Agent
identity and behavior stay in each container; this only owns LLM, memory,
Redis, timeline, cleanup, and summary plumbing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import redis.asyncio as aioredis

from twin.shared.config.settings import Config
from twin.shared.llm.embedding import create_embedding_service
from twin.shared.llm.gemini_service import GeminiService
from twin.shared.llm.openai_service import OpenAIService
from twin.shared.memory import SharedMemoryManager
from twin.shared.memory.active import (
    ActiveMemory,
    ActiveStore,
    ActiveSummaryPolicy,
    ActiveSummaryStateRepository,
    FastPathDetector,
)
from twin.shared.memory.profile import (
    MarkdownProfileStore,
    ProfileCurator,
)
from twin.shared.memory.profile.promotion_guard import ProfilePromotionGuard
from twin.shared.memory.profile.constants import PROFILE_CURATION_IDLE_SECONDS
from twin.shared.memory.timeline import (
    Cleanup,
    Consolidator,
    Extractor,
    TimelineSearch,
    TimelineStore,
    TopicResolver,
)
from twin.shared.memory.timeline.constants import CLEANUP_DEBOUNCE_SECONDS
from twin.shared.memory.scheduler import DebouncedScheduler


@dataclass(slots=True)
class SharedAgentRuntime:
    llm_service: Any
    embedding_service: Any
    memory_manager: SharedMemoryManager
    redis_client: Any
    timeline_redis_client: Any
    timeline_store: TimelineStore
    timeline_search: TimelineSearch
    profile_store: MarkdownProfileStore
    cleanup_scheduler: DebouncedScheduler
    curation_scheduler: DebouncedScheduler
    state_repo: ActiveSummaryStateRepository
    summary_policy: ActiveSummaryPolicy

    async def close(self) -> None:
        if self.cleanup_scheduler:
            await self.cleanup_scheduler.close()
        if self.curation_scheduler:
            await self.curation_scheduler.close()
        if self.llm_service:
            await self.llm_service.close()
        if self.redis_client:
            await self.redis_client.aclose()
        if self.timeline_redis_client and self.timeline_redis_client is not self.redis_client:
            await self.timeline_redis_client.aclose()


async def build_shared_agent_runtime(*, redis_db: int, persona_path: str) -> SharedAgentRuntime:
    llm_service = build_llm_service(persona_path=persona_path)
    embedding_service = create_embedding_service()

    redis_client = await connect_redis(redis_db)
    timeline_db = getattr(Config, "TIMELINE_REDIS_DB", 0)
    timeline_redis_client = await connect_redis(timeline_db)

    active = ActiveMemory(
        store=ActiveStore(redis_client),
        detector=FastPathDetector(),
    )

    profile_store = MarkdownProfileStore()

    timeline_store = TimelineStore(timeline_redis_client)
    await timeline_store.initialize()
    resolver = TopicResolver(timeline_store)
    extractor = Extractor(llm_service)
    cleanup = Cleanup(
        store=timeline_store,
        embedder=embedding_service,
        llm=llm_service,
    )
    cleanup_scheduler = DebouncedScheduler(
        cleanup.run,
        debounce_seconds=CLEANUP_DEBOUNCE_SECONDS,
    )

    promotion_guard = ProfilePromotionGuard(
        timeline_store=timeline_store,
        profile_store=profile_store,
        llm_service=llm_service,
    )

    consolidator = Consolidator(
        active=active,
        store=timeline_store,
        resolver=resolver,
        extractor=extractor,
        embedder=embedding_service,
        promotion_guard=promotion_guard,
        cleanup_scheduler=cleanup_scheduler.schedule,
    )
    timeline_search = TimelineSearch(
        store=timeline_store,
        embedder=embedding_service,
    )

    curator = ProfileCurator(profile_store, llm_service)
    curation_scheduler = DebouncedScheduler(
        curator.curate,
        debounce_seconds=PROFILE_CURATION_IDLE_SECONDS,
    )

    memory_manager = SharedMemoryManager(
        active=active,
        profile_store=profile_store,
        timeline_search=timeline_search,
        consolidator=consolidator,
        curation_scheduler=curation_scheduler.schedule,
    )
    active.trigger_callback = memory_manager.consolidate_scope

    state_repo = ActiveSummaryStateRepository(active)
    summary_policy = ActiveSummaryPolicy(
        active,
        memory_manager.consolidate_scope,
    )

    return SharedAgentRuntime(
        llm_service=llm_service,
        embedding_service=embedding_service,
        memory_manager=memory_manager,
        redis_client=redis_client,
        timeline_redis_client=timeline_redis_client,
        timeline_store=timeline_store,
        timeline_search=timeline_search,
        profile_store=profile_store,
        cleanup_scheduler=cleanup_scheduler,
        curation_scheduler=curation_scheduler,
        state_repo=state_repo,
        summary_policy=summary_policy,
    )


def build_llm_service(*, persona_path: str) -> Any:
    provider = getattr(Config, "LLM_PROVIDER", "gemini").lower()
    if provider in {"openai", "openai_compat", "openai-compatible", "openai_compatible"}:
        return OpenAIService(persona_path=persona_path)
    return GeminiService(persona_path=persona_path)


async def connect_redis(db: int) -> Any:
    if not getattr(Config, "REDIS_ENABLED", False):
        raise RuntimeError("REDIS_ENABLED=false; shared memory runtime requires Redis Stack")
    client = aioredis.from_url(
        Config.REDIS_URL,
        db=db,
        password=Config.REDIS_PASSWORD,
        decode_responses=False,
    )
    await client.ping()
    return client
