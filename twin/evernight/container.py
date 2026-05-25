"""EvernightContainer - simplified DI container."""
import logging

from dotenv import load_dotenv

from twin.shared.config.settings import Config
from twin.shared.llm.gemini_service import GeminiService
from twin.shared.llm.openai_service import OpenAIService
from twin.shared.llm.openai_embedding_service import OpenAIEmbeddingService
from twin.shared.tools.tool_registry import ToolRegistry
from twin.shared.tools.tool_discovery import discover_and_register_tools
from twin.shared.tools.approval_gate import ApprovalGate
from twin.shared.memories.t2 import T2Memory, T2Store
from twin.shared.external.tavily_client import TavilyClient
from twin.shared.external.codebox_client import CodeBoxClient

from twin.evernight.memories.memory_manager import MemoryManager
from twin.evernight.memories.activate_memory.activate_memory_service import ActiveMemoryService
from twin.evernight.memories.activate_memory.events.event_dispatcher import EventDispatcher
from twin.evernight.memories.activate_memory.management.context_builder import ContextBuilder
from twin.evernight.memories.activate_memory.management.state_repository import SummaryStateRepository
from twin.evernight.memories.activate_memory.management.summary_policy import SummaryPolicy
from twin.evernight.memories.activate_memory.management.token_counter import TokenCounter
from twin.evernight.memories.activate_memory.storage.ram_storage import LocalMemoryDB
from twin.evernight.memories.activate_memory.storage.redis_storage import create_redis_storage
from twin.evernight.memories.activate_memory.storage.redis_stack_storage import RedisStackStorage
from twin.evernight.memories.activate_memory.storage.base_storage import BaseStorage
from twin.evernight.memories.core_memory.core_manager import CoreManager
from twin.evernight.memories.core_memory import MarkdownStorage
from twin.shared.memories.discussion_consolidator import DiscussionConsolidator
from twin.evernight.agent import EvernightAgent
from twin.evernight.config import EvernightConfig

logger = logging.getLogger(__name__)


class EvernightContainer:
    _instance = None

    def __init__(self, config: EvernightConfig):
        self.config = config
        self.llm_service = None
        self.memory_manager = None
        self.agent = None
        self.tool_registry = None
        self.redis_storage = None
        self.redis_client = None

    @classmethod
    def get_instance(cls, config: EvernightConfig = None):
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

    async def initialize(self):
        load_dotenv(override=True)
        logger.info("EvernightContainer initializing...")

        # LLM Service
        provider = getattr(Config, "LLM_PROVIDER", "gemini").lower()
        if provider in {"openai", "openai_compat", "openai-compatible", "openai_compatible"}:
            # OpenAI-compatible covers OpenAI, OpenRouter, LM Studio, Qwen compatible-mode, etc.
            self.llm_service = OpenAIService(persona_path=self.config.persona_path)
        else:
            self.llm_service = GeminiService(persona_path=self.config.persona_path)

        # Embedding Service
        embedding_provider = getattr(Config, "EMBEDDING_PROVIDER", "openai_compat").lower()
        if embedding_provider in {"openai", "openai_compat", "openai-compatible", "openai_compatible", "qwen"}:
            self.embedding_service = OpenAIEmbeddingService(
                model_name=Config.EMBEDDING_MODEL_NAME,
                api_key=Config.EMBEDDING_API_KEY,
                api_url=Config.EMBEDDING_API_URL,
            )
        else:
            raise ValueError(
                f"Unsupported embedding provider: {embedding_provider}. "
                "Local embeddings removed. Use 'openai_compat' (or alias 'qwen')."
            )

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
        episodic_memory = T2Memory(
            store=t2_store,
            embedding_service=self.embedding_service,
        )

        # DiscussionConsolidator wires the SUMMARY_REQUESTED event into T2 fan-out
        consolidator = DiscussionConsolidator(
            llm=self.llm_service,
            t2_memory=episodic_memory,
            event_dispatcher=event_bus,
        )

        # Memory Manager
        self.memory_manager = MemoryManager(
            active_memory=t1_service,
            core_memory=t3_manager,
            event_dispatcher=event_bus,
            state_repo=summary_state_repo,
            consolidator=consolidator,
        )

        self.consolidator = consolidator
        # Expose for downstream wiring (InactivityTrigger, A2A skills)
        self.state_repo = summary_state_repo
        self.summary_policy = summary_policy
        self.event_bus = event_bus

        # Tool Registry
        tavily_client = self._init_tavily_client()
        codebox_client = self._init_codebox_client()
        approval_gate = ApprovalGate()

        tool_registry = ToolRegistry(agent_name="evernight")
        tool_dependencies = {
            "core_manager": t3_manager,
            "memory_manager": episodic_memory,
            "llm_service": self.llm_service,
            "base_memory_path": self.config.persona_path,
            "tavily_client": tavily_client,
            "codebox_client": codebox_client,
            "approval_gate": approval_gate,
            "executor_url": Config.BASH_EXECUTOR_URL,
            "timeout": Config.BASH_EXECUTOR_TIMEOUT,
        }

        discover_and_register_tools(
            tools_dir="twin/shared/tools/implementations/system",
            registry=tool_registry,
            dependencies=tool_dependencies,
        )
        discover_and_register_tools(
            tools_dir="twin/shared/tools/implementations/mcp",
            registry=tool_registry,
            dependencies=tool_dependencies,
        )

        self.llm_service.set_tool_registry(tool_registry)

        # Evernight Agent
        self.agent = EvernightAgent(
            memory_manager=self.memory_manager,
            episodic_memory=episodic_memory,
            llm_service=self.llm_service,
            tool_registry=tool_registry,
            march7_url=self.config.march7_url,
            consolidator=consolidator,
        )

        self.tool_registry = tool_registry
        logger.info("EvernightContainer initialized")

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

                    logger.info("Evernight T1 Redis Stack phase=redis_stack")
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

    def _init_tavily_client(self):
        if not Config.TAVILY_API_KEY:
            return None
        try:
            return TavilyClient()
        except Exception as e:
            logger.warning(f"Tavily init failed: {e}")
            return None

    def _init_codebox_client(self):
        try:
            return CodeBoxClient()
        except Exception as e:
            logger.warning(f"CodeBox init failed: {e}")
            return None
