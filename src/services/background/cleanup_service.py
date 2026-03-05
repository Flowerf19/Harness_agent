import asyncio
import json
import logging
import os

logger = logging.getLogger(__name__)


class CleanupService:
    """
    Dịch vụ dọn dẹp dữ liệu cũ và không cần thiết.
    """

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.user_summaries_dir = os.path.join(data_dir, "user_summaries")

        # Lock cho file I/O để ngăn chặn race condition
        self.memory_lock = asyncio.Lock()

    async def cleanup_working_memory(self, user_id: str, messages_to_remove: list):
        """Dọn dẹp working memory sau khi đã trích xuất - chỉ xóa các tin nhắn cụ thể"""
        async with self.memory_lock:
            try:
                history_file = os.path.join(
                    self.user_summaries_dir, f"{user_id}_history.json"
                )

                # Ensure the file exists
                if not os.path.exists(history_file):
                    # Create the file with an empty array
                    os.makedirs(self.user_summaries_dir, exist_ok=True)
                    with open(history_file, "w", encoding="utf-8") as f:
                        json.dump([], f, ensure_ascii=False, indent=2)
                    logger.debug(f"📄 Created default history file for user {user_id}")
                    return

                # Đọc lịch sử hiện tại
                with open(history_file, "r", encoding="utf-8") as f:
                    history = json.load(f)

                if not isinstance(history, list):
                    return

                # Chuyển messages_to_remove thành set để tìm kiếm nhanh hơn
                # So sánh dựa trên nội dung và role
                messages_to_remove_set = set()
                for msg in messages_to_remove:
                    if isinstance(msg, dict) and "role" in msg and "content" in msg:
                        messages_to_remove_set.add((msg["role"], msg["content"]))

                # Lọc ra các tin nhắn không nằm trong danh sách cần xóa
                remaining_history = []
                removed_count = 0
                for msg in history:
                    if isinstance(msg, dict) and "role" in msg and "content" in msg:
                        if (msg["role"], msg["content"]) not in messages_to_remove_set:
                            remaining_history.append(msg)
                        else:
                            removed_count += 1
                    else:
                        # Giữ lại các tin nhắn không hợp lệ (phòng trường hợp lỗi)
                        remaining_history.append(msg)

                # Ghi lại file với phần còn lại
                with open(history_file, "w", encoding="utf-8") as f:
                    json.dump(remaining_history, f, ensure_ascii=False, indent=2)

                logger.info(
                    f"🧹 Cleaned up {removed_count} messages from working memory for {user_id}"
                )

            except Exception as e:
                logger.error(f"❌ Error cleaning up working memory for {user_id}: {e}")

    async def cleanup_old_episodic_events(self, user_id: str, max_events: int = 200):
        """Dọn dẹp các sự kiện episodic cũ để tránh file quá lớn"""
        async with self.memory_lock:
            try:
                episodic_file = os.path.join(
                    self.user_summaries_dir, f"{user_id}_episodic.json"
                )

                if not os.path.exists(episodic_file):
                    return

                # Đọc dữ liệu hiện tại
                with open(episodic_file, "r", encoding="utf-8") as f:
                    existing_events = json.load(f)

                if not isinstance(existing_events, list):
                    return

                # Giới hạn số lượng sự kiện để tránh file quá lớn
                if len(existing_events) > max_events:
                    old_count = len(existing_events)
                    existing_events = existing_events[-max_events:]
                    removed_count = old_count - len(existing_events)

                    # Ghi lại file
                    with open(episodic_file, "w", encoding="utf-8") as f:
                        json.dump(existing_events, f, ensure_ascii=False, indent=2)

                    logger.info(
                        f"🧹 Cleaned up {removed_count} old episodic events for {user_id}"
                    )

            except Exception as e:
                logger.error(
                    f"❌ Error cleaning up old episodic events for {user_id}: {e}"
                )

    async def cleanup_inactive_users(self, days_threshold: int = 30):
        """Dọn dẹp dữ liệu của người dùng không hoạt động trong thời gian dài"""
        import time
        from datetime import datetime, timedelta

        try:
            current_time = time.time()
            threshold_time = current_time - (days_threshold * 24 * 3600)

            # Kiểm tra tất cả các file trong thư mục user_summaries
            if not os.path.exists(self.user_summaries_dir):
                return

            for filename in os.listdir(self.user_summaries_dir):
                if filename.endswith("_metadata.json"):
                    user_id = filename.replace("_metadata.json", "")
                    metadata_file = os.path.join(self.user_summaries_dir, filename)

                    try:
                        # Kiểm tra thời gian sửa đổi cuối cùng của file
                        file_mtime = os.path.getmtime(metadata_file)

                        if file_mtime < threshold_time:
                            # Người dùng không hoạt động đủ lâu, dọn dẹp dữ liệu
                            await self._cleanup_user_data(user_id)

                    except Exception as e:
                        logger.warning(
                            f"⚠️ Error checking metadata file {filename}: {e}"
                        )

        except Exception as e:
            logger.error(f"❌ Error cleaning up inactive users: {e}")

    async def _cleanup_user_data(self, user_id: str):
        """Dọn dẹp toàn bộ dữ liệu của một người dùng"""
        try:
            files_to_remove = [
                f"{user_id}_history.json",
                f"{user_id}_episodic.json",
                f"{user_id}_semantic_memory.json",
                f"{user_id}_summary.txt",
                f"{user_id}_metadata.json",
            ]

            removed_files = 0
            for filename in files_to_remove:
                filepath = os.path.join(self.user_summaries_dir, filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
                    removed_files += 1

            if removed_files > 0:
                logger.info(
                    f"🧹 Cleaned up {removed_files} files for inactive user {user_id}"
                )

        except Exception as e:
            logger.error(f"❌ Error cleaning up user data for {user_id}: {e}")
