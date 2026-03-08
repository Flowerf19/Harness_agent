import logging
import math
from typing import Dict, List, Tuple

from langsmith import traceable

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

    def __init__(self, embedding_service=None):
        """
        :param embedding_service: Wrapper service (VD: QwenService) có chứa hàm .get_embedding(text)
        """
        self.embedding_service = embedding_service
        self._anchor_vectors: Dict[MessageCategory, List[float]] = {}
        self._fact_anchor_vectors: List[List[float]] = []
        self._is_initialized = False

        # 16 anchor tiếng Việt cho việc phát hiện FACT
        self.fact_anchors = [
            # --- NHÓM 1: ĐỊNH DANH & NHÂN KHẨU HỌC ---
            "Tôi tên là, biệt danh của tôi là, mọi người hay gọi tôi là.",
            "Năm nay tôi nhiêu tuổi, tôi sinh năm, ngày tháng năm sinh của tôi.",
            "Quê tôi ở, tôi sinh ra ở, hiện tại tôi đang sống và làm việc tại.",
            "Thông tin cá nhân cơ bản, giới thiệu bản thân, tên tuổi quê quán.",
            # --- NHÓM 2: NGHỀ NGHIỆP & HỌC VẤN ---
            "Tôi làm nghề, công việc hiện tại của tôi là, chuyên môn của tôi là.",
            "Tôi là sinh viên trường, tôi đang học ngành, tôi vừa mới tốt nghiệp.",
            "Thông tin về nghề nghiệp, chức vụ, trường học, tình trạng công việc.",
            # --- NHÓM 3: SỞ THÍCH & ĐAM MÊ ---
            "Tôi rất thích, đam mê của tôi là, sở thích cá nhân, tôi hay dành thời gian để.",
            "Món ăn yêu thích của tôi, thể loại nhạc tôi hay nghe, tựa game tôi thường chơi.",
            "Phong cách của tôi, thói quen sinh hoạt hàng ngày của tôi là.",
            # --- NHÓM 4: RÀNG BUỘC & CẤM KỴ (RẤT QUAN TRỌNG) ---
            "Tôi cực kỳ ghét, tôi không thích, tôi không chịu được, tôi dị ứng với.",
            "Sức khỏe của tôi, bệnh lý của tôi là, tôi không ăn được món.",
            "Những điều cấm kỵ, nhược điểm cá nhân, thói quen xấu cần tránh.",
            # --- NHÓM 5: MỐI QUAN HỆ & GIA ĐÌNH ---
            "Tôi đã có người yêu, tôi đang độc thân, tình trạng hôn nhân của tôi.",
            "Gia đình tôi có, bố mẹ tôi, con cái của tôi, bạn thân của tôi là.",
            "Tôi có nuôi một chú chó, tôi có nuôi mèo, thú cưng của tôi tên là.",
            # --- NHÓM 6: DỰ ĐỊNH & KẾ HOẠCH TƯƠNG LAI ---
            "Tôi dự định sắp tới sẽ, mục tiêu của tôi là, kế hoạch năm nay tôi muốn.",
            "Tôi đang ấp ủ dự án, tôi chuẩn bị đi du lịch ở.",
        ]

    async def initialize(self):
        """Khởi tạo embedding cho các fact anchors."""
        if self._is_initialized:
            return

        if not self.embedding_service:
            logger.warning(
                "⚠️ SemanticEngine: Không có embedding_service, bỏ qua khởi tạo"
            )
            return

        logger.info("🧠 SemanticEngine: Đang khởi tạo các Fact Anchor Vectors...")
        try:
            # Nhúng các fact anchors
            for anchor in self.fact_anchors:
                vector = await self.embedding_service.get_embedding(anchor)
                self._fact_anchor_vectors.append(vector)

            # Vẫn giữ category anchors cho backward compatibility
            for category, prompt in CATEGORY_ANCHOR_PROMPTS.items():
                vector = await self.embedding_service.get_embedding(prompt)
                self._anchor_vectors[category] = vector

            self._is_initialized = True
            logger.info(
                f"✅ SemanticEngine: Khởi tạo {len(self._fact_anchor_vectors)} Fact Anchor Vectors thành công!"
            )
        except Exception as e:
            logger.error(f"❌ SemanticEngine: Lỗi khi khởi tạo Anchor Vectors: {e}")
            self._is_initialized = False

    async def close(self):
        """Đóng kết nối."""
        pass

    @traceable(
        name="T1_Qwen_Embedding_Scoring",
        run_type="chain",
        tags=["tier_1", "semantic", "qwen"],
    )
    async def evaluate(
        self, text: str, role: str = "user"
    ) -> Tuple[float, MessageCategory]:
        """
        Nhúng tin nhắn và so sánh với các mỏ neo.
        Trả về (Final_Score, Category)
        """
        await self.initialize()

        # Fallback an toàn nếu API nhúng đang chết
        if not self._is_initialized or not self._fact_anchor_vectors:
            return 0.0, MessageCategory.GENERAL

        try:
            # 1. Nhúng câu nói của User thành Vector
            msg_vector = await self.embedding_service.get_embedding(text)

            max_similarity = 0.0
            best_category = MessageCategory.GENERAL

            # 2. So sánh với các Fact Anchors
            similarities = []
            for anchor_vec in self._fact_anchor_vectors:
                sim = cosine_similarity(msg_vector, anchor_vec)
                similarities.append(sim)

            # Lấy similarity cao nhất từ fact anchors
            if similarities:
                max_similarity = max(similarities)
                if max_similarity >= SEMANTIC_ACTIVATION_THRESHOLD:
                    best_category = MessageCategory.FACT

            # 3. So sánh với category anchors (backward compatibility)
            for category, anchor_vec in self._anchor_vectors.items():
                sim = cosine_similarity(msg_vector, anchor_vec)
                if sim > max_similarity:
                    max_similarity = sim
                    if sim >= SEMANTIC_ACTIVATION_THRESHOLD:
                        best_category = category

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
