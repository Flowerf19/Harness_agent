"""LLM merge helper for T2 pages."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from twin.shared.llm.llm_response import LLMResponse
from twin.shared.memories.t2.models import T2Chunk, T2Fact, T2Page, generate_topic_id, get_ttl_by_importance

logger = logging.getLogger(__name__)

T2_MERGE_PROMPT = """Role: Memory_Consolidator
Task: Merge_T2_Page

Input:
  old_page: {old_page_json}
  new_info: {new_info_json}

Rules:
  - Current mutable facts replace old values.
  - Historical timeline details should be preserved as facts or key_points.
  - Mark status/sentiment/entities when visible.

Return ONLY valid JSON:
{{
  "current_summary": "<merged summary>",
  "key_points": ["<point>"],
  "history_log": ["<change>"],
  "category": "<category>",
  "importance": <1-5>,
  "entities": ["<entity>"],
  "resolution_status": "<open|resolved|changed>",
  "user_sentiment": "<neutral|positive|negative|mixed>",
  "facts": ["<active fact>"]
}}"""


class T2Merge:
    def __init__(self, llm_client: Any):
        self.llm_client = llm_client

    def _clean_json_output(self, raw_text: str) -> str:
        cleaned = raw_text.strip()
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"```$", "", cleaned)
        return cleaned.strip()

    async def merge(self, old_page: T2Page, new_info: dict) -> T2Page | None:
        try:
            prompt = T2_MERGE_PROMPT.format(
                old_page_json=json.dumps(old_page.model_dump(mode="json"), ensure_ascii=False, indent=2),
                new_info_json=json.dumps(new_info, ensure_ascii=False, indent=2),
            )
            response = await self.llm_client.generate_response(messages=[{"role": "user", "content": prompt}])
            raw = response.content if isinstance(response, LLMResponse) else str(response)
            data = json.loads(self._clean_json_output(raw))
            now = datetime.now(timezone.utc)
            old_page.current_summary = data.get("current_summary", old_page.current_summary)
            old_page.key_points = data.get("key_points", old_page.key_points)
            old_page.history_log = data.get("history_log", old_page.history_log)
            old_page.category = data.get("category", old_page.category)
            old_page.importance = data.get("importance", old_page.importance)
            old_page.entities = data.get("entities", old_page.entities)
            old_page.resolution_status = data.get("resolution_status", old_page.resolution_status)
            old_page.user_sentiment = data.get("user_sentiment", old_page.user_sentiment)
            old_page.ttl_days = get_ttl_by_importance(old_page.importance)
            old_page.updated_at = now
            return old_page
        except Exception as e:
            logger.error("T2Merge: merge failed: %s", e, exc_info=True)
            return None

    def create_new_page(self, user_id: str, canonical_topic: str, new_info: dict) -> T2Page:
        now = datetime.now(timezone.utc)
        topic_id = generate_topic_id(user_id, canonical_topic)
        importance = new_info.get("importance", 3)
        return T2Page(
            page_id=topic_id,
            user_id=user_id,
            topic_id=topic_id,
            canonical_topic=canonical_topic,
            topic_aliases=new_info.get("topic_aliases", []),
            category=new_info.get("category", "casual"),
            current_summary=new_info.get("summary", ""),
            key_points=new_info.get("key_points", []),
            entities=new_info.get("entities", []),
            resolution_status=new_info.get("resolution_status", "open"),
            user_sentiment=new_info.get("user_sentiment", "neutral"),
            importance=importance,
            ttl_days=get_ttl_by_importance(importance),
            created_at=now,
            updated_at=now,
            last_accessed=now,
            confidence=new_info.get("confidence", 1.0),
        )

    def create_chunk(self, user_id: str, page: T2Page, snapshot_text: str, new_info: dict) -> T2Chunk:
        return T2Chunk(
            user_id=user_id,
            topic_id=page.topic_id,
            content=new_info.get("summary") or snapshot_text,
            importance=new_info.get("importance", page.importance),
            confidence=new_info.get("confidence", page.confidence),
        )

    def create_facts(self, user_id: str, page: T2Page, facts: list[str], chunk_id: str) -> list[T2Fact]:
        return [
            T2Fact(
                user_id=user_id,
                topic_id=page.topic_id,
                claim=claim,
                importance=page.importance,
                confidence=page.confidence,
                introduced_at_chunk_id=chunk_id,
            )
            for claim in facts
        ]
