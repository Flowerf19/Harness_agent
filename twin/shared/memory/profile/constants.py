"""Profile (T3) constants — section keys, display headers, default dir."""
from __future__ import annotations

SECTIONS: list[str] = [
    "basic", "contact", "relationship", "work",
    "interest", "habit", "psychological", "rules",
]

SECTION_HEADERS: dict[str, str] = {
    "basic":         "Thông tin cơ bản",
    "contact":       "Liên hệ",
    "relationship":  "Quan hệ",
    "work":          "Nghề nghiệp & Học vấn",
    "interest":      "Sở thích",
    "habit":         "Thói quen",
    "psychological": "Tâm lý & Cảm xúc",
    "rules":         "Ràng buộc & Cấm kỵ",
}

DEFAULT_PROFILE_DIR = "memories"

EMPTY_PLACEHOLDER = "(chưa có)"

PROFILE_HEADER = "=== HỒ SƠ NGƯỜI DÙNG ==="

PROFILE_FOOTER_HINT = (
    "(Lồng tự nhiên vào câu trả lời, KHÔNG nói "
    '"Theo hồ sơ..." hay "Lần trước bạn nói...")'
)
