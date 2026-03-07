import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

from Arize_Phoenix_tool_kit.decorators import track_general_step

logger = logging.getLogger(__name__)


class EpisodicService:
    """
    Service xử lý trí nhớ theo tập (episodic memory) - lưu trữ các sự kiện và tương tác quan trọng.
    Chịu trách nhiệm quản lý, cập nhật và truy xuất các sự kiện episodic của người dùng.
    """

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.user_summaries_dir = os.path.join(data_dir, "user_summaries")
        os.makedirs(self.user_summaries_dir, exist_ok=True)

    def _get_episodic_file_path(self, user_id: str) -> str:
        """Lấy đường dẫn file episodic memory cho user"""
        return os.path.join(self.user_summaries_dir, f"{user_id}_episodic.json")

    @track_general_step(
        step_name="Memory: get_episodic_memories",
        metadata={"version": "1.0.2", "environment": "local_dev", "service": "memory"},
        tags=["memory", "episodic", "query"],
    )
    def get_episodic_memory(self, user_id: str, limit: int = 10) -> List[Dict]:
        """
        Lấy episodic memory của người dùng từ file.
        Trả về danh sách các sự kiện gần nhất, giới hạn theo tham số limit.
        """
        episodic_file = self._get_episodic_file_path(user_id)

        # Ensure the file exists
        if not os.path.exists(episodic_file):
            # Create the file with an empty array
            os.makedirs(os.path.dirname(episodic_file), exist_ok=True)
            with open(episodic_file, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            logger.debug(f"📄 Created default episodic file for user {user_id}")
            return []

        try:
            with open(episodic_file, "r", encoding="utf-8") as f:
                events = json.load(f)
                # Trả về các sự kiện gần nhất
                return events[-limit:] if len(events) > limit else events
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Error loading episodic memory for {user_id}: {e}")
            return []

    def _save_episodic_memory(self, user_id: str, events: List[Dict]):
        """
        Lưu danh sách sự kiện episodic vào file.
        """
        episodic_file = self._get_episodic_file_path(user_id)
        try:
            with open(episodic_file, "w", encoding="utf-8") as f:
                json.dump(events, f, ensure_ascii=False, indent=2)
            logger.debug(
                f"💾 Saved episodic memory for user {user_id} ({len(events)} events)"
            )
        except IOError as e:
            logger.error(f"Error saving episodic memory for {user_id}: {e}")

    async def _update_episodic_memory(
        self, user_id: str, working_memory_entries: List[Dict] = None
    ):
        """
        Cập nhật episodic memory cho người dùng.
        Nếu working_memory_entries được cung cấp, sử dụng nó để tạo sự kiện mới.
        Nếu không, lấy từ working memory service.
        """
        # TODO: Implement actual logic to extract episodic events from working memory
        # This would typically involve calling LLM to extract key events from conversation history

        current_events = self.get_episodic_memory(user_id, limit=100)

        if working_memory_entries:
            # Tạo sự kiện mới từ working memory entries
            new_event = await self._extract_episodic_event(
                working_memory_entries, user_id
            )
            if new_event:
                current_events.append(new_event)
                # Giới hạn số lượng sự kiện để tránh file quá lớn
                if len(current_events) > 50:
                    current_events = current_events[-50:]
                self._save_episodic_memory(user_id, current_events)
                logger.info(f"✅ Added new episodic event for user {user_id}")
        else:
            # Trường hợp không có working memory entries cụ thể
            # Có thể implement logic để phân tích toàn bộ lịch sử
            logger.warning(
                f"⚠️ No working memory entries provided for episodic update for {user_id}"
            )

    async def _extract_episodic_event(
        self, working_memory_entries: List[Dict], user_id: str
    ) -> Optional[Dict]:
        """
        Trích xuất sự kiện episodic từ các entry trong working memory.
        Đây là placeholder - cần implement logic cụ thể với LLM service.
        """
        # TODO: Implement actual LLM call to extract episodic events
        # For now, create a simple event based on the entries
        if not working_memory_entries:
            return None

        # Simple implementation - in real scenario, this would use LLM
        # to extract meaningful events from conversation
        content_summary = " ".join(
            [entry.get("content", "") for entry in working_memory_entries[-3:]]
        )
        return {
            "timestamp": datetime.now().isoformat(),
            "summary": f"Interaction summary for user {user_id}",
            "details": content_summary[:300],
            "type": "conversation",
            "importance": 0.5,
        }

    def ensure_user_files_exist(self, user_id: str):
        """Đảm bảo file episodic memory tồn tại cho người dùng"""
        episodic_file = self._get_episodic_file_path(user_id)
        if not os.path.exists(episodic_file):
            with open(episodic_file, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            logger.debug(f"📄 Created default episodic file for user {user_id}")

    @track_general_step(
        step_name="Memory: add_episodic_memory",
        metadata={"version": "1.0.2", "environment": "local_dev", "service": "memory"},
        tags=["memory", "episodic", "add"],
    )
    def add_priority_event(self, user_id: str, event_type: str, event_data: any = None):
        """
        Thêm sự kiện ưu tiên vào episodic memory.
        """
        current_events = self.get_episodic_memory(user_id, limit=100)

        event = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "data": event_data,
            "importance": 1.0,  # Priority events have high importance
            "summary": f"Priority event: {event_type}",
        }

        current_events.append(event)
        if len(current_events) > 50:
            current_events = current_events[-50:]
        self._save_episodic_memory(user_id, current_events)
        logger.info(
            f"✅ Added priority episodic event for user {user_id}: {event_type}"
        )
