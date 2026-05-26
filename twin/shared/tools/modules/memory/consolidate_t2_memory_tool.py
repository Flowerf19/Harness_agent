"""Evernight-only tool for consolidating T1 snapshots into T2 memory."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from twin.shared.llm.llm_response import LLMResponse
from twin.shared.memories.t2.models import (
    T2Chunk,
    T2Fact,
    T2Page,
    generate_topic_id,
    get_ttl_by_importance,
)
from twin.shared.tools.base_tool import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)


CONSOLIDATE_T2_PROMPT = """Role: T2_Memory_Consolidator
Task: Extract durable Tier-2 memory entries from the chat snapshot.

Return ONLY valid JSON as an array. Each entry must include:
- canonical_topic: stable snake_case or Title_Case topic key
- topic_aliases: list of alternate names
- category: one of entertainment, relationship, work_study, casual, daily_mood, preference, project, identity
- entities: list of people, projects, places, tools, or media mentioned
- summary: current concise summary for the topic
- key_points: list of concrete durable points
- resolution_status: open, resolved, changed, or unknown
- user_sentiment: neutral, positive, negative, mixed, or unknown
- chunk_content: standalone timeline chunk text; do not copy the summary
- source_message_ids: message_id values from the snapshot that support this entry
- event_date: ISO-8601 datetime or YYYY-MM-DD for when the remembered event happened
- facts: list of durable fact strings or objects with claim/confidence/importance
- decision_changes: object describing changed decisions/preferences, or {{}}
- importance: integer 1-5
- confidence: number 0.0-1.0

If there is no durable information, return [].

Snapshot JSON:
{snapshot_json}
"""


class ConsolidateT2MemoryTool(BaseTool):
    """Tool for Evernight to write consolidated T2 memory."""

    def __init__(self, memory_manager: Optional[Any] = None, llm_service: Optional[Any] = None):
        self.memory_manager = memory_manager
        self.llm_service = llm_service

    @property
    def name(self) -> str:
        return "consolidate_t2_memory"

    @property
    def description(self) -> str:
        return (
            "Evernight-only. Consolidate a T1 chat snapshot into Redis-backed T2 "
            "pages, chunks, and facts."
        )

    @property
    def allowed_agents(self) -> Optional[Set[str]]:
        return {"evernight"}

    @property
    def visible_to_agents(self) -> Optional[Set[str]]:
        return {"evernight"}

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "Discord user ID whose T1 snapshot is being consolidated.",
                },
                "snapshot": {
                    "type": "array",
                    "description": "Chat messages from T1. Each item may include role, content, message_id, and timestamp.",
                    "items": {"type": "object"},
                },
                "reason": {
                    "type": "string",
                    "enum": ["overflow", "inactivity", "manual"],
                    "description": "Why consolidation was triggered.",
                },
            },
            "required": ["user_id", "snapshot", "reason"],
        }

    async def execute(self, user_id: str, snapshot: list[dict], reason: str) -> str:
        if not self.memory_manager:
            return "Lỗi: T2 memory chưa sẵn sàng."
        if not self.llm_service:
            return "Lỗi: Evernight LLM chưa sẵn sàng."
        if reason not in {"overflow", "inactivity", "manual"}:
            return "Lỗi: reason không hợp lệ."

        normalized_snapshot = self._normalize_snapshot(snapshot)
        if not normalized_snapshot:
            return "OK: no snapshot messages to consolidate."

        entries = await self._extract_entries(normalized_snapshot)
        if not entries:
            return "OK: no durable T2 entries found."

        written = 0
        for entry in entries:
            self._validate_entry(entry)
            await self._write_entry(user_id, entry, normalized_snapshot)
            written += 1

        return f"OK: consolidated {written} T2 entries for user {user_id} ({reason})."

    def _normalize_snapshot(self, snapshot: list[dict]) -> list[dict]:
        normalized: list[dict] = []
        for index, raw in enumerate(snapshot or [], start=1):
            item = raw.model_dump(mode="json") if hasattr(raw, "model_dump") else dict(raw or {})
            message_id = item.get("message_id") or item.get("id") or f"snapshot-{index}"
            item["message_id"] = str(message_id)
            item.setdefault("role", "unknown")
            item.setdefault("content", "")
            normalized.append(item)
        return normalized

    async def _extract_entries(self, snapshot: list[dict]) -> list[dict]:
        prompt = CONSOLIDATE_T2_PROMPT.format(
            snapshot_json=json.dumps(snapshot, ensure_ascii=False, indent=2)
        )
        response = await self.llm_service.generate_response(
            messages=[{"role": "user", "content": prompt}],
            use_native_tools=False,
        )
        raw = response.content if isinstance(response, LLMResponse) else str(response)
        data = json.loads(self._clean_json(raw))
        if isinstance(data, dict):
            data = data.get("entries", [])
        if not isinstance(data, list):
            raise ToolExecutionError(self.name, "LLM output must be a JSON array.")
        return data

    def _clean_json(self, raw_text: str) -> str:
        cleaned = raw_text.strip()
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"```$", "", cleaned)
        return cleaned.strip()

    def _validate_entry(self, entry: dict) -> None:
        required = [
            "canonical_topic",
            "summary",
            "chunk_content",
            "source_message_ids",
        ]
        for field in required:
            if not entry.get(field):
                raise ToolExecutionError(self.name, f"Entry thiếu '{field}'.")
        if not isinstance(entry["source_message_ids"], list):
            raise ToolExecutionError(self.name, "Entry 'source_message_ids' phải là list.")
        if not str(entry["chunk_content"]).strip():
            raise ToolExecutionError(self.name, "Entry 'chunk_content' không được rỗng.")

    async def _write_entry(self, user_id: str, entry: dict, snapshot: list[dict]) -> None:
        now = datetime.now(timezone.utc)
        canonical_topic = str(entry["canonical_topic"]).strip()
        topic_id = generate_topic_id(user_id, canonical_topic)
        existing_page = await self.memory_manager.lookup_by_page_id(topic_id)
        importance = self._bounded_int(entry.get("importance", 3), 1, 5)
        confidence = self._bounded_float(entry.get("confidence", 1.0), 0.0, 1.0)

        if existing_page:
            page = existing_page
            page.canonical_topic = canonical_topic
            page.topic_aliases = self._merge_strings(page.topic_aliases, entry.get("topic_aliases", []))
            page.key_points = self._merge_strings(page.key_points, entry.get("key_points", []))
            page.entities = self._merge_strings(page.entities, entry.get("entities", []))
            page.current_summary = str(entry.get("summary") or page.current_summary)
            page.category = str(entry.get("category") or page.category)
            page.resolution_status = str(entry.get("resolution_status") or page.resolution_status)
            page.user_sentiment = str(entry.get("user_sentiment") or page.user_sentiment)
            page.importance = importance
            page.confidence = confidence
            page.ttl_days = get_ttl_by_importance(importance)
            page.updated_at = now
        else:
            page = T2Page(
                page_id=topic_id,
                user_id=user_id,
                topic_id=topic_id,
                canonical_topic=canonical_topic,
                topic_aliases=self._string_list(entry.get("topic_aliases", [])),
                category=str(entry.get("category") or "casual"),
                current_summary=str(entry.get("summary") or ""),
                key_points=self._string_list(entry.get("key_points", [])),
                entities=self._string_list(entry.get("entities", [])),
                resolution_status=str(entry.get("resolution_status") or "open"),
                user_sentiment=str(entry.get("user_sentiment") or "neutral"),
                importance=importance,
                confidence=confidence,
                ttl_days=get_ttl_by_importance(importance),
                created_at=now,
                updated_at=now,
                last_accessed=now,
            )

        previous_chunk_id = page.latest_chunk_id
        chunk = T2Chunk(
            user_id=user_id,
            topic_id=topic_id,
            content=str(entry["chunk_content"]).strip(),
            event_date=self._parse_event_date(entry.get("event_date"), snapshot),
            importance=importance,
            confidence=confidence,
            previous_chunk_id=previous_chunk_id,
            source_message_ids=[str(value) for value in entry["source_message_ids"]],
            decision_changes=entry.get("decision_changes") or {},
        )

        facts = self._create_facts(user_id, topic_id, entry.get("facts", []), chunk, importance, confidence)
        chunk.introduced_fact_ids = [fact.fact_id for fact in facts]
        page.latest_chunk_id = chunk.chunk_id
        page.active_fact_ids = self._merge_strings(page.active_fact_ids, chunk.introduced_fact_ids)
        if previous_chunk_id:
            page.history_log.append(f"{now.isoformat()}: added chunk {chunk.chunk_id} after {previous_chunk_id}")
        else:
            page.history_log.append(f"{now.isoformat()}: created page from T1 consolidation")

        await self.memory_manager.upsert_page_with_chunk(page, chunk, facts)

    def _create_facts(
        self,
        user_id: str,
        topic_id: str,
        raw_facts: list[Any],
        chunk: T2Chunk,
        importance: int,
        confidence: float,
    ) -> list[T2Fact]:
        facts: list[T2Fact] = []
        for raw in raw_facts or []:
            if isinstance(raw, dict):
                claim = raw.get("claim") or raw.get("text")
                fact_importance = self._bounded_int(raw.get("importance", importance), 1, 5)
                fact_confidence = self._bounded_float(raw.get("confidence", confidence), 0.0, 1.0)
            else:
                claim = raw
                fact_importance = importance
                fact_confidence = confidence
            if not claim:
                continue
            facts.append(
                T2Fact(
                    user_id=user_id,
                    topic_id=topic_id,
                    claim=str(claim).strip(),
                    importance=fact_importance,
                    confidence=fact_confidence,
                    introduced_at_chunk_id=chunk.chunk_id,
                )
            )
        return facts

    def _parse_event_date(self, value: Any, snapshot: list[dict]) -> datetime:
        candidates = [value]
        candidates.extend(item.get("timestamp") or item.get("created_at") for item in snapshot)
        for candidate in candidates:
            if not candidate:
                continue
            if isinstance(candidate, datetime):
                return candidate if candidate.tzinfo else candidate.replace(tzinfo=timezone.utc)
            try:
                text = str(candidate).replace("Z", "+00:00")
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
                    text = f"{text}T00:00:00+00:00"
                parsed = datetime.fromisoformat(text)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return datetime.now(timezone.utc)

    def _string_list(self, values: Any) -> list[str]:
        if values is None:
            return []
        if isinstance(values, str):
            return [values]
        if not isinstance(values, list):
            return [str(values)]
        return [str(value) for value in values if value is not None and str(value).strip()]

    def _merge_strings(self, current: list[str], new_values: Any) -> list[str]:
        result = list(current or [])
        seen = {item.lower() for item in result}
        for item in self._string_list(new_values):
            if item.lower() not in seen:
                result.append(item)
                seen.add(item.lower())
        return result

    def _bounded_int(self, value: Any, minimum: int, maximum: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = minimum
        return max(minimum, min(maximum, number))

    def _bounded_float(self, value: Any, minimum: float, maximum: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = maximum
        return max(minimum, min(maximum, number))
