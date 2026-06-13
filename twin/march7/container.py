"""March7Container - DI container for shared memory runtime."""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

from twin.march7.agent import March7Agent
from twin.march7.config import March7Config
from twin.shared.agent.runtime import SharedAgentRuntime, build_shared_agent_runtime
from twin.shared.tools.registry.bootstrap import build_tool_registry
from twin.shared.memory.consolidation_client import ConsolidationClient

logger = logging.getLogger(__name__)


class March7Container:
    _instance = None

    def __init__(self, config: March7Config):
        self.config = config
        self.runtime: SharedAgentRuntime | None = None
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
        self.profile_store = None
        self.consolidation_client = None

    @classmethod
    def get_instance(cls, config: March7Config = None):
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

    async def initialize(self):
        load_dotenv(override=True)
        logger.info("March7Container initializing...")

        # Create consolidation client for A2A communication with Evernight
        evernight_url = os.getenv("EVERNIGHT_A2A_URL", "http://evernight:8001")
        self.consolidation_client = ConsolidationClient(evernight_url=evernight_url)
        logger.info("ConsolidationClient initialized for %s", evernight_url)

        self.runtime = await build_shared_agent_runtime(
            redis_db=self.config.redis_db,
            persona_path=self.config.persona_path,
            consolidation_client=self.consolidation_client,
        )
        self.llm_service = self.runtime.llm_service
        self.embedding_service = self.runtime.embedding_service
        self.memory_manager = self.runtime.memory_manager
        self.redis_client = self.runtime.redis_client
        self.timeline_redis_client = self.runtime.timeline_redis_client
        self.timeline_store = self.runtime.timeline_store
        self.timeline_search = self.runtime.timeline_search
        self.profile_store = self.runtime.profile_store
        self.profile_store = self.runtime.profile_store

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
        if self.consolidation_client:
            await self.consolidation_client.close()
        if self.runtime:
            await self.runtime.close()
