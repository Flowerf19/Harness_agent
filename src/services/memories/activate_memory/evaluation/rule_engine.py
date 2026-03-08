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
        # Biên dịch Regex 1 lần duy nhất lúc khởi động để tối ưu tốc độ
        # Bộ Regex Tiếng Việt sử dụng Kỹ thuật Loại trừ (Negative Lookahead)
        self.fact_patterns = [
            # 1. BẮT TÊN/ĐỊNH DANH
            # Giải thích: Phải có chữ "tôi/tớ..." + "tên là/là" + KHÔNG ĐƯỢC chứa các chữ (cái|con|người|kẻ|đứa|nhân vật|bạn|thằng) ngay sau đó.
            r"(?i)\b(tôi|tớ|mình|em|anh|chị|cháu|tao)\s+(tên là|là|được gọi là)\s+(?!cái|con|người|kẻ|đứa|nhân vật|bạn|thằng)[\w\s]{2,30}$",
            # 2. BẮT TUỔI/NĂM SINH
            r"(?i)\b(tôi|tớ|mình|em|anh|chị|cháu|tao)\s+(năm nay\s+)?(\d{1,2}\s+tuổi|sinh năm\s+\d{4})\b",
            # 3. BẮT NƠI SỐNG/QUÊ QUÁN
            r"(?i)\b(tôi|tớ|mình|em|anh|chị)\s+(đang sống ở|sống ở|ở|quê ở|đến từ)\s+[\w\s]{2,30}\b",
            # 4. BẮT NGHỀ NGHIỆP/HỌC VẤN
            r"(?i)\b(tôi|tớ|mình|em|anh|chị)\s+(làm nghề|đang làm vị trí|là sinh viên|học trường|đang học ngành)\s+[\w\s]{2,40}\b",
            # 5. BẮT SỞ THÍCH/RÀNG BUỘC (Cảm xúc mạnh)
            r"(?i)\b(tôi|tớ|mình|em|anh|chị)\s+(rất thích|cực kỳ thích|đam mê|ghét|cực kỳ ghét|dị ứng với|không ăn được)\s+[\w\s]{2,40}\b",
        ]

        self.compiled_facts = [re.compile(p) for p in self.fact_patterns]

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

        # Tầng 3: Kiểm tra Fact patterns
        for pattern in self.compiled_facts:
            if pattern.search(clean_content):
                return RuleResult(
                    matched=True,
                    score=0.85,  # Điểm cao cho fact
                    category=MessageCategory.FACT,
                    stop_processing=False,  # Vẫn cho qua Semantic để confirm
                )

        # Mặc định: Không match rule nào, tiếp tục sang Semantic
        return RuleResult(
            matched=False,
            score=0.2,
            category=MessageCategory.GENERAL,
            stop_processing=False,
        )
