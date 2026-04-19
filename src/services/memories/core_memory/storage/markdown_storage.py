# src/services/memories/core_memory/storage/markdown_storage.py
import os
import logging

logger = logging.getLogger(__name__)

class MarkdownStorage:
    def __init__(self, base_path: str = "memories/users"):
        self.base_path = base_path
        os.makedirs(self.base_path, exist_ok=True)

    def _get_file_path(self, user_id: str) -> str:
        return os.path.join(self.base_path, f"{user_id}.md")

    def get_profile(self, user_id: str) -> str:
        """Đọc profile Markdown từ file, nếu chưa có thì trả về template mặc định"""
        path = self._get_file_path(user_id)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception as e:
                logger.error(f"Lỗi khi đọc T3 của user {user_id}: {e}")
        
        # Template mặc định khi user mới tinh
        return "# HỒ SƠ NGƯỜI DÙNG\n\nChưa có thông tin."

    def save_profile(self, user_id: str, content: str) -> bool:
        """Ghi đè nội dung Markdown mới xuống file"""
        path = self._get_file_path(user_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content.strip())
            return True
        except Exception as e:
            logger.error(f"Lỗi khi lưu T3 của user {user_id}: {e}")
            return False