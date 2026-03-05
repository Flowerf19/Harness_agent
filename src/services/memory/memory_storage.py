import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MemoryStorage:
    """
    Service xử lý lưu trữ và đọc/ghi file cho hệ thống bộ nhớ.
    Chịu trách nhiệm quản lý tất cả các thao tác I/O liên quan đến bộ nhớ người dùng.
    """

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.user_summaries_dir = os.path.join(data_dir, "user_summaries")
        os.makedirs(self.user_summaries_dir, exist_ok=True)

    def _get_summary_file_path(self, user_id: str) -> str:
        """Lấy đường dẫn file summary cho user"""
        return os.path.join(self.user_summaries_dir, f"{user_id}_summary.txt")

    def _get_episodic_file_path(self, user_id: str) -> str:
        """Lấy đường dẫn file episodic memory cho user"""
        return os.path.join(self.user_summaries_dir, f"{user_id}_episodic.json")

    def _get_history_file_path(self, user_id: str) -> str:
        """Lấy đường dẫn file history cho user"""
        return os.path.join(self.user_summaries_dir, f"{user_id}_history.json")

    def ensure_user_files_exist(self, user_id: str):
        """Đảm bảo tất cả các file bộ nhớ tồn tại cho người dùng"""
        # Ensure summary file exists
        summary_file = self._get_summary_file_path(user_id)
        if not os.path.exists(summary_file):
            with open(summary_file, "w", encoding="utf-8") as f:
                f.write("")
            logger.debug(f"📄 Created default summary file for user {user_id}")

        # Ensure episodic file exists
        episodic_file = self._get_episodic_file_path(user_id)
        if not os.path.exists(episodic_file):
            with open(episodic_file, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            logger.debug(f"📄 Created default episodic file for user {user_id}")

        # Ensure history file exists
        history_file = self._get_history_file_path(user_id)
        if not os.path.exists(history_file):
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            logger.debug(f"📄 Created default history file for user {user_id}")

    def read_summary(self, user_id: str) -> str:
        """Đọc nội dung summary từ file"""
        summary_file = self._get_summary_file_path(user_id)

        if not os.path.exists(summary_file):
            logger.debug(
                f"📄 Summary file not found for user {user_id}, returning empty string"
            )
            return ""

        try:
            with open(summary_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                logger.debug(
                    f"📄 Loaded summary for user {user_id}: {content[:100]}..."
                )
                return content
        except IOError as e:
            logger.error(f"Error reading summary file for {user_id}: {e}")
            return ""

    def write_summary(self, user_id: str, content: str):
        """Ghi nội dung summary vào file"""
        summary_file = self._get_summary_file_path(user_id)
        try:
            with open(summary_file, "w", encoding="utf-8") as f:
                f.write(content)
            logger.debug(f"💾 Saved summary for user {user_id}")
        except IOError as e:
            logger.error(f"Error writing summary file for {user_id}: {e}")

    def read_episodic_memory(self, user_id: str, limit: int = 10) -> List[Dict]:
        """Đọc episodic memory từ file"""
        episodic_file = self._get_episodic_file_path(user_id)

        if not os.path.exists(episodic_file):
            logger.debug(
                f"📄 Episodic file not found for user {user_id}, returning empty list"
            )
            return []

        try:
            with open(episodic_file, "r", encoding="utf-8") as f:
                events = json.load(f)
                # Trả về các sự kiện gần nhất
                return events[-limit:] if len(events) > limit else events
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Error loading episodic memory for {user_id}: {e}")
            return []

    def write_episodic_memory(self, user_id: str, events: List[Dict]):
        """Ghi episodic memory vào file"""
        episodic_file = self._get_episodic_file_path(user_id)
        try:
            with open(episodic_file, "w", encoding="utf-8") as f:
                json.dump(events, f, ensure_ascii=False, indent=2)
            logger.debug(
                f"💾 Saved episodic memory for user {user_id} ({len(events)} events)"
            )
        except IOError as e:
            logger.error(f"Error saving episodic memory for {user_id}: {e}")

    def read_history(self, user_id: str) -> List[Dict]:
        """Đọc lịch sử hội thoại từ file"""
        history_file = self._get_history_file_path(user_id)

        if not os.path.exists(history_file):
            logger.debug(
                f"📄 History file not found for user {user_id}, returning empty list"
            )
            return []

        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
                logger.debug(
                    f"📄 Loaded history for user {user_id} ({len(history)} messages)"
                )
                return history
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Error loading history for {user_id}: {e}")
            return []

    def append_to_history(self, user_id: str, message: Dict):
        """Thêm tin nhắn vào lịch sử hội thoại"""
        history = self.read_history(user_id)
        history.append(message)

        # Giới hạn kích thước history để tránh file quá lớn
        if len(history) > 1000:
            history = history[-1000:]

        history_file = self._get_history_file_path(user_id)
        try:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            logger.debug(f"💾 Appended message to history for user {user_id}")
        except IOError as e:
            logger.error(f"Error appending to history for {user_id}: {e}")

    def get_file_paths(self, user_id: str) -> Dict[str, str]:
        """Lấy đường dẫn của tất cả các file bộ nhớ cho user"""
        return {
            "summary": self._get_summary_file_path(user_id),
            "episodic": self._get_episodic_file_path(user_id),
            "history": self._get_history_file_path(user_id),
        }

    def check_file_exists(self, user_id: str, file_type: str) -> bool:
        """Kiểm tra sự tồn tại của file bộ nhớ"""
        file_paths = self.get_file_paths(user_id)
        if file_type in file_paths:
            return os.path.exists(file_paths[file_type])
        return False

    def reset_user_files(self, user_id: str):
        """Xóa tất cả các file bộ nhớ của người dùng"""
        file_paths = self.get_file_paths(user_id)

        for file_path in file_paths.values():
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"🗑️ Removed memory file: {file_path}")
                except Exception as e:
                    logger.error(f"Error removing memory file {file_path}: {e}")

    def get_memory_status(self, user_id: str) -> Dict[str, Any]:
        """Lấy trạng thái lưu trữ bộ nhớ cho người dùng"""
        file_paths = self.get_file_paths(user_id)
        status = {}

        for file_type, file_path in file_paths.items():
            status[f"{file_type}_exists"] = os.path.exists(file_path)
            if os.path.exists(file_path):
                status[f"{file_type}_size"] = os.path.getsize(file_path)
                status[f"{file_type}_modified"] = os.path.getmtime(file_path)
            else:
                status[f"{file_type}_size"] = 0
                status[f"{file_type}_modified"] = None

        return status
