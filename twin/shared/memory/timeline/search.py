"""T2 timeline search — composable read-paths over TimelineStore."""
from __future__ import annotations

import logging
from collections import Counter

from twin.shared.memory.timeline.constants import (
    KNN_NEIGHBOURS_FOR_PRE_FLIGHT,
    TOPIC_CASCADE_LIMIT,
)
from twin.shared.memory.timeline.models import T2Memory
from twin.shared.memory.timeline.store import TimelineStore, _escape_tag

_VALID_MODES = {
    "auto", "semantic", "current_state", "by_topic",
    "topic_timeline", "by_catalog", "change_log", "recent",
}

_REFRESH_TOPIC_CAP = 5


def format_preflight_for_prompt(memories: list[T2Memory]) -> str:
    if not memories:
        return ""
    lines = ["## Ngữ cảnh nhớ liên quan (dùng tự nhiên, không lộ nguồn)"]
    for m in memories:
        content = m.content
        if len(content) > 240:
            content = content[:240] + "…"
        if m.change_type and m.change_type != "new":
            lines.append(f"- {content} [{m.change_type}]")
        else:
            lines.append(f"- {content}")
    return "\n".join(lines)


class TimelineSearch:
    def __init__(self, *, store: TimelineStore, embedder) -> None:
        self.store = store
        self.embedder = embedder
        self.logger = logging.getLogger(__name__)

    async def search(
        self,
        user_id: str,
        *,
        query: str | None = None,
        mode: str = "auto",
        limit: int = 10,
        topic_id: str | None = None,
        catalog: str | None = None,
        hours: int = 24,
        exclude_superseded: bool = True,
    ) -> list[T2Memory]:
        if mode not in _VALID_MODES:
            raise ValueError(f"unknown mode: {mode!r}")

        if mode == "auto":
            if query and not topic_id and not catalog:
                mode = "semantic"
            elif topic_id and not query:
                mode = "by_topic"
            elif catalog:
                mode = "by_catalog"
            else:
                mode = "recent"

        if mode == "semantic":
            results = await self._semantic(user_id, query, limit, exclude_superseded)
        elif mode == "current_state":
            results = await self._current_state(user_id, topic_id, limit)
        elif mode == "by_topic":
            results = await self._by_topic(user_id, topic_id, limit, ascending=False)
        elif mode == "topic_timeline":
            results = await self._by_topic(user_id, topic_id, limit, ascending=True)
        elif mode == "by_catalog":
            results = await self._by_catalog(user_id, catalog, limit, exclude_superseded)
        elif mode == "change_log":
            results = await self._change_log(user_id, topic_id, limit)
        elif mode == "recent":
            results = await self.store.list_recent(user_id, hours=hours, limit=limit)
        else:  # pragma: no cover
            raise ValueError(f"unhandled mode: {mode!r}")

        if results and mode != "recent":
            await self._refresh_touched_topics(user_id, results)
        return results

    async def preflight(
        self,
        user_id: str,
        message: str,
        *,
        limit: int = KNN_NEIGHBOURS_FOR_PRE_FLIGHT,
    ) -> list[T2Memory]:
        self.logger.debug("T2: preflight user=%s len=%d", user_id, len(message or ""))
        return await self.search(user_id, query=message, mode="semantic", limit=limit)

    # ------------------------------------------------------------------
    # Mode implementations
    # ------------------------------------------------------------------
    async def _semantic(
        self,
        user_id: str,
        query: str | None,
        limit: int,
        exclude_superseded: bool,
    ) -> list[T2Memory]:
        if not query:
            raise ValueError("semantic mode requires a query")
        vec = await self.embedder.get_embedding(query)
        hits = await self.store.knn_memories(
            user_id, vec, k=limit, exclude_superseded=exclude_superseded
        )
        return [m for m, _score in hits]

    async def _current_state(
        self, user_id: str, topic_id: str | None, limit: int
    ) -> list[T2Memory]:
        clause = (
            f"@user_id:{{{_escape_tag(user_id)}}} "
            f"@superseded_by:{{_active}}"
        )
        if topic_id:
            clause = f"{clause} @topic_ids:{{{_escape_tag(topic_id)}}}"
        return await self._ft_search(clause, "last_accessed", "DESC", limit)

    async def _by_topic(
        self, user_id: str, topic_id: str | None, limit: int, *, ascending: bool
    ) -> list[T2Memory]:
        if not topic_id:
            raise ValueError("by_topic / topic_timeline mode requires topic_id")
        clause = (
            f"@user_id:{{{_escape_tag(user_id)}}} "
            f"@topic_ids:{{{_escape_tag(topic_id)}}}"
        )
        order = "ASC" if ascending else "DESC"
        return await self._ft_search(clause, "created_at", order, limit)

    async def _by_catalog(
        self,
        user_id: str,
        catalog: str | None,
        limit: int,
        exclude_superseded: bool,
    ) -> list[T2Memory]:
        if not catalog:
            raise ValueError("by_catalog mode requires catalog")
        clause = (
            f"@user_id:{{{_escape_tag(user_id)}}} "
            f"@catalogs:{{{_escape_tag(catalog)}}}"
        )
        if exclude_superseded:
            clause = f"{clause} @superseded_by:{{_active}}"
        return await self._ft_search(clause, "created_at", "DESC", limit)

    async def _change_log(
        self, user_id: str, topic_id: str | None, limit: int
    ) -> list[T2Memory]:
        clause = (
            f"@user_id:{{{_escape_tag(user_id)}}} "
            f"@change_type:{{update|correction|reinforcement}}"
        )
        if topic_id:
            clause = f"{clause} @topic_ids:{{{_escape_tag(topic_id)}}}"
        return await self._ft_search(clause, "created_at", "DESC", limit)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _ft_search(
        self, clause: str, sort_field: str, order: str, limit: int
    ) -> list[T2Memory]:
        try:
            res = await self.store.redis.execute_command(
                "FT.SEARCH", self.store.MEM_INDEX, clause,
                "SORTBY", sort_field, order,
                "LIMIT", "0", str(limit),
                "DIALECT", "2",
            )
        except Exception as exc:
            self.logger.debug("T2: search failed (%s): %s", clause, exc)
            return []
        return self.store._parse_search_memories(res)

    async def _refresh_touched_topics(
        self, user_id: str, memories: list[T2Memory]
    ) -> None:
        counter: Counter[str] = Counter()
        first_seen: dict[str, int] = {}
        for idx, mem in enumerate(memories):
            for tid in mem.topic_ids:
                counter[tid] += 1
                first_seen.setdefault(tid, idx)
        ranked = sorted(
            counter.items(),
            key=lambda kv: (-kv[1], first_seen.get(kv[0], 0)),
        )
        for topic_id, _count in ranked[:_REFRESH_TOPIC_CAP]:
            try:
                await self.store.refresh_topic(user_id, topic_id, bump_access=True)
            except Exception as exc:
                self.logger.debug("T2: refresh_topic failed for %s: %s", topic_id, exc)
            try:
                await self.store.extend_topic_memory_ttls(
                    user_id, topic_id, top=TOPIC_CASCADE_LIMIT
                )
            except Exception as exc:
                self.logger.debug(
                    "T2: extend_topic_memory_ttls failed for %s: %s", topic_id, exc
                )
