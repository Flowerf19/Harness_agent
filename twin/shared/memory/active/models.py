"""T1 active memory models."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ActiveEntry(BaseModel):
    """A single message stored in T1 active memory."""

    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scope: Literal["user", "channel"]
    scope_id: str
    role: Literal["user", "assistant", "system"]
    author_id: str | None = None
    author_name: str | None = None
    message_id: str | None = None
    guild_id: str | None = None
    channel_id: str | None = None
    reply_to: str | None = None
    content: str
    tokens: int = 0
    created_at: datetime = Field(default_factory=_utcnow)
    catalog: str | None = None
    catalog_confidence: float | None = None
