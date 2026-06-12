"""T2 topic resolver — match proposed topic name to existing T2Topic.

2-stage cascade:
  1. exact name / alias match (case-insensitive, normalized)
  2. otherwise → create new topic
"""
from __future__ import annotations

import logging
import re

from twin.shared.memory.timeline.models import T2Topic
from twin.shared.memory.timeline.store import TimelineStore

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize(name: str) -> str:
    """Lowercase, strip, collapse whitespace. Preserves diacritics."""
    return _WHITESPACE_RE.sub(" ", name.strip().lower())


class TopicResolver:
    """Resolve a proposed topic name to an existing T2Topic or create new."""

    def __init__(
        self,
        store: TimelineStore,
    ) -> None:
        self.store = store
        self.logger = logging.getLogger(__name__)

    async def resolve(
        self,
        user_id: str,
        proposed_name: str,
        *,
        catalogs: list[str] | None = None,
        content_hint: str | None = None,
        importance: int = 3,
    ) -> T2Topic:
        """2-stage cascade. Returns existing topic or newly created one."""
        normalized = _normalize(proposed_name)
        self.logger.debug(
            "T2:resolver: resolve user=%s name=%r normalized=%r",
            user_id, proposed_name, normalized,
        )

        # Stage 1 — exact name / alias match.
        existing = await self.store.find_topic_by_name_or_alias(user_id, normalized)
        if existing is not None:
            self.logger.info(
                "T2:resolver: matched via=exact user=%s topic=%s name=%r",
                user_id, existing.topic_id, existing.name,
            )
            await self._attach_alias(existing, proposed_name)
            await self.store.refresh_topic(user_id, existing.topic_id, bump_access=True)
            return existing

        # Stage 2 — create new.
        return await self._create_new(
            user_id, proposed_name, [], catalogs, importance
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _create_new(
        self,
        user_id: str,
        proposed_name: str,
        vec: list[float],
        catalogs: list[str] | None,
        importance: int,
    ) -> T2Topic:
        normalized = _normalize(proposed_name)
        aliases = [proposed_name] if proposed_name != normalized else []
        topic = T2Topic(
            user_id=user_id,
            name=normalized,
            aliases=aliases,
            catalogs=catalogs or [],
            embedding=vec or [],
            importance=importance,
        )
        await self.store.upsert_topic(topic)
        self.logger.info(
            "T2:resolver: matched via=new user=%s topic=%s name=%r",
            user_id, topic.topic_id, topic.name,
        )
        return topic

    async def _attach_alias(self, topic: T2Topic, proposed_name: str) -> None:
        """Add proposed_name as alias if not already present (case-insensitive)."""
        n = _normalize(proposed_name)
        if n == topic.name:
            return
        existing = {_normalize(a) for a in topic.aliases}
        if n in existing:
            return
        await self.store.add_topic_alias(topic.user_id, topic.topic_id, proposed_name)
        topic.aliases.append(proposed_name)
