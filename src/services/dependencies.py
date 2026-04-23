# src/dependencies.py
import logging

from dotenv import load_dotenv

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
from src.services.memories.activate_memory.evaluation.pipeline import EvaluationPipeline
from src.services.memories.activate_memory.evaluation.rule_engine import RuleEngine

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
    RedisStorage,
    create_redis_storage,
)
from src.services.memories.activate_memory.storage.base_storage import BaseStorage
from src.services.memories.core_memory.core_manager import CoreManager
from src.services.memories.core_memory import SmartUpdater, MarkdownStorage
from src.services.memories.episodic_memory.episodic_manager import EpisodicManager
from src.services.memories.episodic_memory.extraction.event_extractor import (
    EventExtractor,
)
from src.services.memories.episodic_memory.extraction.retrieval.vector_engine import (
    VectorEngine,
)
from src.services.memories.episodic_memory.storage.qdrant_vector_db import QdrantVectorDB
from src.services.memories.memory_manager import MemoryManager

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
        self.qdrant_storage = None  # Track Qdrant storage for cleanup
        self.tavily_client = None  # Tavily web search client

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

        # --- 🔴 ĐIỂM MỚI ---
        # 1.5 KHỞI TẠO ĐỘNG CƠ VECTOR (Embedding)
        self.embedding_service = LocalEmbeddingService(
            model_name="Qwen/Qwen3-Embedding-0.6B"
        )
        # -------------------

        # --- 🔴 SỬA LỖI KHỞI TẠO MODEL EMBEDDING ---
        # Gọi initialize() để tải model embedding trước khi sử dụng
        await self.embedding_service.initialize()
        # -----------------------------------------

        # 2. LẮP RÁP BỘ NHỚ TẦNG 1 (Active Memory)
        event_bus = EventDispatcher()

        # === 🔴 STORAGE FACTORY: Redis vs RAM ===
        t1_storage = await self._get_t1_storage()
        # ========================================

        # T1 Pipeline chỉ dùng RuleEngine (không dùng embedding)
        t1_pipeline = EvaluationPipeline(RuleEngine())

        # Khởi tạo các thành phần phụ trợ cho Tầng 1
        t1_token_counter = TokenCounter()
        t1_smart_cleanup = SmartCleanup(storage=t1_storage)
        t1_context_builder = ContextBuilder()

        # Khởi tạo Active Memory Service (Tầng 1)
        t1_service = ActiveMemoryService(
            storage=t1_storage,
            pipeline=t1_pipeline,
            token_counter=t1_token_counter,
            smart_cleanup=t1_smart_cleanup,
            context_builder=t1_context_builder,
            event_dispatcher=event_bus,
        )

        # 3. LẮP RÁP BỘ NHỚ TẦNG 3 (Core Memory)
        # Tầng 3 chỉ cần Chat LLM để làm thư ký tóm tắt, không cần Embedding

        t3_storage = MarkdownStorage()
        t3_updater = SmartUpdater(llm_client=self.llm_service, storage=t3_storage)
        t3_manager = CoreManager(storage=t3_storage, smart_updater=t3_updater)

        # 4. LẮP RÁP BỘ NHỚ TẦNG 2 (Episodic Memory)
        t2_storage = await self._get_t2_storage()

        # Trạm trích xuất dùng LLM để bóc tách tin nhắn
        t2_extractor = EventExtractor(llm_client=self.llm_service)

        # Trạm nhúng Vector dùng mô hình Qwen 0.6B Local
        t2_vector_engine = VectorEngine(embedding_service=self.embedding_service)

        # Nhạc trưởng Tầng 2 điều phối tất cả
        t2_manager = EpisodicManager(
            extractor=t2_extractor,
            vector_engine=t2_vector_engine,
            storage=t2_storage,
        )

        # 5. GỘP VÀO MASTER ORCHESTRATOR
        self.memory_manager = MemoryManager(
            active_memory=t1_service,
            episodic_memory=t2_manager,
            core_memory=t3_manager,
            event_dispatcher=event_bus,
        )

        # 6. KHỞI TẠO MCP TOOL SYSTEM (Đôi tay của Agent)
        # ================================================
        # Architecture: Registry Pattern + MCP Client-Server

        # 6.0 KHỞI TẠO TAVILY CLIENT (Web Search)
        self.tavily_client = self._init_tavily_client()

        # 6.1 Tạo Tool Registry
        tool_registry = ToolRegistry()

        # 6.2 Khám phá và đăng ký tools tự động
        # Dependencies để inject vào các tools
        tool_dependencies = {
            "episodic_manager": t2_manager,
            "core_manager": t3_manager,
            "base_memory_path": "memories",
            "tavily_client": self.tavily_client,
        }

        # Auto-discover tools từ implementations directory
        tools_dir = "src/services/tools/implementations"
        discovered_tools = discover_and_register_tools(
            tools_dir=tools_dir,
            registry=tool_registry,
            dependencies=tool_dependencies,
        )
        logger.info(f"🔧 MCP: Đã khám phá {len(discovered_tools)} tools")

        # 6.3 Tạo MCP Server
        mcp_server = MCPServer(
            registry=tool_registry,
            server_name="discord-bot-mcp-server",
            server_version="1.0.0",
            tool_timeout=60,  # Timeout 60s cho tool execution
        )

        # 6.4 Tạo MCP Client (via InMemoryTransport)
        mcp_transport = InMemoryTransport(mcp_server)
        mcp_client = MCPClient(transport=mcp_transport)

        # 6.5 Cache tool schemas (để LLM services dùng ngay)
        await mcp_client.list_tools()

        # 6.6 Inject MCP Client vào LLM Service
        self.llm_service.set_mcp_client(mcp_client)

        # 7. KHỞI TẠO NHẠC TRƯỞNG GIAO TIẾP
        self.chat_coordinator = ChatCoordinator(
            memory_manager=self.memory_manager,
            llm_service=self.llm_service,
            mcp_client=mcp_client,
        )

        # Store MCP components for later access
        self.mcp_client = mcp_client
        self.mcp_server = mcp_server
        self.tool_registry = tool_registry

        logger.info("✅ Hệ thống đã sẵn sàng online!")

    async def shutdown(self):
        """Đóng các kết nối khi bot tắt."""
        if self.llm_service:
            await self.llm_service.close()
        # Close Redis connection if used
        if self.redis_storage:
            await self.redis_storage.close()
            logger.info("🔴 Redis connection closed")
        # Close Qdrant connection if used
        if self.qdrant_storage:
            await self.qdrant_storage.close()
            logger.info("🔴 Qdrant connection closed")
        # Close Tavily client session
        if self.tavily_client:
            await self.tavily_client.close()
            logger.info("🔴 Tavily client closed")

    async def _get_t1_storage(self) -> BaseStorage:
        """
        Factory method: Chọn storage implementation cho Tầng 1.

        Strategy:
        - Nếu REDIS_ENABLED=true: Thử kết nối Redis
        - Nếu Redis fail hoặc REDIS_ENABLED=false: Fallback về RamStorage

        Returns:
            BaseStorage: RedisStorage hoặc RamStorage instance
        """
        redis_enabled = getattr(Config, "REDIS_ENABLED", False)

        if not redis_enabled:
            logger.info("📦 T1 Storage: Using RamStorage (Redis disabled)")
            return LocalMemoryDB()

        # Try Redis connection
        redis_url = getattr(Config, "REDIS_URL", "redis://localhost:6379")
        redis_password = getattr(Config, "REDIS_PASSWORD", None)
        redis_db = getattr(Config, "REDIS_DB", 0)

        try:
            storage = create_redis_storage(
                redis_url=redis_url,
                redis_password=redis_password,
                redis_db=redis_db,
            )

            # Health check
            if await storage.health_check():
                self.redis_storage = storage  # Track for cleanup
                logger.info(f"🔴 T1 Storage: Using RedisStorage (URL: {redis_url})")
                return storage
            else:
                logger.warning("🔴 Redis health check failed, falling back to RamStorage")
                await storage.close()
                return LocalMemoryDB()

        except Exception as e:
            logger.warning(f"🔴 Redis connection failed: {e}, falling back to RamStorage")
            return LocalMemoryDB()

    async def _get_t2_storage(self):
        """
        Factory method: Khởi tạo Qdrant storage cho Tầng 2 (Episodic Memory).

        Returns:
            BaseVectorDB: QdrantVectorDB instance

        Raises:
            RuntimeError: Nếu không kết nối được Qdrant
        """
        qdrant_url = getattr(Config, "QDRANT_URL", "http://localhost:6333")
        qdrant_api_key = getattr(Config, "QDRANT_API_KEY", None)
        qdrant_collection = getattr(Config, "QDRANT_COLLECTION_NAME", "episodic_memory")

        try:
            storage = QdrantVectorDB(
                url=qdrant_url,
                api_key=qdrant_api_key,
                collection_name=qdrant_collection,
            )

            # Initialize collection
            await storage.initialize()
            self.qdrant_storage = storage  # Track for cleanup
            logger.info(f"🔴 T2 Storage: Using QdrantVectorDB (URL: {qdrant_url})")
            return storage

        except Exception as e:
            logger.error(f"❌ Qdrant connection failed: {e}")
            raise RuntimeError(f"Không thể kết nối Qdrant: {e}")

    def _init_tavily_client(self) -> TavilyClient | None:
        """
        Initialize Tavily client for web search.

        Returns None if TAVILY_API_KEY is not configured (graceful degradation).

        Returns:
            TavilyClient | None: Client instance or None if not configured
        """
        if not Config.TAVILY_API_KEY:
            logger.info("📦 Tavily: API key not configured, web search disabled")
            return None

        try:
            client = TavilyClient()
            logger.info(f"✅ Tavily client initialized - web search enabled")
            return client
        except Exception as e:
            logger.warning(f"⚠️ Tavily client initialization failed: {e}")
            return None


# Hàm tiện ích để gọi ở các file khác
def get_coordinator() -> ChatCoordinator:
    return AppContainer.get_instance().chat_coordinator