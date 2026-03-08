import logging
import re
from dataclasses import dataclass
from typing import Optional

from Arize_Phoenix_tool_kit import track_general_step

from ..models import MessageCategory

logger = logging.getLogger(__name__)


@dataclass
class RuleResult:
    """Cấu trúc dữ liệu trả về từ Rule Engine"""

    matched: bool
    score: float
    category: MessageCategory
    stop_processing: bool  # Nếu True: Bỏ qua hoàn toàn AI (Qwen)
    extracted_content: Optional[str] = None  # Dùng để tách nội dung khi dùng lệnh !note


class RuleEngine:
    """
    Bộ lọc Luật cứng (Hard Rules).
    Hoạt động như một cái phễu, chạy cực nhanh bằng Regex trước khi đưa cho AI.
    """

    def __init__(self):
        # Biên dịch Regex 1 lần duy nhất lúc khởi động để tối ưu tốc độ (Microseconds)

        # 1. Regex cho Rác: Chỉ chứa ký tự đặc biệt, emoji, không có chữ/số
        self.noise_regex = re.compile(r"^[\W_]+$")

        # 2. Regex cho Bảo mật:
        # - JWT Tokens (thường bắt đầu bằng eyJ...)
        self.jwt_regex = re.compile(
            r"eyJ[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+\.[a-zA-Z0-9-_]+"
        )
        # - Căn cước công dân VN (12 số, bắt đầu bằng số 0)
        self.cccd_regex = re.compile(r"\b0\d{11}\b")

        # 3. Regex cho Lệnh ép buộc (Explicit Command):
        # Bắt đầu bằng !note hoặc /nhớ, theo sau là khoảng trắng và nội dung. (Không phân biệt hoa/thường)
        self.cmd_regex = re.compile(r"^[!/](note|nhớ)\s+(.+)", re.IGNORECASE)

    def _check_noise(self, text: str) -> RuleResult:
        """Lọc tin nhắn quá ngắn hoặc vô nghĩa."""
        if len(text.strip()) <= 3 or self.noise_regex.match(text):
            return RuleResult(
                matched=True,
                score=0.1,
                category=MessageCategory.GENERAL,
                stop_processing=True,
            )
        return RuleResult(
            matched=False,
            score=0.0,
            category=MessageCategory.GENERAL,
            stop_processing=False,
        )

    def _check_security(self, text: str) -> RuleResult:
        """Bảo vệ dữ liệu nhạy cảm không bị đưa vào AI hoặc lưu trữ lộ liễu."""
        if self.jwt_regex.search(text) or self.cccd_regex.search(text):
            logger.warning("🚨 RuleEngine: Phát hiện dữ liệu có cấu trúc nhạy cảm!")
            return RuleResult(
                matched=True,
                score=1.0,
                category=MessageCategory.SENSITIVE,
                stop_processing=True,
            )
        return RuleResult(
            matched=False,
            score=0.0,
            category=MessageCategory.GENERAL,
            stop_processing=False,
        )

    def _check_explicit_command(self, text: str) -> RuleResult:
        """Xử lý cú pháp bắt buộc bot phải nhớ (Bypass AI)."""
        match = self.cmd_regex.match(text)
        if match:
            # Tách lấy phần nội dung thực sự (bỏ chữ !note đi)
            content = match.group(2).strip()
            return RuleResult(
                matched=True,
                score=1.0,
                category=MessageCategory.EXPLICIT_COMMAND,
                stop_processing=True,
                extracted_content=content,
            )
        return RuleResult(
            matched=False,
            score=0.0,
            category=MessageCategory.GENERAL,
            stop_processing=False,
        )

    def _check_question(self, text: str) -> RuleResult:
        """Xác định ngữ pháp câu hỏi để cung cấp Base Score cho Qwen."""
        text_lower = text.lower()
        if "?" in text or text_lower.startswith(
            ("tại sao", "làm sao", "làm thế nào", "ai")
        ):
            # LƯU Ý: stop_processing = False. Nó vẫn sẽ đi qua Qwen để xem nội dung câu hỏi là gì!
            return RuleResult(
                matched=True,
                score=0.6,
                category=MessageCategory.QUERY,
                stop_processing=False,
            )
        return RuleResult(
            matched=False,
            score=0.2,
            category=MessageCategory.GENERAL,
            stop_processing=False,
        )

    @track_general_step(
        step_name="T1_Rule_Engine_Evaluation", tags=["tier_1", "rule_engine"]
    )
    def evaluate(self, text: str) -> RuleResult:
        """
        Chạy dữ liệu qua phễu. Lớp nào có quyền `stop_processing=True` sẽ lập tức trả về (Return early).
        """
        # Tầng 1: Chặn rác
        noise_res = self._check_noise(text)
        if noise_res.stop_processing:
            return noise_res

        # Tầng 2: Chặn dữ liệu nhạy cảm
        sec_res = self._check_security(text)
        if sec_res.stop_processing:
            return sec_res

        # Tầng 3: Bắt lệnh trực tiếp (!note)
        cmd_res = self._check_explicit_command(text)
        if cmd_res.stop_processing:
            return cmd_res

        # Tầng 4: Lấy ngữ pháp cơ bản (Không chặn, mặc định đi tiếp)
        return self._check_question(text)
