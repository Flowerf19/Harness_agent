"""T2 background cleanup: supersede detection and topic merge."""
from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from twin.shared.memory.timeline.constants import (
    CLEANUP_SUPERSEDE_THRESHOLD,
    CLEANUP_TOPIC_MERGE_THRESHOLD,
)
from twin.shared.memory.timeline.models import T2Memory, T2Topic
from twin.shared.memory.timeline.store import TimelineStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- helpers


_JSON_BLOCK_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```|(\{.*\})",
    re.DOTALL,
)


def _extract_json(text: str) -> str:
    s = (text or "").strip()
    if s.startswith("{") and s.endswith("}"):
        return s
    m = _JSON_BLOCK_RE.search(text or "")
    if m:
        return (m.group(1) or m.group(2)).strip()
    raise ValueError("no JSON object")


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


# ---------------------------------------------------------------- prompts


_SUPERSEDE_SYSTEM_PROMPT = (
    "Return JSON only. No markdown fences, no commentary."
)


_TOPIC_MERGE_SYSTEM_PROMPT = (
    "Return JSON only. No markdown fences, no commentary."
)


# ---------------------------------------------------------------- result


@dataclass
class CleanupReport:
    supersedes_applied: int = 0
    topics_merged: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- service


class Cleanup:
    """Shared T2 cleanup. T3 curation belongs to manage_user_profile."""

    def __init__(
        self,
        *,
        store: TimelineStore,
        embedder,
        llm,
        supersede_threshold: float = CLEANUP_SUPERSEDE_THRESHOLD,
        topic_merge_threshold: float = CLEANUP_TOPIC_MERGE_THRESHOLD,
        recent_window_hours: int = 24,
        recent_limit: int = 100,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.llm = llm
        self.supersede_threshold = supersede_threshold
        self.topic_merge_threshold = topic_merge_threshold
        self.recent_window_hours = recent_window_hours
        self.recent_limit = recent_limit

    async def run(self, user_id: str) -> CleanupReport:
        report = CleanupReport()
        try:
            await self._t2_supersede(user_id, report)
        except Exception as exc:
            logger.warning(
                "T2:cleanup: supersede step crashed for %s: %s", user_id, exc,
                exc_info=True,
            )
            report.errors.append(f"supersede_step: {exc}")
        try:
            await self._topic_merge(user_id, report)
        except Exception as exc:
            logger.warning(
                "T2:cleanup: topic_merge step crashed for %s: %s", user_id, exc,
                exc_info=True,
            )
            report.errors.append(f"topic_merge_step: {exc}")
        return report

    # ----------------------------------------------------- supersede

    async def _t2_supersede(self, user_id: str, report: CleanupReport) -> None:
        recent = await self.store.list_recent(
            user_id,
            hours=self.recent_window_hours,
            limit=self.recent_limit,
        )
        # Filter to active memories with embeddings.
        active: list[T2Memory] = [
            m for m in recent
            if m.supersedes is None
            and m.superseded_by is None
            and m.embedding
        ]
        if len(active) < 2:
            return

        clusters = _greedy_cluster(
            active,
            key=lambda m: m.embedding,
            threshold=self.supersede_threshold,
        )
        for cluster in clusters:
            if len(cluster) < 2:
                continue
            try:
                pairs = await self._llm_judge_supersede(cluster)
            except Exception as exc:
                report.errors.append(f"supersede_llm: {exc}")
                continue
            ids_in_cluster = {m.memory_id for m in cluster}
            for pair in pairs:
                old_id = pair.get("old_id")
                new_id = pair.get("new_id")
                if not old_id or not new_id:
                    continue
                if old_id == new_id:
                    continue
                if old_id not in ids_in_cluster or new_id not in ids_in_cluster:
                    continue
                change_type = pair.get("change_type") or "correction"
                if change_type not in ("correction", "update"):
                    change_type = "correction"
                change_reason = pair.get("change_reason")
                try:
                    await self.store.mark_superseded(
                        user_id, old_id, new_id, change_type, change_reason,
                    )
                    report.supersedes_applied += 1
                except Exception as exc:
                    report.errors.append(f"supersede_mark: {exc}")

    async def _llm_judge_supersede(
        self, cluster: list[T2Memory]
    ) -> list[dict]:
        lines = []
        for m in cluster:
            lines.append(
                f"- id={m.memory_id} | created={m.created_at.isoformat()} | "
                f"change_type={m.change_type} | content={m.content}"
            )
        user_prompt = (
            "These memories are about the same fact. Is there a supersede "
            "chain (a newer one corrects/updates an older one)? Return JSON: "
            '{"supersedes": [{"old_id": "...", "new_id": "...", '
            '"change_type": "correction|update", "change_reason": "..."}]}. '
            'If none should be linked, return {"supersedes": []}.\n\n'
            "=== MEMORIES ===\n" + "\n".join(lines)
        )
        response = await self.llm.generate_response(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=_SUPERSEDE_SYSTEM_PROMPT,
            use_native_tools=False,
        )
        text = getattr(response, "content", None)
        if not isinstance(text, str):
            text = str(response) if response is not None else ""
        try:
            data = json.loads(_extract_json(text))
        except Exception as exc:
            logger.warning("T2:cleanup: supersede JSON parse failed: %s", exc)
            return []
        pairs = data.get("supersedes") if isinstance(data, dict) else None
        if not isinstance(pairs, list):
            return []
        return [p for p in pairs if isinstance(p, dict)]

    # ----------------------------------------------------- topic merge

    async def _topic_merge(self, user_id: str, report: CleanupReport) -> None:
        topics = await self.store.recent_topics(user_id, k=50)
        topics = [t for t in topics if t.embedding]
        if len(topics) < 2:
            return
        clusters = _greedy_cluster(
            topics,
            key=lambda t: t.embedding,
            threshold=self.topic_merge_threshold,
        )
        for cluster in clusters:
            if len(cluster) < 2:
                continue
            keeper = max(
                cluster,
                key=lambda t: (
                    t.memory_count,
                    t.importance,
                    -t.created_at.timestamp(),
                ),
            )
            losers = [t for t in cluster if t.topic_id != keeper.topic_id]
            if not losers:
                continue
            try:
                merge = await self._llm_judge_merge(keeper, losers)
            except Exception as exc:
                report.errors.append(f"topic_merge_llm: {exc}")
                continue
            if not merge:
                continue
            for loser in losers:
                try:
                    await self.store.rewrite_topic_id_in_memories(
                        user_id, loser.topic_id, keeper.topic_id,
                    )
                except Exception as exc:
                    report.errors.append(f"topic_merge_rewrite: {exc}")
                    continue
                _absorb_alias(keeper, loser.name)
                for alias in loser.aliases:
                    _absorb_alias(keeper, alias)
                keeper.memory_count += loser.memory_count
                try:
                    await self.store.delete_topic(user_id, loser.topic_id)
                    report.topics_merged += 1
                except Exception as exc:
                    report.errors.append(f"topic_merge_delete: {exc}")
            try:
                await self.store.upsert_topic(keeper)
            except Exception as exc:
                report.errors.append(f"topic_merge_upsert: {exc}")

    async def _llm_judge_merge(
        self, keeper: T2Topic, losers: list[T2Topic]
    ) -> bool:
        loser_lines = "\n".join(
            f"- id={t.topic_id} | name={t.name} | "
            f"aliases={','.join(t.aliases) or 'none'} | "
            f"memory_count={t.memory_count}"
            for t in losers
        )
        user_prompt = (
            "Should these topics be merged into the keeper? They are similar "
            "by embedding but you must judge whether they refer to the same "
            'subject. Return JSON: {"merge": true|false, "reason": "..."}.\n\n'
            f"=== KEEPER ===\n- id={keeper.topic_id} | name={keeper.name} | "
            f"aliases={','.join(keeper.aliases) or 'none'} | "
            f"memory_count={keeper.memory_count}\n\n"
            f"=== CANDIDATES TO MERGE ===\n{loser_lines}"
        )
        response = await self.llm.generate_response(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=_TOPIC_MERGE_SYSTEM_PROMPT,
            use_native_tools=False,
        )
        text = getattr(response, "content", None)
        if not isinstance(text, str):
            text = str(response) if response is not None else ""
        try:
            data = json.loads(_extract_json(text))
        except Exception as exc:
            logger.warning("T2:cleanup: topic merge JSON parse failed: %s", exc)
            return False
        return bool(isinstance(data, dict) and data.get("merge"))


# ---------------------------------------------------------------- internals


def _greedy_cluster(
    items: list,
    *,
    key: Callable[[Any], list[float]],
    threshold: float,
) -> list[list]:
    """Greedy clustering by cosine similarity to cluster mean.

    Each item joins the first cluster whose average similarity to its members
    is >= threshold; otherwise starts its own cluster.
    """
    clusters: list[list] = []
    for item in items:
        vec = key(item)
        if not vec:
            continue
        placed = False
        for cluster in clusters:
            sims = [_cosine(vec, key(other)) for other in cluster]
            if sims and (sum(sims) / len(sims)) >= threshold:
                cluster.append(item)
                placed = True
                break
        if not placed:
            clusters.append([item])
    return clusters


def _absorb_alias(keeper: T2Topic, alias: str) -> None:
    a = (alias or "").strip()
    if not a:
        return
    if a.lower() == keeper.name.lower():
        return
    if any(existing.lower() == a.lower() for existing in keeper.aliases):
        return
    keeper.aliases.append(a)
