"""March7Container - simplified DI container."""
import logging

from dotenv import load_dotenv

from twin.shared.config.settings import Config
from twin.shared.llm.gemini_service import GeminiService
from twin.shared.llm.lm_studio_service import LMStudioService
from twin.shared.llm.openai_service import OpenAIService
from twin.shared.llm.qwen_service import QwenService
from twin.shared.tools.tool_registry import ToolRegistry
from twin.shared.tools.tool_discovery import discover_and_register_tools
from twin.shared.tools.approval_gate import ApprovalGate
from twin.shared.tools.dm_client import DMClient
from twin.shared.memories.episodic_memory_manager import EpisodicMemoryManager
from twin.shared.llm.remote_embedding_service import RemoteEmbeddingService
from twin.shared.external.tavily_client import TavilyClient
from twin.shared.external.codebox_client import CodeBoxClient

from twin.march7.memories.memory_manager import MemoryManager
from twin.march7.memories.activate_memory.activate_memory_service import ActiveMemoryService
from twin.march7.memories.activate_memory.events.event_dispatcher import EventDispatcher
from twin.march7.memories.activate_memory.management.context_builder import ContextBuilder
from twin.march7.memories.activate_memory.management.smart_cleanup import SmartCleanup
from twin.march7.memories.activate_memory.management.token_counter import TokenCounter
from twin.march7.memories.activate_memory.storage.ram_storage import LocalMemoryDB
from twin.march7.memories.activate_memory.storage.redis_storage import create_redis_storage
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
        if provider == "qwen":
            self.llm_service = QwenService(persona_path=self.config.persona_path)
        elif provider == "openai":
            self.llm_service = OpenAIService(persona_path=self.config.persona_path)
        elif provider == "lms":
            self.llm_service = LMStudioService(persona_path=self.config.persona_path)
        else:
            self.llm_service = GeminiService(persona_path=self.config.persona_path)

        # Embedding Service
        embedding_provider = getattr(Config, "EMBEDDING_PROVIDER", "qwen").lower()
        if embedding_provider == "qwen":
            self.embedding_service = RemoteEmbeddingService(
                model_name=Config.EMBEDDING_MODEL_NAME,
                api_key=Config.EMBEDDING_API_KEY,
                api_url=Config.EMBEDDING_API_URL,
            )
        else:
            raise ValueError(
                f"Unsupported embedding provider: {embedding_provider}. "
                "Local embeddings removed. Use 'qwen' or other remote provider."
            )

        # T1 Active Memory
        event_bus = EventDispatcher()
        t1_storage = await self._get_t1_storage()

        t1_token_counter = TokenCounter()
        t1_smart_cleanup = SmartCleanup(storage=t1_storage)
        t1_context_builder = ContextBuilder()

        t1_service = ActiveMemoryService(
            storage=t1_storage,
            token_counter=t1_token_counter,
            smart_cleanup=t1_smart_cleanup,
            context_builder=t1_context_builder,
            event_dispatcher=event_bus,
        )

        # T3 Core Memory
        t3_storage = MarkdownStorage()
        # SmartUpdater removed - agent handles merge
        t3_manager = CoreManager(storage=t3_storage)

        # T2 Episodic Memory (shared)
        wiki_storage = await self._get_wiki_storage()
        episodic_memory = EpisodicMemoryManager(
            wiki_storage=wiki_storage,
            embedding_service=self.embedding_service,
        )

        # Memory Manager (no overflow, no evernight)
        self.memory_manager = MemoryManager(
            active_memory=t1_service,
            core_memory=t3_manager,
            event_dispatcher=event_bus,
        )

        # Tool Registry
        tavily_client = self._init_tavily_client()
        codebox_client = self._init_codebox_client()

        # Approval Gate with DM support via Evernight
        dm_client = None
        evernight_url = getattr(Config, "EVERNIGHT_A2A_URL", None)
        if evernight_url:
            dm_client = DMClient(evernight_url=evernight_url)
            logger.info("DM client configured: %s", evernight_url)

        approval_gate = ApprovalGate(dm_client=dm_client)

        tool_registry = ToolRegistry()
        tool_dependencies = {
            "core_manager": t3_manager,
            "memory_manager": episodic_memory,
            "base_memory_path": self.config.persona_path,
            "tavily_client": tavily_client,
            "codebox_client": codebox_client,
            "approval_gate": approval_gate,
            "executor_url": Config.BASH_EXECUTOR_URL,
            "timeout": Config.BASH_EXECUTOR_TIMEOUT,
        }

        system_tools = discover_and_register_tools(
            tools_dir="twin/shared/tools/implementations/system",
            registry=tool_registry,
            dependencies=tool_dependencies,
        )
        logger.info(f"✅ System tools loaded: {len(system_tools)} - {[t.name for t in system_tools]}")

        mcp_tools = discover_and_register_tools(
            tools_dir="twin/shared/tools/implementations/mcp",
            registry=tool_registry,
            dependencies=tool_dependencies,
        )
        logger.info(f"✅ MCP tools loaded: {len(mcp_tools)} - {[t.name for t in mcp_tools]}")

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
                return storage
            else:
                await storage.close()
                return LocalMemoryDB()
        except Exception as e:
            logger.warning(f"Redis connection failed, using RAM: {e}")
            return LocalMemoryDB()

    async def _get_wiki_storage(self):
        from twin.shared.memories.wiki.wiki_storage import WikiStorage

        try:
            storage = WikiStorage(url=Config.QDRANT_URL, api_key=Config.QDRANT_API_KEY)
            await storage.initialize()
            return storage
        except Exception as e:
            raise RuntimeError(f"Wiki storage init failed: {e}")

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
