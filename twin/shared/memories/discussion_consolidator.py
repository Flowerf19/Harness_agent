"""Consolidate T1 discussion windows into user-centric T2 pages."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from twin.shared.memories.t2.models import T2Page, generate_topic_id, utc_now

logger = logging.getLogger(__name__)


# Regex to extract a JSON object out of LLM output that may wrap it in code
# fences or markdown.  We accept ```json ... ```, ``` ... ``` or a bare {...}.
_JSON_BLOCK_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```|(\{.*\})",
    re.DOTALL,
)


def extract_json_object(text: str) -> str:
    """Best-effort extraction of a JSON object from LLM-shaped text."""
    if not text:
        raise ValueError("empty LLM response")

    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    match = _JSON_BLOCK_RE.search(text)
    if match:
        return (match.group(1) or match.group(2)).strip()

    raise ValueError("no JSON object found in LLM response")


class DiscussionConsolidator:
    """Turn a SUMMARY_REQUESTED payload into user-centric T2 pages.

    Returns a result dict so callers can choose whether to dispatch local
    events or to surface the result over an A2A skill response.
    """

    def __init__(
        self,
        llm: Any,
        t2_memory: Any,
        event_dispatcher: Any | None = None,
        bot_user_ids: set[str] | None = None,
    ):
        self.llm = llm
        self.t2 = t2_memory
        self.events = event_dispatcher
        self.bot_user_ids = {str(uid) for uid in (bot_user_ids or set())}

    async def consolidate(self, payload: dict) -> dict:
        """Run the LLM + fan-out + embed pipeline.

        Always returns a result dict.  Never raises.  Failure cases set
        ``status="failed"`` with a ``reason``.
        """
        try:
            transcript = self._format_transcript(payload)
            mode = "multi_user" if payload.get("scope") == "channel" else "single_user"
            summary = await self._llm_summarize(transcript, mode, payload)

            summarized_entry_ids = [e["entry_id"] for e in payload.get("entries", [])]

            if summary.get("status") == "skipped":
                return {
                    "status": "skipped",
                    "scope": payload.get("scope"),
                    "scope_id": payload.get("scope_id"),
                    "summarized_entry_ids": summarized_entry_ids,
                    "page_ids": [],
                    "canonical_topic": summary.get("canonical_topic"),
                    "active_participants": [],
                }

            participants = summary.get("participants") or self._participants_from_payload(payload)
            participants = self._strip_bot_ids(participants, payload)
            active_participants = summary.get("active_participants") or participants
            active_participants = self._strip_bot_ids(active_participants, payload)
            if mode == "single_user":
                active_participants = [payload["scope_id"]]
            elif not active_participants:
                # Channel turn where only bot lines remained after filtering.
                return {
                    "status": "skipped",
                    "scope": payload.get("scope"),
                    "scope_id": payload.get("scope_id"),
                    "summarized_entry_ids": summarized_entry_ids,
                    "page_ids": [],
                    "canonical_topic": summary.get("canonical_topic"),
                    "active_participants": [],
                }

            page_ids: list[str] = []
            for participant_id in active_participants:
                page = self._build_page(str(participant_id), summary, payload, participants)
                existing = await self.t2.lookup_by_page_id(page.page_id)
                merged = self._merge(existing, page) if existing else page
                await self.t2.embed_page(merged)
                page_ids.append(page.page_id)

            return {
                "status": "ok",
                "scope": payload.get("scope"),
                "scope_id": payload.get("scope_id"),
                "summarized_entry_ids": summarized_entry_ids,
                "page_ids": page_ids,
                "canonical_topic": summary.get("canonical_topic"),
                "active_participants": active_participants,
            }
        except Exception as exc:
            logger.exception("DiscussionConsolidator failed")
            return {
                "status": "failed",
                "scope": payload.get("scope"),
                "scope_id": payload.get("scope_id"),
                "reason": str(exc),
                "retry_after_seconds": 600,
            }

    def _format_transcript(self, payload: dict) -> str:
        lines = []
        for entry in payload.get("entries", []):
            name = entry.get("author_name") or entry.get("author_id") or entry.get("user_id") or entry.get("role")
            lines.append(f"{name}: {entry.get('content', '')}")
        return "\n".join(lines)

    async def _llm_summarize(self, transcript: str, mode: str, payload: dict) -> dict:
        prompt = (
            "Bạn là memory consolidator cho Bé Bảy.\n"
            f"Mode: {mode}.\n"
            "Chỉ lưu quyết định kỹ thuật, facts quan trọng, preference, context dự án, vấn đề debug, kết luận.\n"
            "Bỏ qua xã giao, câu ngắn không ngữ cảnh, joke không liên quan, spam.\n"
            "Output JSON với keys: canonical_topic, category, current_summary, key_points, "
            "participants, active_participants, importance (1-5), confidence (0-1), status (ok|skipped).\n"
            "Nếu nội dung không đáng lưu trả status=skipped.\n\n"
            f"Transcript:\n{transcript}"
        )
        response = await self.llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="Return ONLY a valid JSON object. No markdown fences, no commentary.",
            use_native_tools=False,
        )
        text = getattr(response, "content", response)
        if not isinstance(text, str):
            raise ValueError("LLM summary response is not text")
        return json.loads(extract_json_object(text))

    def _participants_from_payload(self, payload: dict) -> list[str]:
        """Collect distinct human author ids from the transcript.

        Assistant entries (the bot's own replies) are excluded so the
        fan-out never creates a user-centric T2 page for the bot itself.
        """
        participants: list[str] = []
        human_ids: set[str] = set()
        for entry in payload.get("entries", []):
            if entry.get("role") == "assistant":
                continue
            user_id = entry.get("author_id") or entry.get("user_id")
            if user_id and user_id not in human_ids:
                human_ids.add(user_id)
                participants.append(str(user_id))
        if not participants and payload.get("scope") == "user":
            participants.append(str(payload["scope_id"]))
        return participants

    def _human_ids(self, payload: dict) -> set[str]:
        """Set of human author ids (used to filter LLM-returned lists)."""
        ids: set[str] = set()
        for entry in payload.get("entries", []):
            if entry.get("role") == "assistant":
                continue
            uid = entry.get("author_id") or entry.get("user_id")
            if uid:
                ids.add(str(uid))
        if payload.get("scope") == "user":
            ids.add(str(payload["scope_id"]))
        return ids

    def _strip_bot_ids(self, participants: list[str], payload: dict) -> list[str]:
        """Drop bot ids from a participants list.

        An id is considered "bot-like" when it appears in the explicit
        ``bot_user_ids`` set passed at construction OR when the payload never
        contains a non-assistant entry for that id. Both checks together mean
        no T2 page is ever fanned out for a bot — even if the LLM hallucinates
        the bot into its participants list.
        """
        human_ids = self._human_ids(payload)
        result: list[str] = []
        for pid in participants:
            spid = str(pid)
            if spid in self.bot_user_ids:
                continue
            if spid not in human_ids:
                continue
            result.append(spid)
        return result

    def _build_page(
        self,
        participant_id: str,
        summary: dict,
        payload: dict,
        participants: list[str],
    ) -> T2Page:
        canonical_topic = summary["canonical_topic"]
        page_id = generate_topic_id(participant_id, canonical_topic)
        source_ref = {
            "channel_id": payload.get("channel_id"),
            "guild_id": payload.get("guild_id"),
            "msg_from": payload.get("from_entry_id"),
            "msg_to": payload.get("to_entry_id"),
            "from_ts": payload.get("from_ts"),
            "to_ts": payload.get("to_ts"),
        }
        return T2Page(
            page_id=page_id,
            user_id=participant_id,
            scope="user_global",
            topic_id=page_id,
            canonical_topic=canonical_topic,
            category=summary.get("category", "casual"),
            current_summary=summary.get("current_summary", ""),
            key_points=summary.get("key_points", []),
            participants=participants,
            source_refs=[source_ref],
            importance=summary.get("importance", 3),
            confidence=summary.get("confidence", 1.0),
        )

    def _merge(self, existing: T2Page, new: T2Page) -> T2Page:
        existing.current_summary = new.current_summary or existing.current_summary
        existing.key_points = list(dict.fromkeys([*existing.key_points, *new.key_points]))
        existing.participants = list(dict.fromkeys([*existing.participants, *new.participants]))
        existing.source_refs = [*existing.source_refs, *new.source_refs]
        existing.importance = max(existing.importance, new.importance)
        existing.confidence = max(existing.confidence, new.confidence)
        existing.access_count += 1
        existing.updated_at = utc_now()
        return existing
