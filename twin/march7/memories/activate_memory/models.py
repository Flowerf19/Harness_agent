# src/services/memories/activate_memory/models.py
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def get_utc_now() -> datetime:
    """Trả về thời gian UTC chuẩn có chứa thông tin múi giờ."""
    return datetime.now(timezone.utc)


class MemoryEntry(BaseModel):
    """T1 Active Memory entry stored in Redis."""

    scope: Literal["user", "channel"] = "user"
    scope_id: str | None = None

    user_id: str = Field(...)
    role: str = Field(...)

    author_id: str | None = None
    author_name: str | None = None
    guild_id: str | None = None
    channel_id: str | None = None
    message_id: str | None = None
    reply_to: str | None = None

    content: str = Field(...)
    tokens: int = Field(...)

    # Auto-generated fields
    timestamp: datetime = Field(default_factory=get_utc_now)
    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    def model_post_init(self, __context) -> None:
        if self.scope_id is None:
            self.scope_id = self.channel_id if self.scope == "channel" else self.user_id
        if self.author_id is None:
            self.author_id = self.user_id


class SummaryState(BaseModel):
    scope: Literal["user", "channel"]
    scope_id: str
    last_activity_at: datetime = Field(default_factory=get_utc_now)
    last_summarized_at: datetime | None = None
    last_summarized_entry_id: str | None = None
    unsummarized_message_count: int = 0
    unsummarized_token_count: int = 0
    summary_in_progress: bool = False
    locked_until: datetime | None = None
    retry_count: int = 0
