# src/dependencies.py
import logging

from dotenv import load_dotenv

from src.config.settings import Config

# --- Coordinator ---
from src.services.chat_coordinator import ChatCoordinator
from src.services.llm.embedding_service import LocalEmbeddingService

# --- LLM Services ---
from src.services.llm.gemini_service import GeminiService
from src.services.llm.qwen_service import QwenService
from src.services.memories.activate_memory.activate_memory_service import (
    ActiveMemoryService,
)
from src.services.memories.activate_memory.evaluation.pipeline import EvaluationPipeline
from src.services.memories.activate_memory.evaluation.rule_engine import RuleEngine
from src.services.memories.activate_memory.evaluation.sematic_enegine import (
    SemanticEngine,
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
from src.services.memories.core_memory.core_manager import CoreManager
from src.services.memories.core_memory.smart_updater import SmartUpdater
from src.services.memories.core_memory.storage.local_yaml_db import LocalYamlDB
from src.services.memories.episodic_memory.episodic_manager import EpisodicManager
from src.services.memories.episodic_memory.extraction.event_extractor import (
    EventExtractor,
)
from src.services.memories.episodic_memory.extraction.retrieval.vector_engine import (
    VectorEngine,
)
from src.services.memories.episodic_memory.storage.local_vector_db import LocalVectorDB
from src.services.memories.memory_manager import MemoryManager

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
        t1_storage = LocalMemoryDB()

        # Cắm Embedding Service xịn xò vào Semantic Engine thay vì cắm nhầm Chat LLM
        t1_semantic = SemanticEngine(embedding_service=self.embedding_service)
        t1_pipeline = EvaluationPipeline(RuleEngine(), t1_semantic)

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
        t3_storage = LocalYamlDB()
        t3_updater = SmartUpdater(llm_client=self.llm_service, storage=t3_storage)
        t3_manager = CoreManager(storage=t3_storage, smart_updater=t3_updater)

        # 4. LẮP RÁP BỘ NHỚ TẦNG 2 (Episodic Memory)
        t2_storage = LocalVectorDB()

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

        # 6. KHỞI TẠO NHẠC TRƯỞNG GIAO TIẾP
        self.chat_coordinator = ChatCoordinator(
            memory_manager=self.memory_manager, llm_service=self.llm_service
        )

        logger.info("✅ Hệ thống đã sẵn sàng online!")

    async def shutdown(self):
        """Đóng các kết nối khi bot tắt."""
        if self.llm_service:
            await self.llm_service.close()


# Hàm tiện ích để gọi ở các file khác
def get_coordinator() -> ChatCoordinator:
    return AppContainer.get_instance().chat_coordinator
