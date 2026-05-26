"""March7Container - simplified DI container."""
import logging

from dotenv import load_dotenv

from twin.shared.config.settings import Config
from twin.shared.llm.gemini_service import GeminiService
from twin.shared.llm.openai_service import OpenAIService
from twin.shared.tools.registry.bootstrap import build_tool_registry
from twin.shared.memories.t2 import T2Memory, T2Store
from twin.shared.llm.embedding import create_embedding_service

from twin.march7.memories.memory_manager import MemoryManager
from twin.march7.memories.activate_memory.activate_memory_service import ActiveMemoryService
from twin.march7.memories.activate_memory.events.event_dispatcher import EventDispatcher
from twin.march7.memories.activate_memory.management.context_builder import ContextBuilder
from twin.march7.memories.activate_memory.management.state_repository import SummaryStateRepository
from twin.march7.memories.activate_memory.management.summary_policy import SummaryPolicy
from twin.march7.memories.activate_memory.management.token_counter import TokenCounter
from twin.march7.memories.activate_memory.storage.ram_storage import LocalMemoryDB
from twin.march7.memories.activate_memory.storage.redis_storage import create_redis_storage
from twin.march7.memories.activate_memory.storage.redis_stack_storage import RedisStackStorage
from twin.march7.memories.activate_memory.storage.base_storage import BaseStorage
from twin.march7.memories.core_memory.core_manager import CoreManager
from twin.march7.memories.core_memory import MarkdownStorage
from twin.march7.agent import March7Agent
from twin.march7.config import March7Config

logger = logging.getLogger(__name__)


class March7Container:
    _instance = None

    def __init__(self, config: March7Config):
        self.config = config
        self.llm_service = None
        self.memory_manager = None
        self.agent = None
        self.tool_registry = None
        self.redis_storage = None
        self.redis_client = None

    @classmethod
    def get_instance(cls, config: March7Config = None):
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

    async def initialize(self):
        load_dotenv(override=True)
        logger.info("March7Container initializing...")

        # LLM Service
        provider = getattr(Config, "LLM_PROVIDER", "gemini").lower()
        if provider in {"openai", "openai_compat", "openai-compatible", "openai_compatible"}:
            # OpenAI-compatible covers OpenAI, OpenRouter, LM Studio, Qwen compatible-mode, etc.
            self.llm_service = OpenAIService(persona_path=self.config.persona_path)
        else:
            self.llm_service = GeminiService(persona_path=self.config.persona_path)

        # Embedding Service
        self.embedding_service = create_embedding_service()

        # T1 Active Memory
        event_bus = EventDispatcher()
        t1_storage = await self._get_t1_storage()

        t1_token_counter = TokenCounter()
        t1_context_builder = ContextBuilder()
        summary_state_repo = SummaryStateRepository(self.redis_client)
        summary_policy = SummaryPolicy(t1_storage, summary_state_repo, event_bus)

        t1_service = ActiveMemoryService(
            storage=t1_storage,
            token_counter=t1_token_counter,
            context_builder=t1_context_builder,
            event_dispatcher=event_bus,
            summary_policy=summary_policy,
        )

        # T3 Core Memory
        t3_storage = MarkdownStorage()
        # SmartUpdater removed - agent handles merge
        t3_manager = CoreManager(storage=t3_storage)

        # T2 semantic memory (Redis Stack, shared)
        t2_store = await self._get_t2_store()
        t2_memory = T2Memory(
            store=t2_store,
            embedding_service=self.embedding_service,
        )
        # Evernight client for the SUMMARY_REQUESTED -> consolidate_discussion A2A hop
        evernight_a2a_url = getattr(Config, "EVERNIGHT_A2A_URL", None)
        evernight_client = None
        if evernight_a2a_url:
            try:
                from gateway.adapters.discord.evernight_client import EvernightClient
                evernight_client = EvernightClient(base_url=evernight_a2a_url)
                logger.info("Evernight A2A client configured: %s", evernight_a2a_url)
            except Exception as e:
                logger.warning("Evernight A2A client init failed: %s", e)

        # Memory Manager
        self.memory_manager = MemoryManager(
            active_memory=t1_service,
            core_memory=t3_manager,
            event_dispatcher=event_bus,
            state_repo=summary_state_repo,
            evernight_client=evernight_client,
        )

        # Expose for downstream wiring (InactivityTrigger, tests, A2A skills)
        self.state_repo = summary_state_repo
        self.summary_policy = summary_policy
        self.event_bus = event_bus

        # Tool Registry
        tools = build_tool_registry(
            agent_name="march7",
            core_manager=t3_manager,
            memory_manager=t2_memory,
            llm_service=self.llm_service,
            base_memory_path=self.config.persona_path,
            use_evernight_dm_approval=True,
        )
        tool_registry = tools.registry

        self.llm_service.set_tool_registry(tool_registry)

        # March7 Agent
        self.agent = March7Agent(
            memory_manager=self.memory_manager,
            llm_service=self.llm_service,
            tool_registry=tool_registry,
            redis_client=self.redis_client,
        )

        self.tool_registry = tool_registry
        logger.info("March7Container initialized")

    async def shutdown(self):
        if self.llm_service:
            await self.llm_service.close()
        if self.redis_storage:
            await self.redis_storage.close()

    async def _get_t1_storage(self) -> BaseStorage:
        redis_enabled = getattr(Config, "REDIS_ENABLED", False)
        if not redis_enabled:
            return LocalMemoryDB()

        try:
            storage = create_redis_storage(
                redis_url=Config.REDIS_URL,
                redis_password=Config.REDIS_PASSWORD,
                redis_db=self.config.redis_db,
            )
            if await storage.health_check():
                self.redis_storage = storage
                self.redis_client = storage.redis
                phase = getattr(Config, "T1_STORAGE_PHASE", "legacy")
                if phase == "redis_stack":
                    stack_storage = RedisStackStorage(self.redis_client)
                    try:
                        await stack_storage.initialize()
                    except Exception as e:
                        logger.warning("T1 Redis Stack init failed, fallback legacy: %s", e)
                        return storage

                    logger.info("T1 Redis Stack phase=redis_stack (read=redis_stack, write=redis_stack)")
                    return stack_storage
                return storage
            else:
                await storage.close()
                return LocalMemoryDB()
        except Exception as e:
            logger.warning(f"Redis connection failed, using RAM: {e}")
            return LocalMemoryDB()

    async def _get_t2_store(self):
        try:
            storage = T2Store(redis_client=self.redis_client)
            await storage.initialize()
            return storage
        except Exception as e:
            raise RuntimeError(f"T2 storage init failed: {e}")
