# src/services/memories/activate_memory/models.py
import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class MessageCategory(str, Enum):
    GENERAL = "general"
    FACT = "fact"
    GOAL = "goal"
    PREFERENCE = "preference"
    RELATIONSHIP = "relationship"
    QUERY = "query"
    SENSITIVE = "sensitive"
    EXPLICIT_COMMAND = "explicit_cmd"


def get_utc_now() -> datetime:
    """Trả về thời gian UTC chuẩn có chứa thông tin múi giờ."""
    return datetime.now(timezone.utc)


class MemoryEntry(BaseModel):
    # Field(...) bắt buộc phải có khi tạo object
    user_id: str = Field(...)
    role: str = Field(...)
    content: str = Field(...)
    tokens: int = Field(...)

    # Các giá trị có mặc định
    importance_score: float = Field(default=0.0, ge=0.0, le=1.0)  # Ép chuẩn từ 0 đến 1
    category: MessageCategory = Field(default=MessageCategory.GENERAL)

    # Tự động sinh id và timestamp
    timestamp: datetime = Field(default_factory=get_utc_now)
    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # (Pydantic đã tự có sẵn hàm .model_dump() và .model_validate() cực mạnh)
    # Không cần viết hàm to_dict() thủ công nữa!
