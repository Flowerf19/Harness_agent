import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Callable, Dict, List

sys.path.insert(0, "/home/flowerf/Projects/Arize_Phoenix_tool_kit")
from phoenix_core import track_rag_step

from ..background import MemoryBackgroundService
from ..working_memory import WorkingMemoryService
from .episodic_service import EpisodicService
from .memory_storage import MemoryStorage
from .semantic_service import SemanticService
from .summary_service import SummaryService

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Lớp quản lý tập trung cho cả 3 tầng bộ nhớ:
    - Working Memory (Tầng 1 - Ngắn hạn)
    - Episodic Memory (Tầng 2 - Nhật ký)
    - Core Persona (Tầng 3 - Hồ sơ cốt lõi)
    """

    def __init__(self, llm_service, data_dir: str):
        self.llm_service = llm_service
        self.data_dir = data_dir

        # Khởi tạo storage service
        self.memory_storage = MemoryStorage(data_dir)

        # Khởi tạo các service bộ nhớ chuyên biệt
        self.summary_service = SummaryService(llm_service, data_dir)
        self.episodic_service = EpisodicService(data_dir)
        self.semantic_service = SemanticService(llm_service, data_dir)

        # Khởi tạo các tầng bộ nhớ
        # Khởi tạo relationship service trước
        from .relationship import RelationshipService
        from .working_memory import ConversationManager, WorkingMemoryService

        self.relationship_service = RelationshipService(llm_service, data_dir)

        # Khởi tạo working memory service trước
        self.working_memory = WorkingMemoryService(
            max_capacity=20, trigger_threshold=20
        )

        # Khởi tạo conversation manager với working memory service
        self.conversation_manager = ConversationManager(self.working_memory)

        # Sau đó khởi tạo background service với relationship service và working memory service
        self.background_service = MemoryBackgroundService(
            llm_service, data_dir, self.relationship_service, self.working_memory
        )

        # Context cho từng người dùng
        self.user_contexts: Dict[str, Dict] = {}

        # Callback cho các trigger
        self.trigger_callbacks: List[Callable] = []

        # Đăng ký callback cho working memory
        self.working_memory.register_trigger_callback(self._on_working_memory_trigger)

        logger.info("🧠 MemoryManager initialized with 3 memory tiers")

    def initialize_user_context(self, user_id: str):
        """Khởi tạo context cho người dùng mới"""
        if user_id not in self.user_contexts:
            self.user_contexts[user_id] = {
                "last_activity": datetime.now(),
                "session_start": datetime.now(),
                "message_count": 0,
                "needs_persona_update": False,
                "last_episodic_update": None,
                "last_persona_update": None,
            }

        # Ensure user data files exist - sử dụng memory storage service
        self.memory_storage.ensure_user_files_exist(user_id)

    @track_rag_step(
        name="memory_manager.add_message",
        metadata={"service": "memory_manager", "operation": "add_message"},
    )
    def add_message(self, user_id: str, role: str, content: str):
        """
        Thêm tin nhắn vào hệ thống bộ nhớ
        """
        # Khởi tạo context nếu chưa có
        self.initialize_user_context(user_id)

        # Cập nhật thông tin context
        self.user_contexts[user_id]["last_activity"] = datetime.now()
        self.user_contexts[user_id]["message_count"] += 1

        # Thêm vào working memory
        self.working_memory.add_message(user_id, role, content)

        # Lưu tin nhắn vào history file ngay lập tức
        self.conversation_manager.append_message_to_persistent_history(
            user_id, role, content
        )

        # Ghi nhận hoạt động cho background service
        self.background_service.record_user_activity(user_id)

        logger.debug(f"🧠 Added message to memory for {user_id}: {content[:50]}...")

    @track_rag_step(
        name="memory_manager.get_context",
        metadata={"service": "memory_manager", "operation": "get_context"},
    )
    def get_context(self, user_id: str) -> Dict:
        """
        Lấy toàn bộ context cho người dùng bao gồm cả 3 tầng bộ nhớ
        """
        # Ensure user files exist - sử dụng memory storage service
        self.memory_storage.ensure_user_files_exist(user_id)

        # Lấy thông tin từ working memory
        working_context = self.working_memory.get_context(user_id, max_entries=5)

        # Lấy thông tin từ core persona (từ summary service)
        core_summary = self.summary_service.get_core_persona(user_id)

        # Tạo context tổng hợp
        context = {
            "working_memory": [
                {
                    "role": entry.role,
                    "content": entry.content,
                    "importance": entry.importance_score,
                    "category": entry.category.value,
                    "timestamp": entry.timestamp.isoformat(),
                }
                for entry in working_context
            ],
            "core_persona": core_summary,
            "user_stats": self.working_memory.get_statistics(user_id),
            "session_info": self.user_contexts.get(user_id, {}),
        }

        return context

    @track_rag_step(
        name="memory_manager.get_working_memory_context",
        metadata={
            "service": "memory_manager",
            "operation": "get_working_memory_context",
        },
    )
    def get_working_memory_context(
        self, user_id: str, max_entries: int = 5
    ) -> List[Dict]:
        """
        Lấy context từ working memory
        """
        # Ensure user files exist - sử dụng memory storage service
        self.memory_storage.ensure_user_files_exist(user_id)

        entries = self.working_memory.get_context(user_id, max_entries)
        return [
            {
                "role": entry.role,
                "content": entry.content,
                "importance": entry.importance_score,
                "category": entry.category.value,
            }
            for entry in entries
        ]

    @track_rag_step(
        name="memory_manager.get_core_persona",
        metadata={"service": "memory_manager", "operation": "get_core_persona"},
    )
    def get_core_persona(self, user_id: str) -> str:
        """
        Lấy core persona của người dùng từ background_service
        """
        # Ensure user files exist - sử dụng memory storage service
        self.memory_storage.ensure_user_files_exist(user_id)

        return self.summary_service.get_core_persona(user_id)

    def get_episodic_memory(self, user_id: str, limit: int = 10) -> List[Dict]:
        """
        Lấy episodic memory của người dùng
        """
        # Đọc từ episodic service
        return self.episodic_service.get_episodic_memory(user_id, limit)

    @track_rag_step(
        name="memory_manager.trigger_episodic_update",
        metadata={"service": "memory_manager", "operation": "episodic_update"},
    )
    def trigger_episodic_update(self, user_id: str):
        """
        Kích hoạt cập nhật episodic memory cho người dùng
        """
        logger.info(f"🔄 Triggering episodic memory update for {user_id}")

        # Ensure user files exist - sử dụng memory storage service
        self.memory_storage.ensure_user_files_exist(user_id)

        # Gọi trực tiếp phương thức cập nhật từ episodic service
        # Note: Trong phiên bản hiện tại, _update_episodic_memory vẫn nằm trong background_service
        # để giữ backward compatibility, nhưng nên chuyển sang episodic_service trong tương lai
        asyncio.create_task(self.background_service._update_episodic_memory(user_id))

    @track_rag_step(
        name="memory_manager.trigger_persona_update",
        metadata={"service": "memory_manager", "operation": "persona_update"},
    )
    def trigger_persona_update(self, user_id: str):
        """
        Kích hoạt cập nhật core persona cho người dùng
        """
        logger.info(f"🔄 Triggering core persona update for {user_id}")

        # Ensure user files exist - sử dụng memory storage service
        self.memory_storage.ensure_user_files_exist(user_id)

        # Gọi trực tiếp phương thức cập nhật từ summary service
        # Note: Trong phiên bản hiện tại, _update_core_persona vẫn nằm trong background_service
        # để giữ backward compatibility, nhưng nên chuyển sang summary_service trong tương lai
        asyncio.create_task(self.background_service._update_core_persona(user_id))

    def _on_working_memory_trigger(self, trigger_type: str, user_id: str, data: any):
        """
        Xử lý các trigger từ working memory
        """
        logger.info(
            f"🔔 Working memory trigger: {trigger_type} for {user_id} with data: {data}"
        )

        if trigger_type == "MESSAGE_THRESHOLD_REACHED":
            # Kích hoạt cập nhật episodic memory khi đạt ngưỡng tin nhắn
            self.trigger_episodic_update(user_id)

            # FIX MEMORY LEAK: Xóa bớt RAM, chỉ giữ lại khoảng 10 tin nhắn gần nhất làm context
            self.working_memory.cleanup_old_entries(user_id, keep_count=10)

    def register_trigger_callback(self, callback: Callable):
        """
        Đăng ký callback cho các trigger
        """
        self.trigger_callbacks.append(callback)

    def start_background_services(self):
        """
        Khởi động các dịch vụ nền
        """
        self.background_service.start()
        logger.info("🔄 Background services started")

    def stop_background_services(self):
        """
        Dừng các dịch vụ nền
        """
        self.background_service.stop()
        logger.info("🔄 Background services stopped")

    def get_memory_status(self, user_id: str) -> Dict:
        """
        Lấy trạng thái tổng quát của bộ nhớ cho người dùng
        """
        working_stats = self.working_memory.get_statistics(user_id)

        # Kiểm tra sự tồn tại của các file bộ nhớ thông qua memory storage
        memory_status = self.memory_storage.get_memory_status(user_id)

        return {
            "working_memory": working_stats,
            "core_persona_exists": memory_status["summary_exists"],
            "episodic_memory_exists": memory_status["episodic_exists"],
            "history_exists": memory_status["history_exists"],
            "session_info": self.user_contexts.get(user_id, {}),
            "last_activity": self.user_contexts.get(user_id, {}).get(
                "last_activity", None
            ),
        }

    def reset_user_memory(self, user_id: str):
        """
        Đặt lại bộ nhớ cho người dùng
        """
        # Xóa khỏi working memory
        self.working_memory.clear_memory(user_id)

        # Xóa context người dùng
        if user_id in self.user_contexts:
            del self.user_contexts[user_id]

        # Xóa các file bộ nhớ thông qua memory storage
        self.memory_storage.reset_user_files(user_id)

    async def force_update_all_memories(self, user_id: str):
        """
        Buộc cập nhật tất cả các tầng bộ nhớ
        """
        logger.info(f"🔄 Force updating all memories for {user_id}")

        # Cập nhật episodic memory
        # Note: Vẫn sử dụng background_service để giữ backward compatibility
        await self.background_service._update_episodic_memory(user_id)

        # Cập nhật core persona
        # Note: Vẫn sử dụng background_service để giữ backward compatibility
        await self.background_service._update_core_persona(user_id)

        logger.info(f"✅ All memories updated for {user_id}")

    def search_memory(self, user_id: str, query: str) -> Dict:
        """
        Tìm kiếm trong tất cả các tầng bộ nhớ
        """
        results = {}

        # Tìm trong working memory
        keywords = [query.lower()]  # Đơn giản hóa: chỉ tìm theo từ khóa
        working_results = self.working_memory.search_by_keywords(
            user_id, keywords, limit=5
        )
        results["working_memory"] = [
            {
                "content": entry.content,
                "role": entry.role,
                "importance": entry.importance_score,
                "category": entry.category.value,
                "timestamp": entry.timestamp.isoformat(),
            }
            for entry in working_results
        ]

        # Tìm trong episodic memory
        episodic_memory = self.episodic_service.get_episodic_memory(user_id, limit=20)
        query_lower = query.lower()
        episodic_results = [
            event
            for event in episodic_memory
            if query_lower in event.get("summary", "").lower()
            or query_lower in event.get("details", "").lower()
        ][:5]
        results["episodic_memory"] = episodic_results

        # Trong core persona, tìm kiếm đơn giản trong nội dung
        core_persona = self.summary_service.get_core_persona(user_id)
        if query_lower in core_persona.lower():
            results["core_persona"] = {
                "found": True,
                "preview": core_persona[:200] + "..."
                if len(core_persona) > 200
                else core_persona,
            }
        else:
            results["core_persona"] = {"found": False}

        return results

    async def record_priority_event(
        self, user_id: str, event_type: str, event_data: any = None
    ):
        """
        Ghi nhận sự kiện ưu tiên
        """
        await self.background_service.record_priority_event(
            user_id, event_type, event_data
        )
