import logging
from typing import Optional, Tuple

from langsmith import traceable

from ..models import MessageCategory

logger = logging.getLogger(__name__)


class EvaluationPipeline:
    """
    Trạm kiểm soát T1 - Chỉ dùng Rule-based evaluation (không dùng embedding).
    FACT detection được chuyển sang T2/T3 xử lý bởi LLM trong quá trình consolidation.
    """

    def __init__(self, rule_engine):
        self.rule_engine = rule_engine

    @traceable(
        name="T1_Evaluation_Pipeline",
        run_type="chain",
        tags=["tier_1", "pipeline", "evaluation"],
    )
    async def evaluate_message(
        self, text: str, role: str
    ) -> Tuple[float, MessageCategory, Optional[str]]:
        """
        Đánh giá tin nhắn chỉ dùng RuleEngine (nhanh, regex-based).
        Không gọi embedding API - tối ưu hiệu suất T1.

        Args:
            text: Nội dung tin nhắn
            role: Vai trò người gửi ('user' hoặc 'assistant')

        Returns:
            Tuple[float, MessageCategory, Optional[str]]: 
                (Điểm_số, Danh_mục, Nội_dung_trích_xuất_nếu_có)
        """
        rule_result = self.rule_engine.evaluate(text)

        if rule_result.stop_processing:
            logger.debug(
                f"🛑 Pipeline: Dừng sớm tại RuleEngine (Category: {rule_result.category.value})"
            )

        return (
            rule_result.score,
            rule_result.category,
            rule_result.extracted_content,
        )