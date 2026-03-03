import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List

logger = logging.getLogger(__name__)


class MessageCategory(Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    QUERY = "query"
    RESPONSE = "response"
    RELATIONSHIP = "relationship"
    GOAL = "goal"
    STATUS_UPDATE = "status_update"
    GENERAL = "general"


@dataclass
class WorkingMemoryEntry:
    role: str  # 'user' hoặc 'assistant'
    content: str
    timestamp: datetime
    importance_score: float = 0.5  # 0.0 - 1.0
    category: MessageCategory = MessageCategory.GENERAL
    access_count: int = 0
    is_sensitive: bool = False


class WorkingMemoryService:
    """
    Dịch vụ quản lý Working Memory (Tầng 1 - Ngắn hạn)
    """

    def __init__(self, max_capacity: int = 20, trigger_threshold: int = 20):
        self.max_capacity = max_capacity  # Số lượng tin nhắn tối đa
        self.trigger_threshold = trigger_threshold  # Ngưỡng kích hoạt cập nhật
        self.memories: Dict[str, List[WorkingMemoryEntry]] = {}  # Lưu theo user_id
        self.trigger_callbacks = []  # Danh sách callback khi đạt ngưỡng

    def add_message(self, user_id: str, role: str, content: str) -> WorkingMemoryEntry:
        """
        Thêm tin nhắn vào working memory với đánh giá mức độ quan trọng
        """
        # Tính toán mức độ quan trọng
        importance_score, category = self._evaluate_importance(content, role)

        entry = WorkingMemoryEntry(
            role=role,
            content=content,
            timestamp=datetime.now(),
            importance_score=importance_score,
            category=category,
        )

        # Thêm vào danh sách của người dùng
        if user_id not in self.memories:
            self.memories[user_id] = []

        self.memories[user_id].append(entry)

        # Kiểm tra điều kiện trigger
        self._check_trigger_conditions(user_id)

        logger.debug(
            f"📥 Added message to working memory for {user_id}: {content[:50]}..."
        )

        return entry

    def _evaluate_importance(
        self, content: str, role: str
    ) -> tuple[float, MessageCategory]:
        """
        Đánh giá mức độ quan trọng của tin nhắn dựa trên:
        - Vai trò (user/assistant)
        - Độ dài tin nhắn
        - Nội dung thực sự (phân tích từ khóa đơn giản)

        Logic đơn giản nhưng hiệu quả:
        1. Ưu tiên phát hiện thông tin nhạy cảm
        2. Phát hiện câu hỏi (dấu ?)
        3. Phân loại nội dung dựa trên từ khóa đặc trưng
        """
        importance = 0.5  # Mức mặc định
        category = MessageCategory.GENERAL

        # Chuyển đổi nội dung sang lowercase để so sánh không phân biệt hoa thường
        content_lower = content.lower()

        # Tăng mức độ quan trọng nếu là tin nhắn của người dùng (+0.2)
        if role == "user":
            importance += 0.2

        # Tăng mức độ quan trọng nếu tin nhắn dài (nhiều text) (+0.1)
        if len(content) > 50:  # Tin nhắn dài hơn 50 ký tự
            importance += 0.1

        # === PHÂN TÍCH NỘI DUNG ĐƠN GIẢN ===

        # 1. Thông tin nhạy cảm (ưu tiên cao nhất) (+0.4)
        sensitive_keywords = ["mật khẩu", "password", "token", "key", "secret"]
        if any(keyword in content_lower for keyword in sensitive_keywords):
            return min(importance + 0.4, 1.0), MessageCategory.FACT

        # 2. Câu hỏi (+0.2)
        if "?" in content:
            return min(importance + 0.2, 1.0), MessageCategory.QUERY

        # 3. Thông tin cá nhân (+0.3)
        personal_keywords = [
            "tôi tên",
            "tên tôi",
            "tuổi",
            "sinh năm",
            "sống ở",
            "làm việc tại",
            "nghề",
        ]
        if any(keyword in content_lower for keyword in personal_keywords):
            return min(importance + 0.3, 1.0), MessageCategory.FACT

        # 4. Sở thích (+0.25)
        preference_keywords = ["thích", "yêu", "đam mê", "sở thích", "hobby", "ước mơ"]
        if any(keyword in content_lower for keyword in preference_keywords):
            return min(importance + 0.25, 1.0), MessageCategory.PREFERENCE

        # 5. Mục tiêu (+0.25)
        goal_keywords = ["mục tiêu", "kế hoạch", "dự định", "muốn", "hy vọng", "sẽ"]
        if any(keyword in content_lower for keyword in goal_keywords):
            return min(importance + 0.25, 1.0), MessageCategory.GOAL

        # 6. Mối quan hệ (+0.2)
        relationship_keywords = [
            "gia đình",
            "bạn bè",
            "đồng nghiệp",
            "sếp",
            "người thân",
        ]
        if any(keyword in content_lower for keyword in relationship_keywords):
            return min(importance + 0.2, 1.0), MessageCategory.RELATIONSHIP

        # Trả về giá trị mặc định
        return min(importance, 1.0), category

    def get_context(
        self, user_id: str, max_entries: int = 5
    ) -> List[WorkingMemoryEntry]:
        """
        Lấy ngữ cảnh gần đây từ working memory, ưu tiên thông tin quan trọng
        """
        if user_id not in self.memories or not self.memories[user_id]:
            return []

        # 1. Lấy ra các tin nhắn ưu tiên cao nhất
        user_memory = self.memories[user_id]
        important_entries = sorted(
            user_memory,
            key=lambda x: (x.importance_score, x.timestamp.timestamp()),
            reverse=True,
        )[:max_entries]

        # 2. FIX: Sort lại theo thời gian thực (từ cũ đến mới) để LLM đọc hiểu luồng nói chuyện
        chronological_entries = sorted(
            important_entries, key=lambda x: x.timestamp.timestamp()
        )
        return chronological_entries

    def get_recent_conversation(
        self, user_id: str, max_entries: int = 3
    ) -> List[WorkingMemoryEntry]:
        """
        Lấy cuộc trò chuyện gần đây theo thứ tự thời gian
        """
        if user_id not in self.memories or not self.memories[user_id]:
            return []

        # Lấy các entry gần đây nhất
        user_memory = self.memories[user_id]
        recent_entries = user_memory[-max_entries:]  # Lấy từ cuối danh sách

        # Tăng số lần truy cập cho các entry này
        for entry in recent_entries:
            entry.access_count += 1

        return recent_entries

    def search_by_category(
        self, user_id: str, category: MessageCategory, limit: int = 5
    ) -> List[WorkingMemoryEntry]:
        """
        Tìm kiếm các entry theo danh mục
        """
        if user_id not in self.memories:
            return []

        matching_entries = [
            entry for entry in self.memories[user_id] if entry.category == category
        ]

        # Sắp xếp theo mức độ quan trọng và thời gian
        sorted_entries = sorted(
            matching_entries,
            key=lambda x: (x.importance_score, x.timestamp.timestamp()),
            reverse=True,
        )

        return sorted_entries[:limit]

    def _check_trigger_conditions(self, user_id: str):
        """
        Kiểm tra các điều kiện để kích hoạt các hành động
        """
        if user_id not in self.memories:
            return

        message_count = len(self.memories[user_id])

        # Kích hoạt nếu đạt ngưỡng số lượng tin nhắn
        if message_count >= self.trigger_threshold:
            self._trigger_callback("MESSAGE_THRESHOLD_REACHED", user_id, message_count)

    def register_trigger_callback(self, callback_func):
        """
        Đăng ký hàm callback để xử lý các trigger
        """
        self.trigger_callbacks.append(callback_func)

    def _trigger_callback(self, trigger_type: str, user_id: str, data: any):
        """
        Kích hoạt các callback đã đăng ký
        """
        for callback in self.trigger_callbacks:
            try:
                callback(trigger_type, user_id, data)
            except Exception as e:
                logger.error(f"Error in trigger callback: {e}")

    def cleanup_old_entries(self, user_id: str, keep_count: int = 10):
        """
        Dọn dẹp các entry cũ, giữ lại số lượng nhất định
        """
        if user_id not in self.memories:
            return

        user_memory = self.memories[user_id]

        if len(user_memory) <= keep_count:
            return  # Không cần dọn dẹp

        # Ưu tiên giữ lại các entry quan trọng
        sorted_entries = sorted(
            user_memory,
            key=lambda x: (x.importance_score, x.timestamp.timestamp()),
            reverse=True,
        )

        # Giữ lại số lượng mong muốn
        self.memories[user_id] = sorted_entries[:keep_count]

        logger.debug(
            f"🧹 Cleaned up working memory for {user_id}, kept {len(self.memories[user_id])} entries"
        )

    def get_statistics(self, user_id: str) -> Dict:
        """
        Lấy thống kê về working memory của người dùng
        """
        if user_id not in self.memories:
            return {
                "total_messages": 0,
                "categories": {},
                "avg_importance": 0.0,
            }

        user_memory = self.memories[user_id]

        # Thống kê theo danh mục
        categories = {}
        total_importance = 0

        for entry in user_memory:
            # Thống kê danh mục
            cat = entry.category.value
            categories[cat] = categories.get(cat, 0) + 1

            # Tổng mức độ quan trọng
            total_importance += entry.importance_score

        # Tính trung bình mức độ quan trọng
        avg_importance = total_importance / len(user_memory) if user_memory else 0.0

        return {
            "total_messages": len(user_memory),
            "categories": categories,
            "avg_importance": round(avg_importance, 2),
        }

    def clear_memory(self, user_id: str):
        """
        Xóa toàn bộ working memory của người dùng
        """
        if user_id in self.memories:
            del self.memories[user_id]
            logger.info(f"🗑️ Cleared working memory for {user_id}")
