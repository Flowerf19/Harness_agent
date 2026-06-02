"""T2 consolidator — hot path Pass 1 orchestrator.

Pulls T1 entries, calls Extractor (1 LLM), resolves topics, embeds + writes
T2 memories, auto-promotes to T3 when eligible. Never raises.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Literal

from twin.shared.memory.active.service import ActiveMemory
from twin.shared.memory.timeline.constants import (
    MAX_CATALOGS_PER_MEMORY,
    T3_PROMOTE_MIN_CONFIDENCE,
    T3_PROMOTE_MIN_IMPORTANCE,
)
from twin.shared.memory.timeline.extractor import CandidateMemory, Extractor
from twin.shared.memory.timeline.models import (
    CATALOG_TO_T3,
    T2Memory,
    T2Topic,
    T3_PROMOTABLE,
)
from twin.shared.memory.timeline.store import TimelineStore
from twin.shared.memory.timeline.topic_resolver import TopicResolver


ProfileReader = Callable[[str], Awaitable[str] | str]
ProfileAppender = Callable[[str, str, str, str], Awaitable[None]]
CleanupScheduler = Callable[[str], Awaitable[None] | None]


@dataclass
class ConsolidationResult:
    status: Literal["ok", "skipped", "failed"]
    scope: str | None = None
    scope_id: str | None = None
    summarized_entry_ids: list[str] = field(default_factory=list)
    memory_ids: list[str] = field(default_factory=list)
    topic_ids: list[str] = field(default_factory=list)
    promoted_to_t3: list[dict] = field(default_factory=list)
    primary_catalog: str | None = None
    primary_confidence: float = 0.0
    error: str | None = None


def _format_transcript(entries) -> str:
    lines: list[str] = []
    for e in entries:
        if e.role == "assistant":
            label = "Bot"
        else:
            label = e.author_name or e.author_id or e.role
        lines.append(f"{label}: {e.content}")
    return "\n".join(lines)


async def _maybe_await(value):
    if asyncio.iscoroutine(value) or isinstance(value, asyncio.Future):
        return await value
    return value


class Consolidator:
    """Orchestrate Pass 1: T1 transcript → atomic T2 memories + T3 promotions."""

    def __init__(
        self,
        *,
        active: ActiveMemory,
        store: TimelineStore,
        resolver: TopicResolver,
        extractor: Extractor,
        embedder,
        profile_reader: ProfileReader | None = None,
        profile_appender: ProfileAppender | None = None,
        cleanup_scheduler: CleanupScheduler | None = None,
    ) -> None:
        self.active = active
        self.store = store
        self.resolver = resolver
        self.extractor = extractor
        self.embedder = embedder
        self.profile_reader = profile_reader
        self.profile_appender = profile_appender
        self.cleanup_scheduler = cleanup_scheduler
        self.logger = logging.getLogger(__name__)

    async def consolidate(
        self,
        *,
        scope: str,
        scope_id: str,
        user_id: str | None = None,
    ) -> ConsolidationResult:
        """Hot path Pass 1. Sync, never raises.

        ``user`` scope: every memory belongs to the single ``user_id``.
        ``channel`` scope: one extraction over the whole transcript; each memory
        is routed to the participant it is ABOUT (its ``subject``), so facts
        about one person never land in another's profile.
        """
        if scope == "user":
            user_id = user_id or scope_id
            if not user_id:
                self.logger.warning(
                    "T2:consolidator: user_id required for scope=%s/%s",
                    scope, scope_id,
                )
                return ConsolidationResult(
                    status="failed", scope=scope, scope_id=scope_id,
                    error="user_id required",
                )

        result = ConsolidationResult(
            status="failed", scope=scope, scope_id=scope_id,
        )

        try:
            entries = await self.active.get_context(scope, scope_id, limit=200)
            if not entries:
                self.logger.info(
                    "T2:consolidator: no entries scope=%s/%s — skipped",
                    scope, scope_id,
                )
                result.status = "skipped"
                return result

            transcript = _format_transcript(entries)

            participants_map = {
                e.author_id: (e.author_name or e.author_id)
                for e in entries
                if e.role != "assistant" and e.author_id
            }
            bot_name = next(
                (e.author_name for e in entries
                 if e.role == "assistant" and e.author_name),
                None,
            )

            # Per-user hints (T3 profile + topic glossary) only make sense for a
            # single-user scope; a channel mixes several subjects.
            t3_snap = ""
            topic_glossary = []
            if scope == "user":
                if self.profile_reader is not None:
                    try:
                        t3_snap = await _maybe_await(self.profile_reader(user_id)) or ""
                    except Exception as exc:
                        self.logger.warning(
                            "T2:consolidator: profile_reader failed: %s", exc,
                        )
                        t3_snap = ""
                try:
                    topic_glossary = await self.store.recent_topics(user_id, k=20)
                except Exception as exc:
                    self.logger.debug(
                        "T2:consolidator: recent_topics failed: %s", exc,
                    )
                    topic_glossary = []

            extract_result = await self.extractor.extract(
                transcript,
                t3_snapshot=t3_snap,
                topic_glossary=topic_glossary,
                participants=participants_map,
                bot_name=bot_name,
            )
            result.primary_catalog = extract_result.primary_catalog
            result.primary_confidence = extract_result.primary_confidence

            summarized_ids = [e.entry_id for e in entries]

            # Route each memory to the participant it is ABOUT. Drop memories
            # about the bot or whose subject matches no participant.
            name_to_id = {
                (name or "").strip().lower(): author_id
                for author_id, name in participants_map.items()
            }
            bot_key = (bot_name or "").strip().lower()
            routed: list[tuple[str, CandidateMemory]] = []
            for cand in extract_result.memories:
                target_id = self._route_subject(
                    scope, user_id, cand, name_to_id, bot_key
                )
                if target_id is None:
                    self.logger.info(
                        "T2:consolidator: drop memory subject=%r (bot/unmatched) "
                        "scope=%s/%s", cand.subject, scope, scope_id,
                    )
                    continue
                routed.append((target_id, cand))

            if not routed:
                self.logger.info(
                    "T2:consolidator: 0 routable candidates scope=%s/%s — skipped "
                    "(flush T1)", scope, scope_id,
                )
                result.status = "skipped"
                result.summarized_entry_ids = summarized_ids
                return result

            for target_id, cand in routed:
                await self._process_candidate(target_id, cand, result)

            result.summarized_entry_ids = summarized_ids
            result.status = "ok"
            self.logger.info(
                "T2:consolidator: ok scope=%s/%s memories=%d topics=%d promoted=%d",
                scope, scope_id,
                len(result.memory_ids), len(result.topic_ids),
                len(result.promoted_to_t3),
            )

            if self.cleanup_scheduler is not None:
                for target_id in {tid for tid, _ in routed}:
                    try:
                        sched = self.cleanup_scheduler(target_id)
                        if asyncio.iscoroutine(sched):
                            # Fire-and-forget — don't await.
                            asyncio.create_task(sched)
                    except Exception as exc:
                        self.logger.warning(
                            "T2:consolidator: cleanup_scheduler failed: %s", exc,
                        )

            return result

        except Exception as exc:
            self.logger.error(
                "T2:consolidator: failed scope=%s/%s: %s",
                scope, scope_id, exc, exc_info=True,
            )
            result.status = "failed"
            result.error = str(exc)
            return result

    @staticmethod
    def _route_subject(
        scope: str,
        user_id: str | None,
        cand: CandidateMemory,
        name_to_id: dict[str, str],
        bot_key: str,
    ) -> str | None:
        """Return the user_id a memory belongs to, or None to drop it.

        ``user`` scope → always the single user. ``channel`` scope → the
        participant whose display name matches ``cand.subject``; None for the
        bot or an unknown subject (prevents cross-profile contamination).
        """
        if scope == "user":
            return user_id
        subject = (cand.subject or "").strip().lower()
        if not subject or subject == bot_key:
            return None
        return name_to_id.get(subject)

    async def _process_candidate(
        self,
        user_id: str,
        cand: CandidateMemory,
        result: ConsolidationResult,
    ) -> None:
        # Resolve topics in parallel.
        topic_names = cand.topic_names or []
        if topic_names:
            resolved: list[T2Topic] = await asyncio.gather(
                *[
                    self.resolver.resolve(
                        user_id, name,
                        catalogs=cand.catalogs,
                        content_hint=cand.content,
                        importance=cand.importance,
                    )
                    for name in topic_names
                ]
            )
        else:
            resolved = []

        # Embed content.
        try:
            embedding = await self.embedder.get_embedding(cand.content)
        except Exception as exc:
            self.logger.warning(
                "T2:consolidator: embed failed: %s", exc,
            )
            embedding = []

        catalogs = (cand.catalogs or [])[:MAX_CATALOGS_PER_MEMORY]

        memory = T2Memory(
            user_id=user_id,
            content=cand.content,
            embedding=embedding or [],
            topic_ids=[t.topic_id for t in resolved],
            catalogs=catalogs,
            speaker=cand.speaker,
            importance=cand.importance,
            confidence=cand.confidence,
            source_msg_ids=cand.source_msg_ids,
            change_type=cand.change_type_hint,
        )
        await self.store.upsert_memory(memory)
        result.memory_ids.append(memory.memory_id)

        # Update topics: bump member count + union catalogs.
        for topic in resolved:
            try:
                topic.memory_count += 1
                merged_cats = list(topic.catalogs)
                for c in catalogs:
                    if c not in merged_cats:
                        merged_cats.append(c)
                topic.catalogs = merged_cats[:4]
                await self.store.upsert_topic(topic)
            except Exception as exc:
                self.logger.debug(
                    "T2:consolidator: topic update failed %s: %s",
                    topic.topic_id, exc,
                )
            if topic.topic_id not in result.topic_ids:
                result.topic_ids.append(topic.topic_id)

        # T3 promotion.
        if (
            self.profile_appender is not None
            and cand.importance >= T3_PROMOTE_MIN_IMPORTANCE
            and cand.confidence >= T3_PROMOTE_MIN_CONFIDENCE
        ):
            for cat in catalogs:
                if cat not in T3_PROMOTABLE:
                    continue
                section = CATALOG_TO_T3[cat]
                try:
                    await _maybe_await(
                        self.profile_appender(
                            user_id, section, cand.content, memory.memory_id,
                        )
                    )
                    result.promoted_to_t3.append(
                        {
                            "section": section,
                            "content": cand.content,
                            "memory_id": memory.memory_id,
                        }
                    )
                except Exception as exc:
                    self.logger.warning(
                        "T2:consolidator: T3 append failed section=%s: %s",
                        section, exc,
                    )
