"""March7Container - DI container for shared memory runtime."""
from __future__ import annotations

import logging

import redis.asyncio as aioredis
from dotenv import load_dotenv

from twin.march7.agent import March7Agent
from twin.march7.config import March7Config
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
from twin.shared.memory.profile import MarkdownProfileStore
from twin.shared.memory.timeline import (
    Cleanup,
    CleanupScheduler,
    Consolidator,
    Extractor,
    TimelineSearch,
    TimelineStore,
    TopicResolver,
)
from twin.shared.tools.registry.bootstrap import build_tool_registry

logger = logging.getLogger(__name__)


class March7Container:
    _instance = None

    def __init__(self, config: March7Config):
        self.config = config
        self.llm_service = None
        self.embedding_service = None
        self.memory_manager = None
        self.agent = None
        self.tool_registry = None
        self.redis_client = None
        self.timeline_redis_client = None
        self.timeline_store = None
        self.timeline_search = None
        self.profile_store = None
        self.cleanup_scheduler = None
        self.state_repo = None
        self.summary_policy = None

    @classmethod
    def get_instance(cls, config: March7Config = None):
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

    async def initialize(self):
        load_dotenv(override=True)
        logger.info("March7Container initializing...")

        self.llm_service = self._build_llm_service()
        self.embedding_service = create_embedding_service()

        self.redis_client = await self._connect_redis(self.config.redis_db)
        timeline_db = getattr(Config, "TIMELINE_REDIS_DB", 0)
        self.timeline_redis_client = await self._connect_redis(timeline_db)

        active = ActiveMemory(
            store=ActiveStore(self.redis_client),
            detector=FastPathDetector(),
        )

        self.profile_store = MarkdownProfileStore()

        self.timeline_store = TimelineStore(self.timeline_redis_client)
        await self.timeline_store.initialize()
        resolver = TopicResolver(self.timeline_store, self.embedding_service, self.llm_service)
        extractor = Extractor(self.llm_service)
        cleanup = Cleanup(
            store=self.timeline_store,
            embedder=self.embedding_service,
            llm=self.llm_service,
            profile_reader=self.profile_store.read_raw,
            profile_writer=self.profile_store.write_raw,
        )
        self.cleanup_scheduler = CleanupScheduler(cleanup.run)
        consolidator = Consolidator(
            active=active,
            store=self.timeline_store,
            resolver=resolver,
            extractor=extractor,
            embedder=self.embedding_service,
            profile_reader=self.profile_store.read_raw,
            profile_appender=self.profile_store.append_raw,
            cleanup_scheduler=self.cleanup_scheduler.schedule,
        )
        self.timeline_search = TimelineSearch(
            store=self.timeline_store,
            embedder=self.embedding_service,
        )

        self.memory_manager = SharedMemoryManager(
            active=active,
            profile_store=self.profile_store,
            timeline_search=self.timeline_search,
            consolidator=consolidator,
        )
        active.trigger_callback = self.memory_manager.consolidate_scope

        self.state_repo = ActiveSummaryStateRepository(active)
        self.summary_policy = ActiveSummaryPolicy(
            active,
            self.memory_manager.consolidate_scope,
        )

        tools = build_tool_registry(
            agent_name="march7",
            core_manager=None,
            memory_manager=self.memory_manager,
            timeline_search=self.timeline_search,
            profile_store=self.profile_store,
            llm_service=self.llm_service,
            base_memory_path=self.config.persona_path,
            use_evernight_dm_approval=True,
        )
        self.tool_registry = tools.registry
        self.llm_service.set_tool_registry(self.tool_registry)
        self.llm_service.set_tool_prompt_catalog(tools.tool_prompt_catalog)

        self.agent = March7Agent(
            memory_manager=self.memory_manager,
            llm_service=self.llm_service,
            tool_registry=self.tool_registry,
            redis_client=self.redis_client,
        )

        logger.info("March7Container initialized")

    async def shutdown(self):
        if self.cleanup_scheduler:
            await self.cleanup_scheduler.close()
        if self.llm_service:
            await self.llm_service.close()
        if self.redis_client:
            await self.redis_client.aclose()
        if self.timeline_redis_client and self.timeline_redis_client is not self.redis_client:
            await self.timeline_redis_client.aclose()

    def _build_llm_service(self):
        provider = getattr(Config, "LLM_PROVIDER", "gemini").lower()
        if provider in {"openai", "openai_compat", "openai-compatible", "openai_compatible"}:
            return OpenAIService(persona_path=self.config.persona_path)
        return GeminiService(persona_path=self.config.persona_path)

    async def _connect_redis(self, db: int):
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
