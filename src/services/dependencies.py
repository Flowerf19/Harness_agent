# src/dependencies.py
from __future__ import annotations  # Lazy type annotations to avoid circular imports

import logging

from dotenv import load_dotenv

from src.agents.evernight.services.wiki_storage import WikiStorage
from src.config.settings import Config

# --- Coordinator ---
from src.services.chat_coordinator import ChatCoordinator
from src.services.llm.embedding_service import LocalEmbeddingService

# --- LLM Services ---
from src.services.llm.gemini_service import GeminiService
from src.services.llm.lm_studio_service import LMStudioService
from src.services.llm.qwen_service import QwenService
from src.services.memories.activate_memory.activate_memory_service import (
    ActiveMemoryService,
)

# --- Memory System ---
from src.services.memories.activate_memory.events.event_dispatcher import (
    EventDispatcher,
)
from src.services.memories.activate_memory.management.context_builder import (
    ContextBuilder,
)
from src.services.memories.activate_memory.management.smart_cleanup import SmartCleanup
from src.services.memories.activate_memory.management.token_counter import TokenCounter
from src.services.memories.activate_memory.storage.ram_storage import LocalMemoryDB
from src.services.memories.activate_memory.storage.redis_storage import (
    create_redis_storage,
)
from src.services.memories.activate_memory.storage.base_storage import BaseStorage
from src.services.memories.core_memory.core_manager import CoreManager
from src.services.memories.core_memory import SmartUpdater, MarkdownStorage
from src.services.memories.memory_manager import MemoryManager

# --- Evernight System (T2 Wiki) - Lazy imports to avoid circular dependency ---
# These imports are moved inside initialize() method

# --- Tasks ---
from src.services.queue.overflow_queue import OverflowQueue
from src.tasks.nightly_trigger import NightlyTrigger

# --- Tools System (MCP Architecture) ---
from src.services.tools.tool_registry import ToolRegistry
from src.services.tools.mcp_server import MCPServer
from src.services.tools.mcp_client import MCPClient
from src.services.tools.mcp_transport import InMemoryTransport
from src.services.tools.tool_discovery import discover_and_register_tools

# --- External Services ---
from src.services.external.tavily_client import TavilyClient

logger = logging.getLogger(__name__)


class AppContainer:
    """
    Dependency Injection Container.
    Đảm bảo các services chỉ được khởi tạo 1 lần duy nhất (Singleton).
    """

    _instance = None

    def __init__(self):
        self.llm_service = None
        self.memory_manager = None
        self.chat_coordinator = None
        self.redis_storage = None  # Track Redis storage for cleanup
        self.redis_client = None  # Raw Redis client for queue
        self.tavily_client = None  # Tavily web search client
        self.wiki_storage = None  # Wiki storage for cleanup
        self.nightly_trigger = None  # Scheduled trigger

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize(self):
        """Khởi tạo toàn bộ hệ thống."""
        load_dotenv()
        logger.info("⚡ Đang khởi động Trạm Điện (AppContainer)...")

        # 1. CHỌN ĐỘNG CƠ LLM (Chat)
        provider = getattr(Config, "LLM_PROVIDER", "gemini").lower()
        if provider == "qwen":
            self.llm_service = QwenService()
        elif provider == "lms":
            self.llm_service = LMStudioService()
        else:
            self.llm_service = GeminiService()

        # --- EMBEDDING SERVICE ---
        self.embedding_service = LocalEmbeddingService(
            model_name="Qwen/Qwen3-Embedding-0.6B"
        )
        await self.embedding_service.initialize()

        # 2. LẮP RÁP BỘ NHỚ TẦNG 1 (Active Memory)
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

        # 3. LẮP RÁP BỘ NHỚ TẦNG 3 (Core Memory)
        t3_storage = MarkdownStorage()
        t3_updater = SmartUpdater(llm_client=self.llm_service, storage=t3_storage)
        t3_manager = CoreManager(storage=t3_storage, smart_updater=t3_updater)

        # 4. KHỞI TẠO EVERNIGHT SYSTEM (T2 Wiki)
        # ========================================
        # Lazy imports to avoid circular dependency
        from src.agents.evernight.agent import EvernightAgent
        from src.agents.evernight.services.wiki_merge import WikiMergeService
        from src.agents.evernight.spawner import EvernightSpawner

        wiki_storage = await self._get_wiki_storage()
        wiki_merge = WikiMergeService(llm_client=self.llm_service)

        evernight_agent = EvernightAgent(
            wiki_storage=wiki_storage,
            wiki_merge=wiki_merge,
            llm_client=self.llm_service,
            embedding_service=self.embedding_service,
        )

        # Redis client for overflow queue (reuse if available)
        overflow_queue = await self._get_overflow_queue()
        evernight_spawner = EvernightSpawner(
            evernight_agent=evernight_agent,
            overflow_queue=overflow_queue,
        )

        # 5. GỘP VÀO MASTER ORCHESTRATOR
        self.memory_manager = MemoryManager(
            active_memory=t1_service,
            core_memory=t3_manager,
            event_dispatcher=event_bus,
            overflow_queue=overflow_queue,
            evernight_spawner=evernight_spawner,
        )

        # 6. KHỞI TẠO MCP TOOL SYSTEM
        self.tavily_client = self._init_tavily_client()
        tool_registry = ToolRegistry()

        tool_dependencies = {
            "core_manager": t3_manager,
            "wiki_storage": wiki_storage,
            "embedding_service": self.embedding_service,
            "base_memory_path": "memories",
            "tavily_client": self.tavily_client,
        }

        tools_dir = "src/services/tools/implementations"
        discovered_tools = discover_and_register_tools(
            tools_dir=tools_dir,
            registry=tool_registry,
            dependencies=tool_dependencies,
        )
        logger.info(f"🔧 MCP: Đã khám phá {len(discovered_tools)} tools")

        mcp_server = MCPServer(
            registry=tool_registry,
            server_name="discord-bot-mcp-server",
            server_version="1.0.0",
            tool_timeout=60,
        )

        mcp_transport = InMemoryTransport(mcp_server)
        mcp_client = MCPClient(transport=mcp_transport)
        await mcp_client.list_tools()
        self.llm_service.set_mcp_client(mcp_client)

        # 7. KHỞI TẠO NHẠC TRƯỞNG GIAO TIẾP
        self.chat_coordinator = ChatCoordinator(
            memory_manager=self.memory_manager,
            llm_service=self.llm_service,
            mcp_client=mcp_client,
        )

        # 8. KHỞI TẠO NIGHTLY TRIGGER (Background Task)
        self.nightly_trigger = NightlyTrigger(
            overflow_queue=overflow_queue,
            evernight_spawner=evernight_spawner,
            trigger_hour=2,  # 2 AM
        )

        # Store components for later access
        self.mcp_client = mcp_client
        self.mcp_server = mcp_server
        self.tool_registry = tool_registry
        self.evernight_agent = evernight_agent
        self.evernight_spawner = evernight_spawner

        logger.info("✅ Hệ thống đã sẵn sàng online!")

    async def shutdown(self):
        """Đóng các kết nối khi bot tắt."""
        # Stop nightly trigger
        if self.nightly_trigger:
            self.nightly_trigger.stop()
            logger.info("🔴 Nightly trigger stopped")

        if self.llm_service:
            await self.llm_service.close()

        if self.redis_storage:
            await self.redis_storage.close()
            logger.info("🔴 Redis connection closed")

        if self.redis_client:
            await self.redis_client.close()
            logger.info("🔴 Redis client closed")

        if self.wiki_storage:
            await self.wiki_storage.close()
            logger.info("🔴 Wiki storage closed")

        if self.tavily_client:
            await self.tavily_client.close()
            logger.info("🔴 Tavily client closed")

    async def _get_t1_storage(self) -> BaseStorage:
        """Factory method: Chọn storage implementation cho Tầng 1."""
        redis_enabled = getattr(Config, "REDIS_ENABLED", False)

        if not redis_enabled:
            logger.info("📦 T1 Storage: Using RamStorage (Redis disabled)")
            return LocalMemoryDB()

        redis_url = getattr(Config, "REDIS_URL", "redis://localhost:6379")
        redis_password = getattr(Config, "REDIS_PASSWORD", None)
        redis_db = getattr(Config, "REDIS_DB", 0)

        try:
            storage = create_redis_storage(
                redis_url=redis_url,
                redis_password=redis_password,
                redis_db=redis_db,
            )

            if await storage.health_check():
                self.redis_storage = storage
                # Also get raw Redis client for queue
                self.redis_client = storage.redis
                logger.info(f"🔴 T1 Storage: Using RedisStorage (URL: {redis_url})")
                return storage
            else:
                logger.warning("🔴 Redis health check failed, falling back to RamStorage")
                await storage.close()
                return LocalMemoryDB()

        except Exception as e:
            logger.warning(f"🔴 Redis connection failed: {e}, falling back to RamStorage")
            return LocalMemoryDB()

    async def _get_wiki_storage(self) -> "WikiStorage":
        """Factory method: Khởi tạo WikiStorage cho T2."""
        # Lazy import to avoid circular dependency
        from src.agents.evernight.services.wiki_storage import WikiStorage
        
        qdrant_url = getattr(Config, "QDRANT_URL", "http://localhost:6333")
        qdrant_api_key = getattr(Config, "QDRANT_API_KEY", None)

        try:
            storage = WikiStorage(url=qdrant_url, api_key=qdrant_api_key)
            await storage.initialize()
            self.wiki_storage = storage
            logger.info(f"🔴 Wiki Storage: Using Qdrant (URL: {qdrant_url})")
            return storage

        except Exception as e:
            logger.error(f"❌ Wiki storage initialization failed: {e}")
            raise RuntimeError(f"Không thể kết nối Wiki storage: {e}")

    async def _get_overflow_queue(self) -> "OverflowQueue":
        """Factory method: Khởi tạo OverflowQueue."""
        # Lazy import to avoid circular dependency
        from src.services.queue.overflow_queue import OverflowQueue
        
        # If Redis client already exists (from T1 storage), reuse it
        if self.redis_client:
            logger.info("📦 Overflow Queue: Using existing Redis client")
            return OverflowQueue(redis_client=self.redis_client)

        # Otherwise, create new Redis client
        redis_enabled = getattr(Config, "REDIS_ENABLED", False)
        if not redis_enabled:
            logger.warning("⚠️ Overflow Queue: Redis disabled, using in-memory fallback")
            # Return None - queue disabled
            return None

        redis_url = getattr(Config, "REDIS_URL", "redis://localhost:6379")
        redis_password = getattr(Config, "REDIS_PASSWORD", None)
        redis_db = getattr(Config, "REDIS_DB", 0)

        try:
            import redis.asyncio as redis
            self.redis_client = redis.Redis(
                host=redis_url.split("://")[1].split(":")[0] if "://" in redis_url else "localhost",
                port=int(redis_url.split(":")[-1]) if ":" in redis_url else 6379,
                password=redis_password,
                db=redis_db,
                decode_responses=True,
            )
            logger.info("🔴 Overflow Queue: Created new Redis client")
            return OverflowQueue(redis_client=self.redis_client)

        except Exception as e:
            logger.warning(f"⚠️ Overflow Queue: Failed to create Redis client: {e}")
            return None

    def _init_tavily_client(self) -> TavilyClient | None:
        """Initialize Tavily client for web search."""
        if not Config.TAVILY_API_KEY:
            logger.info("📦 Tavily: API key not configured, web search disabled")
            return None

        try:
            client = TavilyClient()
            logger.info("✅ Tavily client initialized - web search enabled")
            return client
        except Exception as e:
            logger.warning(f"⚠️ Tavily client initialization failed: {e}")
            return None


# Hàm tiện ích để gọi ở các file khác
def get_coordinator() -> ChatCoordinator:
    return AppContainer.get_instance().chat_coordinator