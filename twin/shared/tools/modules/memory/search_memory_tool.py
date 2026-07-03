"""SearchMemoryTool - query T2 timeline memory."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Coroutine, Optional

from twin.shared.config.settings import Config
from twin.shared.llm.embedding.embedding_trace_logger import (
    cosine_similarity,
    token_overlap,
)
from twin.shared.memory.vn_time import VN_TZ, vn_now
from twin.shared.tools.registry.base import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)

_MAX_LIMIT = 20
_WIDEN_MULTIPLIER = 3


class SearchMemoryTool(BaseTool):
    """Tool for querying Redis Stack backed T2 timeline memory.

    Interface v3 (P3.1, fix B1): the only params are `query` and
    `days_back` (plus `user_id`/`channel_id`/`limit`) — `mode`/`topic`/
    `hours`/`days` are gone. Behavior is inferred from which of
    query/days_back are present:
        query + days_back -> hybrid search, time-filtered
        query only        -> hybrid search, all-time
        days_back only    -> timeline in that range, sorted new -> old
        neither            -> recent
    """

    def __init__(
        self,
        timeline_summary_store: Optional[Any] = None,
        embedding_service: Optional[Any] = None,
    ):
        self.timeline_summary_store = timeline_summary_store
        self.embedding_service = embedding_service

    @property
    def name(self) -> str:
        return "search_memory"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "Discord user ID.",
                },
                "channel_id": {
                    "type": "string",
                    "description": (
                        "ID kênh Discord hiện tại — chỉ truyền khi đang chat "
                        "trong kênh chung (lấy 'Platform channel ID' từ system "
                        "prompt). Tool sẽ tìm cả ký ức của kênh."
                    ),
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Truy vấn đã rewrite thành từ khóa chủ đề. Bỏ trống = "
                        "xem dòng thời gian gần đây."
                    ),
                },
                "days_back": {
                    "type": "integer",
                    "description": (
                        "Số ngày nhìn lại — chỉ đưa khi user có mốc thời gian "
                        "('hôm qua'→2, 'mấy ngày trước'→7, 'tuần trước'→10, "
                        "'tháng trước'→35)."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "default": 5,
                    "description": f"Số kết quả, tối đa {_MAX_LIMIT}.",
                },
            },
            "required": ["user_id"],
        }

    async def execute(
        self,
        user_id: str,
        channel_id: Optional[str] = None,
        query: Optional[str] = None,
        days_back: Optional[int] = None,
        limit: int = 5,
    ) -> str:
        user_id = str(user_id or "").strip()
        channel_id = str(channel_id or "").strip() or None
        query = (query or "").strip() or None
        days_back = self._positive_int_or_none(days_back)

        if not user_id:
            return "Lỗi: Thiếu user_id."

        if not user_id.isdigit():
            logger.warning("T2: invalid user_id for search_memory: %s", user_id)
            return f"Lỗi: user_id '{user_id}' không hợp lệ. user_id phải là số ID của Discord user."

        if channel_id and not channel_id.isdigit():
            # Auxiliary scope only — drop it rather than failing the recall.
            logger.warning("T2: invalid channel_id for search_memory: %s", channel_id)
            channel_id = None

        if self.timeline_summary_store is None:
            return "Lỗi: timeline_summary_store chưa được cấu hình."

        limit = self._bounded_limit(limit)

        # T2 channel summaries are stored under user_id=channel_id, so a turn
        # in a channel must search BOTH the speaker scope and the channel
        # scope. This tool is the ONLY recall path (no automatic preflight),
        # so dropping the channel scope here would make channel memory
        # permanently unreachable.
        scope_ids = [user_id]
        if channel_id and channel_id != user_id:
            scope_ids.append(channel_id)

        widen_label: Optional[str] = None
        try:
            if query:
                if self.embedding_service is None:
                    return "Lỗi: embedding_service chưa được cấu hình."
                memories, widen_label = await self._search_with_query(
                    scope_ids, query, days_back, limit,
                )
            elif days_back:
                memories, widen_label = await self._search_timeline(
                    scope_ids, days_back, limit,
                )
            else:
                memories = await self._search_recent(scope_ids, limit)
        except Exception as e:
            logger.error("SearchMemoryTool: search failed: %s", e, exc_info=True)
            return f"Lỗi khi tìm kiếm ký ức: {e}"

        return self._format_memories(memories, widen_label=widen_label)

    # ------------------------------------------------------ behavior matrix

    async def _search_with_query(
        self, scope_ids: list[str], query: str, days_back: Optional[int], limit: int,
    ) -> tuple[list[Any], Optional[str]]:
        """`query` present (P3.1): always hybrid (KNN+BM25) — v3 drops the
        old separate semantic-only mode. `days_back`, if given, widens on
        empty (P3.3); the embedding is computed once and reused across
        widen rounds — only the time window changes between rounds."""
        query_input = f"{Config.EMBEDDING_QUERY_PREFIX}{query}"
        embedding = await self.embedding_service.get_embedding(query_input)

        async def round_fn(since_ts: Optional[float]) -> list[Any]:
            memories, sources = await self._dual_scope_semantic(
                scope_ids, embedding, limit, query, since_ts,
            )
            self._trace_search_results(
                query_input, query, embedding, memories,
                scope_ids=scope_ids, sources=sources,
            )
            return memories

        if days_back is None:
            return await round_fn(None), None
        return await self._widen_and_format(round_fn, days_back)

    async def _search_timeline(
        self, scope_ids: list[str], days_back: int, limit: int,
    ) -> tuple[list[Any], Optional[str]]:
        """`days_back` alone (no query): timeline within that range, sorted
        new -> old, no embedding call. Widens on empty (P3.3)."""

        async def round_fn(since_ts: Optional[float]) -> list[Any]:
            return await self._dual_scope_recent(scope_ids, limit, since_ts)

        return await self._widen_and_format(round_fn, days_back)

    async def _search_recent(self, scope_ids: list[str], limit: int) -> list[Any]:
        """Neither `query` nor `days_back`: plain recent, no time filter —
        nothing to widen from, so this is a single unlabeled round."""
        return await self._dual_scope_recent(scope_ids, limit, since_ts=None)

    # ------------------------------------------------------------ P3.3 widen

    async def _widen_and_format(
        self,
        round_fn: Callable[[Optional[float]], Coroutine[Any, Any, list[Any]]],
        days_back: int,
    ) -> tuple[list[Any], Optional[str]]:
        """Try `days_back`, then `days_back*3`, then no filter at all — max 3
        rounds, all within this single tool call (the LLM still only sees one
        call). A round past the first labels its results so the model stays
        honest about the wider window it actually saw, instead of silently
        answering as if the original window had data.
        """
        widened_days = days_back * _WIDEN_MULTIPLIER
        rounds: list[tuple[Optional[int], Optional[str]]] = [
            (days_back, None),
            (widened_days, (
                f"(không thấy trong {days_back} ngày — kết quả từ {widened_days} ngày)"
            )),
            (None, (
                f"(không thấy trong {days_back} ngày — kết quả từ toàn bộ)"
            )),
        ]
        for round_days, label in rounds:
            since_ts = (
                self._since_ts_from_days_back(round_days)
                if round_days is not None else None
            )
            memories = await round_fn(since_ts)
            if memories:
                return memories, label
        return [], None

    # ------------------------------------------------------- dual-scope I/O

    async def _dual_scope_semantic(
        self,
        scope_ids: list[str],
        embedding: list[float],
        limit: int,
        query_text: str,
        since_ts: Optional[float],
    ) -> tuple[list[Any], list[str]]:
        """Hybrid-search every scope, dedup, truncate to limit. Returns
        (memories, sources) where sources[i] is the scope memories[i] came
        from (needed by the trace log)."""
        memories: list[Any] = []
        sources: list[str] = []
        seen: set[Any] = set()
        # Only pass since_ts when set, so store fakes with the pre-P3.2
        # signature (no since_ts kwarg) stay compatible on the untimed path.
        time_kwargs: dict[str, float] = {}
        if since_ts is not None:
            time_kwargs["since_ts"] = since_ts
        for sid in scope_ids:
            results = await self.timeline_summary_store.search(
                user_id=sid,
                query_embedding=embedding,
                limit=limit,
                query_text=query_text,
                **time_kwargs,
            )
            for summary in results:
                key = self._dedup_key(summary)
                if key in seen:
                    continue
                seen.add(key)
                memories.append(summary)
                sources.append(sid)
        return memories[:limit], sources[:limit]

    async def _dual_scope_recent(
        self, scope_ids: list[str], limit: int, since_ts: Optional[float],
    ) -> list[Any]:
        """get_recent every scope, dedup, re-sort merged newest-first."""
        memories: list[Any] = []
        seen: set[Any] = set()
        time_kwargs: dict[str, float] = {}
        if since_ts is not None:
            time_kwargs["since_ts"] = since_ts
        for sid in scope_ids:
            results = await self.timeline_summary_store.get_recent(
                user_id=sid, limit=limit, **time_kwargs,
            )
            for summary in results:
                key = self._dedup_key(summary)
                if key in seen:
                    continue
                seen.add(key)
                memories.append(summary)
        # Each scope returns newest-first; re-sort the merged list so channel
        # hits interleave with speaker hits chronologically.
        memories.sort(key=self._created_at_key, reverse=True)
        return memories[:limit]

    # ------------------------------------------------------------- helpers

    @staticmethod
    def _positive_int_or_none(value: Any) -> Optional[int]:
        if value is None or value == "":
            return None
        try:
            value = int(value)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    @staticmethod
    def _since_ts_from_days_back(days_back: int) -> float:
        return (vn_now() - timedelta(days=days_back)).timestamp()

    @staticmethod
    def _bounded_limit(limit: int) -> int:
        try:
            value = int(limit)
        except (TypeError, ValueError):
            value = 5
        return max(1, min(value, _MAX_LIMIT))

    @staticmethod
    def _dedup_key(memory: Any) -> Any:
        return (
            SearchMemoryTool._field(memory, "summary_id")
            or SearchMemoryTool._field(memory, "summary")
            or id(memory)
        )

    @staticmethod
    def _created_at_key(memory: Any) -> float:
        value = SearchMemoryTool._field(memory, "created_at")
        if isinstance(value, datetime):
            return value.timestamp()
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _trace_search_results(
        self,
        input_text: str,
        current_query: str,
        query_embedding: list[float],
        summaries: list[dict[str, Any]],
        scope_ids: list[str] | None = None,
        sources: list[str] | None = None,
    ) -> None:
        """Log every semantic search result for embedding model debugging.

        Moved here from SharedMemoryManager when automatic preflight was
        removed — the tool is now the only T2 search path, so SEARCH trace
        events (used for gate calibration) must be emitted here. ``scope_ids``/
        ``sources`` record which scopes the dual-scope search covered and which
        one each hit came from, without touching the fixed trace schema.
        """
        trace_logger = getattr(self.embedding_service, "trace_logger", None)
        if not trace_logger or not trace_logger.enabled:
            return

        for rank, summary in enumerate(summaries, start=1):
            matched_text = summary.get("summary") or summary.get("content", "")
            matched_embedding = summary.get("embedding")
            if matched_embedding and query_embedding:
                cs = cosine_similarity(query_embedding, matched_embedding)
            else:
                cs = None

            extra = None
            if scope_ids is not None:
                extra = {
                    "scope_ids_searched": scope_ids,
                    "source_scope_id": sources[rank - 1] if sources and rank <= len(sources) else None,
                }

            self.embedding_service._trace_embedding_event(
                input_text=input_text,
                vector=query_embedding,
                raw_dim=None,
                latency_ms=0.0,
                cache_hit=True,
                event_type="SEARCH",
                query_text=current_query,
                matched_text=matched_text,
                cosine_similarity=cs,
                token_overlap=token_overlap(current_query, matched_text),
                action="KNN_RESULT" if rank == 1 else "KNN_CANDIDATE",
                knn_score=summary.get("score"),
                bm25_score=summary.get("_score"),
                rrf_rank=rank,
                extra=extra,
            )

    @staticmethod
    def _days_ago_display(memory: Any) -> Optional[str]:
        """P3.4: "<N> ngày trước — DD/MM" in VN tz from `period_end`
        (fallback `created_at`). None when neither field is usable."""
        ts = SearchMemoryTool._field(memory, "period_end")
        if ts is None:
            ts = SearchMemoryTool._field(memory, "created_at")
        if isinstance(ts, datetime):
            ts = ts.timestamp()
        try:
            ts = float(ts)
        except (TypeError, ValueError):
            return None
        dt_vn = datetime.fromtimestamp(ts, tz=VN_TZ)
        delta_days = (vn_now().date() - dt_vn.date()).days
        when = "hôm nay" if delta_days <= 0 else f"{delta_days} ngày trước"
        return f"{when} — {dt_vn.strftime('%d/%m')}"

    @staticmethod
    def _format_memories(memories: Any, *, widen_label: Optional[str] = None) -> str:
        if isinstance(memories, str):
            return memories
        if not memories:
            return "Không tìm thấy ký ức phù hợp."

        header = f"Tìm thấy {len(memories)} ký ức:"
        if widen_label:
            header += f" {widen_label}"
        lines = [header]
        for index, memory in enumerate(memories, start=1):
            content = (
                SearchMemoryTool._field(memory, "summary")
                or SearchMemoryTool._field(memory, "content")
                or str(memory)
            )
            content = str(content).strip()
            topic_val = SearchMemoryTool._field(memory, "topic")
            topic_display = SearchMemoryTool._field(memory, "topic_display")
            label = topic_display or topic_val
            date_display = SearchMemoryTool._days_ago_display(memory)

            line = str(index) + "."
            if label:
                line += f" [{label}]"
            if date_display:
                line += f" ({date_display})"
            line += f" {content}"
            lines.append(line)

            metadata = SearchMemoryTool._metadata(memory)
            if metadata:
                lines.append(f"   ({'; '.join(metadata)})")
        return "\n".join(lines)

    @staticmethod
    def _field(memory: Any, field_name: str, default: Any = None) -> Any:
        if isinstance(memory, dict):
            return memory.get(field_name, default)
        return getattr(memory, field_name, default)

    @staticmethod
    def _metadata(memory: Any) -> list[str]:
        metadata: list[str] = []
        # KNN `score` is COSINE DISTANCE (1 - similarity) — surface it to the
        # LLM as a 0-1 relevance so weak hits can be treated with caution.
        score = SearchMemoryTool._field(memory, "score")
        if score is not None:
            try:
                metadata.append(f"relevance={1.0 - float(score):.2f}")
            except (TypeError, ValueError):
                pass
        elif SearchMemoryTool._field(memory, "_score") is not None:
            metadata.append("match=bm25")
        for field_name in ("memory_id", "summary_id", "speaker"):
            value = SearchMemoryTool._field(memory, field_name)
            if value:
                metadata.append(f"{field_name}={value}")

        catalogs = SearchMemoryTool._field(memory, "catalogs")
        if catalogs:
            metadata.append(f"catalogs={','.join(catalogs)}")

        created_at = SearchMemoryTool._field(memory, "created_at")
        if isinstance(created_at, datetime):
            metadata.append(f"created_at={created_at.isoformat()}")
        elif created_at:
            try:
                ts = float(created_at)
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                metadata.append(f"created_at={dt.isoformat()}")
            except (ValueError, TypeError):
                metadata.append(f"created_at={created_at}")

        return metadata

    def __repr__(self) -> str:
        return f"<SearchMemoryTool: timeline_summary_store={self.timeline_summary_store is not None}>"
