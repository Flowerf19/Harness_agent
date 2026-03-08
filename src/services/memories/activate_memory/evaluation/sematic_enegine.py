import logging
import math
from typing import Dict, List, Optional, Tuple

from Arize_Phoenix_tool_kit import track_general_step

from ..constants import SEMANTIC_ACTIVATION_THRESHOLD
from ..models import MessageCategory

logger = logging.getLogger(__name__)

# Khai báo các câu Prompt định nghĩa (Mỏ neo) cho từng Category
CATEGORY_ANCHOR_PROMPTS = {
    MessageCategory.FACT: "Thông tin cá nhân khách quan: tên, tuổi, quê quán, nghề nghiệp, tình trạng sức khỏe, tài sản, sự kiện đã xảy ra.",
    MessageCategory.GOAL: "Mục tiêu tương lai: kế hoạch, dự định, ước mơ, mong muốn đạt được, những việc sẽ làm.",
    MessageCategory.PREFERENCE: "Sở thích cá nhân: những thứ yêu thích, đam mê, thói quen, món ăn ngon, hoặc những thứ ghét, dị ứng, cấm kỵ.",
    MessageCategory.RELATIONSHIP: "Mối quan hệ xã hội: gia đình, bố mẹ, anh chị em, bạn bè, đồng nghiệp, người yêu, kẻ thù.",
    MessageCategory.EXPLICIT_COMMAND: "Đây là một câu mệnh lệnh hoặc yêu cầu rõ ràng. Người dùng đang trực tiếp ra lệnh, sai khiến hệ thống hoặc bot phải ghi nhớ, lưu ý, ghi chú lại thông tin.",
}


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Tính khoảng cách Cosine giữa 2 vector. Trả về từ -1.0 đến 1.0"""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0

    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_v1 = math.sqrt(sum(a * a for a in v1))
    norm_v2 = math.sqrt(sum(b * b for b in v2))

    if norm_v1 == 0 or norm_v2 == 0:
        return 0.0

    return dot_product / (norm_v1 * norm_v2)


class SemanticEngine:
    """
    Bộ não phân tích Ngữ nghĩa bằng AI Embedding.
    Đo khoảng cách giữa câu nói của user và các định nghĩa (Anchors).
    """

    def __init__(self, embedding_service):
        """
        :param embedding_service: Wrapper service (VD: QwenService) có chứa hàm .get_embedding(text)
        """
        self.embedding_service = embedding_service
        self._anchor_vectors: Dict[MessageCategory, List[float]] = {}
        self._is_initialized = False

    async def _ensure_initialized(self):
        """Lazy loading: Chỉ gọi API nhúng các mỏ neo trong lần gọi đầu tiên."""
        if self._is_initialized:
            return

        logger.info("🧠 SemanticEngine: Đang khởi tạo các Anchor Vectors từ Qwen...")
        try:
            for category, prompt in CATEGORY_ANCHOR_PROMPTS.items():
                vector = await self.embedding_service.get_embedding(prompt)
                self._anchor_vectors[category] = vector
            self._is_initialized = True
            logger.info("✅ SemanticEngine: Khởi tạo Anchor Vectors thành công!")
        except Exception as e:
            logger.error(f"❌ SemanticEngine: Lỗi khi khởi tạo Anchor Vectors: {e}")
            # Nếu sập API nhúng, bot vẫn chạy được nhưng không có AI đánh giá
            self._is_initialized = False

    @track_general_step(
        step_name="T1_Qwen_Embedding_Scoring", tags=["tier_1", "semantic", "qwen"]
    )
    async def evaluate(self, text: str, role: str) -> Tuple[float, MessageCategory]:
        """
        Nhúng tin nhắn và so sánh với các mỏ neo.
        Trả về (Final_Score, Category)
        """
        await self._ensure_initialized()

        # Fallback an toàn nếu API nhúng đang chết
        if not self._is_initialized or not self._anchor_vectors:
            return 0.0, MessageCategory.GENERAL

        try:
            # 1. Nhúng câu nói của User thành Vector
            msg_vector = await self.embedding_service.get_embedding(text)

            max_similarity = 0.0
            best_category = MessageCategory.GENERAL

            # 2. So sánh với từng Mỏ neo
            for category, anchor_vec in self._anchor_vectors.items():
                sim = cosine_similarity(msg_vector, anchor_vec)
                if sim > max_similarity:
                    max_similarity = sim
                    best_category = category

            # 3. Áp dụng Ngưỡng Kích Hoạt (Activation Threshold)
            # Nếu điểm cao nhất vẫn thấp hơn Threshold (VD: 0.65), coi như đây là câu chat nhảm
            if max_similarity < SEMANTIC_ACTIVATION_THRESHOLD:
                best_category = MessageCategory.GENERAL

            # 4. Tính điểm cộng (Bonus Rules)
            final_score = max_similarity
            if final_score > 0:
                if role == "user":
                    final_score += (
                        0.1  # Lời user nói quan trọng hơn bot tự biên tự diễn
                    )
                if len(text) > 50:
                    final_score += 0.05  # Câu dài thường chứa nhiều bối cảnh hơn

            return min(final_score, 1.0), best_category

        except Exception as e:
            logger.error(f"❌ SemanticEngine: Lỗi quá trình nhúng tin nhắn: {e}")
            return 0.0, MessageCategory.GENERAL
