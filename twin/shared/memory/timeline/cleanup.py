"""T2/T3 background cleanup: profile dedupe, supersede detection, topic merge."""
from __future__ import annotations

import asyncio
import difflib
import json
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

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


def _strip_fences(text: str) -> str:
    s = (text or "").strip()
    if s.startswith("```"):
        # Drop opening fence + optional language tag.
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*\n?", "", s)
        if s.endswith("```"):
            s = s[: -3]
    return s.strip()


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


def _diff_ratio(old: str, new: str) -> float:
    if not old and not new:
        return 0.0
    return 1.0 - difflib.SequenceMatcher(None, old, new).ratio()


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value) or isinstance(value, asyncio.Future):
        return await value
    return value


# ---------------------------------------------------------------- prompts


_T3_SYSTEM_PROMPT = (
    "Return raw markdown. No code fences. No commentary."
)

_T3_USER_PROMPT = (
    "Bạn là memory janitor. Merge duplicate bullets, resolve conflicts "
    "(giữ thông tin mới nhất khi mâu thuẫn), preserve markdown structure. "
    "Return ONLY the cleaned markdown, no commentary, no fences.\n\n"
    "=== HỒ SƠ ===\n"
    "{markdown}"
)


_SUPERSEDE_SYSTEM_PROMPT = (
    "Return JSON only. No markdown fences, no commentary."
)


_TOPIC_MERGE_SYSTEM_PROMPT = (
    "Return JSON only. No markdown fences, no commentary."
)


# ---------------------------------------------------------------- result


@dataclass
class CleanupReport:
    t3_updated: bool = False
    t3_diff_ratio: float = 0.0
    supersedes_applied: int = 0
    topics_merged: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- service


class Cleanup:
    """Three-step background cleanup. Never raises."""

    def __init__(
        self,
        *,
        store: TimelineStore,
        embedder,
        llm,
        profile_reader: Callable[[str], Awaitable[str] | str] | None = None,
        profile_writer: Callable[[str, str], Awaitable[None]] | None = None,
        supersede_threshold: float = CLEANUP_SUPERSEDE_THRESHOLD,
        topic_merge_threshold: float = CLEANUP_TOPIC_MERGE_THRESHOLD,
        recent_window_hours: int = 24,
        recent_limit: int = 100,
        max_diff_ratio: float = 0.5,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.llm = llm
        self.profile_reader = profile_reader
        self.profile_writer = profile_writer
        self.supersede_threshold = supersede_threshold
        self.topic_merge_threshold = topic_merge_threshold
        self.recent_window_hours = recent_window_hours
        self.recent_limit = recent_limit
        self.max_diff_ratio = max_diff_ratio

    async def run(self, user_id: str) -> CleanupReport:
        report = CleanupReport()
        try:
            await self._t3_cleanup(user_id, report)
        except Exception as exc:
            logger.warning(
                "T2:cleanup: T3 step crashed for %s: %s", user_id, exc,
                exc_info=True,
            )
            report.errors.append(f"t3_step: {exc}")
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

    # ----------------------------------------------------- step 1: T3

    async def _t3_cleanup(self, user_id: str, report: CleanupReport) -> None:
        if self.profile_reader is None or self.profile_writer is None:
            return
        try:
            old = await _maybe_await(self.profile_reader(user_id)) or ""
        except Exception as exc:
            report.errors.append(f"t3_read: {exc}")
            return
        if not old.strip():
            return

        try:
            response = await self.llm.generate_response(
                messages=[{
                    "role": "user",
                    "content": _T3_USER_PROMPT.format(markdown=old),
                }],
                system_prompt=_T3_SYSTEM_PROMPT,
                use_native_tools=False,
            )
        except Exception as exc:
            report.errors.append(f"t3_llm: {exc}")
            return

        text = getattr(response, "content", None)
        if not isinstance(text, str):
            text = str(response) if response is not None else ""
        new = _strip_fences(text)
        if not new.strip():
            report.errors.append("t3_llm: empty response")
            return

        ratio = _diff_ratio(old, new)
        report.t3_diff_ratio = ratio
        if ratio > self.max_diff_ratio:
            logger.warning(
                "T2:cleanup: T3 diff %.2f > %.2f for %s — skipping write",
                ratio, self.max_diff_ratio, user_id,
            )
            report.errors.append(
                f"t3_diff_too_large: {ratio:.2f} > {self.max_diff_ratio:.2f}"
            )
            return
        if ratio == 0.0:
            return
        try:
            await _maybe_await(self.profile_writer(user_id, new))
            report.t3_updated = True
        except Exception as exc:
            report.errors.append(f"t3_write: {exc}")

    # ----------------------------------------------------- step 2: supersede

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
            logger.debug("T2:cleanup: supersede JSON parse failed: %s", exc)
            return []
        pairs = data.get("supersedes") if isinstance(data, dict) else None
        if not isinstance(pairs, list):
            return []
        return [p for p in pairs if isinstance(p, dict)]

    # ----------------------------------------------------- step 3: topic merge

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
            logger.debug("T2:cleanup: topic merge JSON parse failed: %s", exc)
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
