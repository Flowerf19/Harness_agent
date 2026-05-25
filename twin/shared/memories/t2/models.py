"""T2 memory models stored in Redis Stack."""
from __future__ import annotations

import hashlib
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_topic_id(user_id: str, topic: str) -> str:
    namespace = hashlib.md5(user_id.encode()).hexdigest()
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{namespace}:{topic.lower()}"))


def get_ttl_by_importance(importance: int) -> int:
    return {5: 90, 4: 60, 3: 30, 2: 14, 1: 7}.get(importance, 30)


def expires_at_for_importance(importance: int, now: datetime | None = None) -> datetime:
    base = now or utc_now()
    return base + timedelta(days=get_ttl_by_importance(importance))


class T2Fact(BaseModel):
    fact_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    topic_id: str
    claim: str
    status: Literal["active", "superseded"] = "active"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    importance: int = Field(default=3, ge=1, le=5)
    introduced_at_chunk_id: str | None = None
    supersedes_fact_id: str | None = None
    superseded_by_fact_id: str | None = None
    superseded_at_chunk_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None


class T2Chunk(BaseModel):
    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    topic_id: str
    content: str
    event_date: datetime = Field(default_factory=utc_now)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    importance: int = Field(default=3, ge=1, le=5)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    previous_chunk_id: str | None = None
    next_chunk_id: str | None = None
    related_chunk_ids: list[str] = Field(default_factory=list)
    introduced_fact_ids: list[str] = Field(default_factory=list)
    updated_fact_ids: list[str] = Field(default_factory=list)
    superseded_fact_ids: list[str] = Field(default_factory=list)
    decision_changes: dict[str, Any] = Field(default_factory=dict)
    source_message_ids: list[str] = Field(default_factory=list)
    embedding: list[float] | None = None
    expires_at: datetime | None = None


class T2Page(BaseModel):
    page_id: str
    user_id: str
    scope: str = "user_global"
    topic_id: str
    canonical_topic: str
    topic_aliases: list[str] = Field(default_factory=list)
    category: str = "casual"
    current_summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    participants: list[str] = Field(default_factory=list)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    active_fact_ids: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    resolution_status: str = "open"
    user_sentiment: str = "neutral"
    importance: int = Field(default=3, ge=1, le=5)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    last_accessed: datetime = Field(default_factory=utc_now)
    access_count: int = 0
    latest_chunk_id: str | None = None
    ttl_days: int = 30
    expires_at: datetime | None = None
    history_log: list[str] = Field(default_factory=list)
    summary_embedding: list[float] | None = None
    latest_chunk_embedding: list[float] | None = None

    @property
    def embedding(self) -> list[float] | None:
        return self.summary_embedding

    @embedding.setter
    def embedding(self, value: list[float] | None) -> None:
        self.summary_embedding = value


def calculate_relevance(page: T2Page, now: datetime) -> float:
    if page.ttl_days <= 0:
        return 0.0
    access_boost = min(1.0 + 0.1 * page.access_count, 1.5)
    effective_ttl = page.ttl_days * access_boost
    age_days = (now - page.last_accessed).total_seconds() / 86400.0
    return math.exp(-age_days / effective_ttl)
