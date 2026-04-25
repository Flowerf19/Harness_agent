# src/services/memories/activate_memory/models.py
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


def get_utc_now() -> datetime:
    """Trả về thời gian UTC chuẩn có chứa thông tin múi giờ."""
    return datetime.now(timezone.utc)


class MemoryEntry(BaseModel):
    """T1 Active Memory entry stored in Redis."""

    user_id: str = Field(...)
    role: str = Field(...)
    content: str = Field(...)
    tokens: int = Field(...)

    # Auto-generated fields
    timestamp: datetime = Field(default_factory=get_utc_now)
    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
