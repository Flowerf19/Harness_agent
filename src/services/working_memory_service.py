import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

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
    entities: List[str] = field(default_factory=list)  # Các thực thể được trích xuất
    keywords: List[str] = field(default_factory=list)  # Từ khóa quan trọng


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
        importance_score, category, entities, keywords = self._evaluate_importance(
            content, role
        )

        entry = WorkingMemoryEntry(
            role=role,
            content=content,
            timestamp=datetime.now(),
            importance_score=importance_score,
            category=category,
            entities=entities,
            keywords=keywords,
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
    ) -> tuple[float, MessageCategory, List[str], List[str]]:
        """
        Đánh giá mức độ quan trọng của tin nhắn
        """
        importance = 0.5  # Mức mặc định
        category = MessageCategory.GENERAL
        entities = []
        keywords = []

        content_lower = content.lower()

        # Các mẫu để nhận diện thông tin quan trọng
        personal_info_patterns = [
            (r"(tên|name).*?(là|is|:)\s*(\w+)", MessageCategory.FACT, ["name"]),
            (r"(\d+)\s*(tuổi|age|năm)", MessageCategory.FACT, ["age"]),
            (
                r"(thích|like|love|yêu).*?(\w+)",
                MessageCategory.PREFERENCE,
                ["preference"],
            ),
            (
                r"(bạn|anh|chị|em)\s*(\w+)",
                MessageCategory.RELATIONSHIP,
                ["relationship"],
            ),
            (
                r"(muốn|mong|ước|plan|want|need).*?(đi|làm|có)",
                MessageCategory.GOAL,
                ["goal"],
            ),
        ]

        # Kiểm tra các mẫu thông tin cá nhân
        for pattern, cat, kw_list in personal_info_patterns:
            import re

            matches = re.finditer(pattern, content_lower)
            for match in matches:
                importance += 0.2  # Tăng mức độ quan trọng
                if importance > 1.0:
                    importance = 1.0
                category = cat
                keywords.extend(kw_list)
                # Trích xuất thực thể nếu có
                if len(match.groups()) > 2:
                    entities.append(match.group(3))

        # Tăng mức độ quan trọng nếu là tin nhắn của người dùng
        if role == "user":
            importance += 0.1
            if importance > 1.0:
                importance = 1.0

        # Tăng mức độ quan trọng nếu có cảm xúc mạnh
        emotional_words = [
            "rất",
            "cực kỳ",
            "thật sự",
            "đáng yêu",
            "tuyệt vời",
            "buồn",
            "vui",
            "giận",
        ]
        for word in emotional_words:
            if word in content_lower:
                importance += 0.05
                if importance > 1.0:
                    importance = 1.0

        # Trích xuất từ khóa quan trọng
        keywords.extend(self._extract_keywords(content))

        return min(importance, 1.0), category, list(set(entities)), list(set(keywords))

    def _extract_keywords(self, content: str) -> List[str]:
        """
        Trích xuất từ khóa từ nội dung
        """
        # Đơn giản hóa: tách từ và loại bỏ stop words cơ bản
        import re

        words = re.findall(r"\b\w+\b", content.lower())

        # Stop words cơ bản trong tiếng Việt và Anh
        stop_words = {
            "và",
            "hoặc",
            "nhưng",
            "rồi",
            "với",
            "của",
            "trong",
            "tại",
            "về",
            "qua",
            "trên",
            "dưới",
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "with",
            "of",
            "in",
            "at",
            "to",
            "for",
            "on",
        }

        keywords = [word for word in words if len(word) > 2 and word not in stop_words]
        return list(set(keywords))  # Trả về duy nhất

    def get_context(
        self, user_id: str, max_entries: int = 5
    ) -> List[WorkingMemoryEntry]:
        """
        Lấy ngữ cảnh gần đây từ working memory, ưu tiên thông tin quan trọng
        """
        if user_id not in self.memories or not self.memories[user_id]:
            return []

        # Lấy các entry và sắp xếp theo mức độ quan trọng và thời gian
        user_memory = self.memories[user_id]

        # Sắp xếp theo: (importance_score giảm dần, timestamp giảm dần)
        sorted_entries = sorted(
            user_memory,
            key=lambda x: (x.importance_score, x.timestamp.timestamp()),
            reverse=True,
        )

        # Trả về số lượng tối đa được yêu cầu
        return sorted_entries[:max_entries]

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

    def search_by_keywords(
        self, user_id: str, keywords: List[str], limit: int = 5
    ) -> List[WorkingMemoryEntry]:
        """
        Tìm kiếm các entry theo từ khóa
        """
        if user_id not in self.memories:
            return []

        matching_entries = []
        keywords_lower = [kw.lower() for kw in keywords]

        for entry in self.memories[user_id]:
            # Kiểm tra trong nội dung và từ khóa của entry
            content_lower = entry.content.lower()
            entry_keywords_lower = [k.lower() for k in entry.keywords]

            if any(
                keyword in content_lower or keyword in entry_keywords_lower
                for keyword in keywords_lower
            ):
                matching_entries.append(entry)

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
                "most_common_keywords": [],
            }

        user_memory = self.memories[user_id]

        # Thống kê theo danh mục
        categories = {}
        total_importance = 0
        all_keywords = []

        for entry in user_memory:
            # Thống kê danh mục
            cat = entry.category.value
            categories[cat] = categories.get(cat, 0) + 1

            # Tổng mức độ quan trọng
            total_importance += entry.importance_score

            # Thu thập từ khóa
            all_keywords.extend(entry.keywords)

        # Tính trung bình mức độ quan trọng
        avg_importance = total_importance / len(user_memory) if user_memory else 0.0

        # Lấy từ khóa phổ biến nhất
        from collections import Counter

        keyword_counts = Counter(all_keywords)
        most_common_keywords = [item[0] for item in keyword_counts.most_common(5)]

        return {
            "total_messages": len(user_memory),
            "categories": categories,
            "avg_importance": round(avg_importance, 2),
            "most_common_keywords": most_common_keywords,
        }

    def clear_memory(self, user_id: str):
        """
        Xóa toàn bộ working memory của người dùng
        """
        if user_id in self.memories:
            del self.memories[user_id]
            logger.info(f"🗑️ Cleared working memory for {user_id}")
