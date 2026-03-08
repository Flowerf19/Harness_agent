import logging
from typing import Optional, Tuple

from langsmith import traceable

from ..models import MessageCategory

logger = logging.getLogger(__name__)


class EvaluationPipeline:
    """
    Trạm kiểm soát tổng hợp (Orchestrator).
    Nhận tin nhắn đầu vào, điều phối qua Rule Engine và Semantic Engine để ra kết quả cuối cùng.
    """

    def __init__(self, rule_engine, semantic_engine):
        self.rule_engine = rule_engine
        self.semantic_engine = semantic_engine

    @traceable(
        name="T1_Evaluation_Pipeline",
        run_type="chain",
        tags=["tier_1", "pipeline", "evaluation"],
    )
    async def evaluate_message(
        self, text: str, role: str
    ) -> Tuple[float, MessageCategory, Optional[str]]:
        """
        Đánh giá toàn diện một tin nhắn.
        Trả về: (Điểm_số, Danh_mục, Nội_dung_trích_xuất_nếu_có)
        """
        # --- BƯỚC 1: Lá chắn Luật Cứng (Chạy đồng bộ, siêu tốc) ---
        rule_result = self.rule_engine.evaluate(text)

        # Nếu Luật cứng phán quyết "Chặn" (Cụ thể: là Rác, Dữ liệu nhạy cảm, hoặc Lệnh !note)
        if rule_result.stop_processing:
            logger.debug(
                f"🛑 Pipeline: Dừng sớm tại RuleEngine (Category: {rule_result.category.value})"
            )
            return (
                rule_result.score,
                rule_result.category,
                rule_result.extracted_content,
            )

        # --- BƯỚC 2: Bộ não AI Ngữ nghĩa (Chạy bất đồng bộ) ---
        # Chỉ những tin nhắn sạch và không mang tính mệnh lệnh gắt gao mới đến được đây
        semantic_score, semantic_category = await self.semantic_engine.evaluate(
            text, role
        )

        # --- BƯỚC 3: Tổng hợp Quyết định (Conflict Resolution) ---
        final_score = rule_result.score
        final_category = rule_result.category

        # Logic Hợp nhất:
        # Nếu AI phát hiện ra ngữ nghĩa thực sự (khác GENERAL), ta tin tưởng AI.
        # Nếu AI không phát hiện ra gì, ta giữ nguyên phán quyết Base của Luật (Ví dụ: nó là 1 câu hỏi QUERY).
        if semantic_category != MessageCategory.GENERAL:
            final_category = semantic_category
            final_score = semantic_score
        else:
            # Ngay cả khi AI bảo là GENERAL, nhưng nếu điểm Cosine vẫn cao hơn điểm Base của Luật,
            # ta vẫn lấy điểm cao hơn để tránh tin nhắn bị xóa oan khi dọn dẹp RAM.
            final_score = max(semantic_score, rule_result.score)

        return min(final_score, 1.0), final_category, rule_result.extracted_content
