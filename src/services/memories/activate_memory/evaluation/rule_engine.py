import re
from dataclasses import dataclass
from typing import Optional

from ..models import MessageCategory


@dataclass
class RuleResult:
    """Cấu trúc dữ liệu trả về từ Rule Engine"""

    matched: bool
    score: float
    category: MessageCategory
    stop_processing: bool
    extracted_content: Optional[str] = None


class RuleEngine:
    """
    Bộ lọc Luật cứng (Hard Rules).
    Hoạt động như một cái phễu, chạy cực nhanh bằng Regex trước khi đưa cho AI.
    """

    def __init__(self):
        # Regex cho Noise
        self.noise_regex = re.compile(r"^[\W_]+$")

        # Regex cho lệnh ép buộc (!note, /nhớ)
        self.cmd_regex = re.compile(r"^[!/](note|nhớ)\s+(.+)", re.IGNORECASE)

    def evaluate(self, content: str) -> RuleResult:
        """Đánh giá cực nhanh bằng Regex trước khi qua Semantic Engine."""
        # Chuẩn hóa khoảng trắng dư thừa
        clean_content = " ".join(content.split())

        # Tầng 1: Chặn rác (quá ngắn hoặc chỉ chứa ký tự đặc biệt)
        if len(clean_content.strip()) <= 3 or self.noise_regex.match(clean_content):
            return RuleResult(
                matched=True,
                score=0.1,
                category=MessageCategory.GENERAL,
                stop_processing=True,
            )

        # Tầng 2: Bắt lệnh trực tiếp (!note, /nhớ)
        cmd_match = self.cmd_regex.match(clean_content)
        if cmd_match:
            return RuleResult(
                matched=True,
                score=1.0,
                category=MessageCategory.EXPLICIT_COMMAND,
                stop_processing=True,
                extracted_content=cmd_match.group(2).strip(),
            )

        # Mặc định: Không match rule nào, tiếp tục sang Semantic
        return RuleResult(
            matched=False,
            score=0.2,
            category=MessageCategory.GENERAL,
            stop_processing=False,
        )
