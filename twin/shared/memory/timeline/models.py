"""T2 timeline models: T2Memory + catalog enums and helpers."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from twin.shared.memory.timeline.constants import (
    MAX_CATALOGS_PER_MEMORY,
    TTL_BY_IMPORTANCE,
)

CATALOGS = [
    "identity", "contact", "relationship", "work",
    "interest", "habit", "psychological", "rules",
    "decision", "event", "emotion", "discussion",
]

CATALOG_SET = set(CATALOGS)

T3_PROMOTABLE = {
    "identity", "contact", "relationship", "work",
    "interest", "habit", "psychological", "rules",
}

CATALOG_TO_T3 = {
    "identity": "basic",
    "contact": "contact",
    "relationship": "relationship",
    "work": "work",
    "interest": "interest",
    "habit": "habit",
    "psychological": "psychological",
    "rules": "rules",
}




def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


def get_ttl_by_importance(importance: int) -> int:
    return TTL_BY_IMPORTANCE.get(importance, TTL_BY_IMPORTANCE[3])


def expires_at_for_importance(
    importance: int, now: datetime | None = None
) -> datetime:
    base = now or utc_now()
    return base + timedelta(days=get_ttl_by_importance(importance))





def _validate_catalogs(values: list[str], max_count: int) -> list[str]:
    if len(values) > max_count:
        raise ValueError(f"too many catalogs: {len(values)} > {max_count}")
    for cat in values:
        if cat not in CATALOG_SET:
            raise ValueError(f"invalid catalog: {cat!r}")
    return values



class T2Memory(BaseModel):
    memory_id: str = Field(default_factory=new_uuid)
    user_id: str
    content: str
    embedding: list[float] = Field(default_factory=list)

    catalogs: list[str] = Field(default_factory=list)
    speaker: Literal["user", "bot", "joint"] = "user"
    created_at: datetime = Field(default_factory=utc_now)
    importance: int = 3
    confidence: float = 1.0
    source_msg_ids: list[str] = Field(default_factory=list)
    ttl_days: int = 30
    expires_at: datetime | None = None
    last_accessed: datetime = Field(default_factory=utc_now)
    access_count: int = 0

    @model_validator(mode="after")
    def _populate_derived(self) -> "T2Memory":
        _validate_catalogs(self.catalogs, MAX_CATALOGS_PER_MEMORY)
        if self.expires_at is None:
            self.expires_at = expires_at_for_importance(
                self.importance, self.created_at
            )
        if self.ttl_days == 30 and self.importance != 3:
            self.ttl_days = get_ttl_by_importance(self.importance)
        return self
