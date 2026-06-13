"""T2 timeline search — composable read-paths over TimelineStore."""
from __future__ import annotations

import logging
from collections import Counter

from twin.shared.memory.timeline.constants import (
    KNN_NEIGHBOURS_FOR_PRE_FLIGHT,
)
from twin.shared.memory.timeline.models import T2Memory
from twin.shared.memory.timeline.store import TimelineStore, _escape_tag

_VALID_MODES = {
    "auto", "semantic", "by_catalog", "recent",
}


def format_preflight_for_prompt(memories: list[T2Memory]) -> str:
    if not memories:
        return ""
    lines = ["## Ngữ cảnh nhớ liên quan (dùng tự nhiên, không lộ nguồn)"]
    for m in memories:
        content = m.content
        if len(content) > 240:
            content = content[:240] + "…"
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
        catalog: str | None = None,
        hours: int = 24,
    ) -> list[T2Memory]:
        if mode not in _VALID_MODES:
            raise ValueError(f"unknown mode: {mode!r}")

        if mode == "auto":
            if query and not catalog:
                mode = "semantic"
            elif catalog:
                mode = "by_catalog"
            else:
                mode = "recent"

        if mode == "semantic":
            results = await self._semantic(user_id, query, limit)
        elif mode == "by_catalog":
            results = await self._by_catalog(user_id, catalog, limit)
        elif mode == "recent":
            results = await self.store.list_recent(user_id, hours=hours, limit=limit)
        else:  # pragma: no cover
            raise ValueError(f"unhandled mode: {mode!r}")

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
    ) -> list[T2Memory]:
        if not query:
            raise ValueError("semantic mode requires a query")
        vec = await self.embedder.get_embedding(query)
        hits = await self.store.knn_memories(
            user_id, vec, k=limit
        )
        return [m for m, _score in hits]

    async def _by_catalog(
        self,
        user_id: str,
        catalog: str | None,
        limit: int,
    ) -> list[T2Memory]:
        if not catalog:
            raise ValueError("by_catalog mode requires catalog")
        clause = (
            f"@user_id:{{{_escape_tag(user_id)}}} "
            f"@catalogs:{{{_escape_tag(catalog)}}}"
        )
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

