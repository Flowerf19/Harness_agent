"""ConsolidateMemoryTool - consolidate T1 active memory into T2 timeline + T3 profile."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from twin.shared.agent.contract import extract_json
from twin.shared.config.settings import Config
from twin.shared.observability import call_with_langsmith_extra, langsmith_extra
from twin.shared.observability.langsmith import traceable
from twin.shared.tools.registry.base import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)

_SUMMARIZER_PROMPT = """Bạn là Memory Summarizer. Đọc cuộc trò chuyện và trích xuất thông tin đáng nhớ theo từng topic.

=== HỒ SƠ HIỆN TẠI ===
{profile}

=== TIN NHẮN GẦN ĐÂY ===
{messages}

Nhiệm vụ:
1. Lọc noise (chào hỏi đơn thuần, emoji phiếm, thông tin tạm thời vô nghĩa).
2. Nếu session TOÀN noise hoặc không có gì đáng nhớ → set has_meaningful_content=false, topics=[].
3. Với nội dung có ý nghĩa: nhóm theo topic, mỗi topic viết 1-2 câu summary ngắn.
4. Tối đa 5 topics. Topic slug: lowercase, underscore, tự đặt (ví dụ: work, interest, health, travel, relationship...).
5. Trích xuất facts mới đáng lưu vào hồ sơ (bỏ qua nếu đã có hoặc mâu thuẫn thì ghi đè).

Return JSON:
{{
  "has_meaningful_content": true,
  "topics": [
    {{
      "topic": "work",
      "topic_display": "Công việc",
      "summary": "User đang làm dự án X, deadline tuần tới.",
      "importance": 4
    }}
  ],
  "profile_updates": {{
    "basic": [],
    "work": ["Đang làm dự án X"],
    "interest": [],
    "relationship": [],
    "habit": [],
    "psychological": [],
    "rules": [],
    "contact": []
  }}
}}

Rules importance:
- 5: identity/contact critical
- 4: work/relationship/habit quan trọng
- 3: interest/event thông thường
- 2-1: casual, temporary

Chỉ return JSON, không giải thích."""


class ConsolidateMemoryTool(BaseTool):
    """Consolidate T1 messages into T2 timeline + T3 profile."""

    def __init__(
        self,
        memory_manager: Any,
        llm_service: Any,
        embedding_service: Any,
        timeline_summary_store: Any,
    ):
        self.memory_manager = memory_manager
        self.llm_service = llm_service
        self.embedding_service = embedding_service
        self.timeline_summary_store = timeline_summary_store

    @property
    def name(self) -> str:
        return "consolidate_memory"

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "description": "Scope của consolidation (user hoặc channel)",
                    "default": "user",
                },
                "scope_id": {
                    "type": "string",
                    "description": "ID của scope cần consolidate",
                },
                "reason": {
                    "type": "string",
                    "description": "Lý do consolidate",
                },
                "max_messages": {
                    "type": "integer",
                    "default": 200,
                    "description": "Số messages tối đa cần tóm tắt",
                },
                "entries": {
                    "type": "array",
                    "description": "Danh sách entries được ship qua A2A để consolidate trực tiếp (không đọc T1 local)",
                    "items": {"type": "object"},
                },
            },
            "required": ["scope_id", "reason"],
        }

    @property
    def visible_to_agents(self) -> Optional[set[str]]:
        return {"evernight"}

    @traceable(
        name="memory.consolidate",
        run_type="chain",
        tags=["memory", "consolidation", "evernight"],
    )
    async def execute(
        self,
        scope: str,
        scope_id: str,
        reason: str,
        max_messages: int = 200,
        entries: list[dict] | None = None,
    ) -> str:
        scope_id = str(scope_id or "").strip()
        scope = str(scope or "user").strip()
        if not scope_id:
            return "Lỗi: Thiếu scope_id."

        logger.info(
            "ConsolidateMemoryTool: scope=%s scope_id=%s reason=%s max_messages=%d",
            scope, scope_id, reason, max_messages,
        )
        trace_base = {
            "workflow": "evernight.memory_consolidation",
            "workflow_step": "memory.consolidate",
            "agent_name": "evernight",
            "provider": self._provider_name(),
            "model": self._model_name(),
            "scope": scope,
            "scope_id": scope_id,
            "reason": reason,
            "max_messages": max_messages,
        }

        try:
            # 1. Source the messages. When entries are shipped over the wire
            # (A2A flow), consolidate THOSE directly — do NOT touch local T1
            # (no read, no trim), since they belong to the requesting agent.
            # Only fall back to reading local T1 when no entries are shipped
            # (Evernight's own user-scope worker path).
            if entries:
                t1_entries = await self._shipped_entries_as_t1(
                    entries,
                    trace_base,
                    langsmith_extra=langsmith_extra(
                        tags=["memory", "t1", "read", "shipped"],
                        metadata={
                            **trace_base,
                            "workflow_step": "memory.t1_read",
                            "source": "shipped_entries",
                            "count": len(entries),
                        },
                    ),
                )
                entry_ids = [
                    str(d.get("entry_id"))
                    for d in t1_entries
                    if d.get("entry_id")
                ]
            else:
                t1_entries = await self._read_t1_context(
                    scope,
                    scope_id,
                    max_messages,
                    trace_base,
                    langsmith_extra=langsmith_extra(
                        tags=["memory", "t1", "read"],
                        metadata={**trace_base, "workflow_step": "memory.t1_read"},
                    ),
                )
                entry_ids = [e.entry_id for e in t1_entries]
            if not t1_entries:
                return json.dumps({
                    "status": "skipped",
                    "reason": "no_messages",
                    "messages_summarized": 0,
                    "entry_ids": [],
                })

            messages_text = self._format_messages(t1_entries)

            # 2. Read current profile. Channel scope has no single-user profile
            # to read — scope_id is a channel id, and read_raw() would
            # auto-create memories/<channel_id>.md, which nothing ever reads
            # (recall reads by speaker user_id). Skip for channel scope.
            profile_text = ""
            if scope != "channel":
                try:
                    profile_text = await self._read_profile(
                        scope_id,
                        trace_base,
                        langsmith_extra=langsmith_extra(
                            tags=["memory", "t3", "read"],
                            metadata={**trace_base, "workflow_step": "memory.t3_profile_read"},
                        ),
                    )
                except Exception as exc:
                    logger.debug("ConsolidateMemoryTool: no profile for scope_id=%s: %s", scope_id, exc)

            # 3. LLM call with Summarizer prompt
            prompt = _SUMMARIZER_PROMPT.format(
                profile=profile_text,
                messages=messages_text,
            )
            response = await call_with_langsmith_extra(
                self.llm_service.generate_response,
                messages=[{"role": "user", "content": prompt}],
                include_tool_catalog=False,
                include_persona=False,
                max_tokens=Config.LLM_CONSOLIDATION_MAX_TOKENS,
                reasoning_effort=Config.LLM_CONSOLIDATION_REASONING_EFFORT,
                langsmith_extra=langsmith_extra(
                    tags=["memory", "consolidation", "summarizer", "llm"],
                    metadata={**trace_base, "workflow_step": "memory.summarizer"},
                ),
            )
            content = getattr(response, "content", None) or str(response)

            # 4. Parse JSON (LLM may wrap output in ```json markdown fences)
            try:
                data = json.loads(extract_json(content))
            except json.JSONDecodeError as exc:
                logger.error("ConsolidateMemoryTool: JSON parse failed: %s\nRaw: %s", exc, content[:500])
                return json.dumps({
                    "status": "failed",
                    "reason": "parse_failed",
                    "error": str(exc),
                })

            # extract_json returns "{}" when content holds no JSON object at all.
            # An empty/non-dict/garbage parse must NOT be treated as success:
            # returning status="ok" here would make the caller trim T1, deleting
            # messages that were never summarized (data loss). Require at least one
            # recognized key (new format or legacy timeline_summary) before trusting
            # it; otherwise fail → retry next poll.
            recognized = isinstance(data, dict) and any(
                k in data for k in ("has_meaningful_content", "topics", "timeline_summary")
            )
            if not recognized:
                logger.error(
                    "ConsolidateMemoryTool: empty/invalid parse, refusing to trim. Raw: %s",
                    content[:500],
                )
                return json.dumps({
                    "status": "failed",
                    "reason": "empty_parse",
                })

            # 5. Store N topic summaries in T2. Track store failures separately
            # from "nothing meaningful to store": if the session HAD meaningful
            # topics but every store attempt failed, we must NOT report success —
            # the manager trims T1 on status=="ok"+entry_ids, which would delete
            # the transcript while nothing landed in T2 (silent data loss).
            summary_ids: list[str] = []
            topics_attempted = 0
            topics_failed = 0
            has_meaningful = data.get("has_meaningful_content", True)
            topics = data.get("topics", [])

            # Fallback: old format with flat timeline_summary → wrap as single topic
            if not topics and data.get("timeline_summary"):
                topics = [{
                    "topic": "general",
                    "topic_display": "Tổng hợp",
                    "summary": data["timeline_summary"],
                    "importance": data.get("importance", 3),
                }]
                has_meaningful = bool(topics[0]["summary"])

            if has_meaningful and topics:
                for topic_item in topics:
                    t_summary = str(topic_item.get("summary", "")).strip()
                    if not t_summary:
                        continue
                    topics_attempted += 1
                    try:
                        embedding = await self._embed_summary(
                            t_summary,
                            trace_base,
                            topic_item,
                            langsmith_extra=langsmith_extra(
                                tags=["memory", "t2", "embedding"],
                                metadata={
                                    **trace_base,
                                    "workflow_step": "memory.t2_embed_summary",
                                    "topic": topic_item.get("topic", "general"),
                                },
                            ),
                        )
                        sid = await self._store_t2_summary(
                            scope_id,
                            t_summary,
                            embedding,
                            topic_item,
                            trace_base,
                            langsmith_extra=langsmith_extra(
                                tags=["memory", "t2", "store"],
                                metadata={
                                    **trace_base,
                                    "workflow_step": "memory.t2_store_summary",
                                    "topic": topic_item.get("topic", "general"),
                                    "importance": int(topic_item.get("importance", 3)),
                                },
                            ),
                        )
                        summary_ids.append(sid)
                    except Exception as exc:
                        topics_failed += 1
                        logger.warning(
                            "ConsolidateMemoryTool: timeline store failed topic=%s: %s",
                            topic_item.get("topic"), exc,
                        )
            else:
                logger.info(
                    "ConsolidateMemoryTool: session has no meaningful content — skipping T2 store (scope=%s/%s)",
                    scope, scope_id,
                )

            # 5b. Every meaningful topic failed to store → refuse to report
            # success. The manager only trims T1 on status=="ok", so returning
            # "failed" keeps the transcript intact for the next consolidation
            # attempt (avoids the silent T1-loss / empty-T2 race). Return before
            # the profile update so the retry re-applies everything atomically
            # rather than double-appending profile bullets.
            if topics_attempted > 0 and not summary_ids:
                logger.error(
                    "ConsolidateMemoryTool: all %d topic store(s) failed — "
                    "refusing to trim T1 (scope=%s/%s)",
                    topics_attempted, scope, scope_id,
                )
                return json.dumps({
                    "status": "failed",
                    "reason": "all_stores_failed",
                    "topics_attempted": topics_attempted,
                    "topics_failed": topics_failed,
                    "topics_stored": 0,
                }, ensure_ascii=False)

            # 6. Update profile T3. Channel scope has no single-user profile to
            # write — scope_id is a channel id, and appending multi-user
            # profile_updates there would pollute memories/<channel_id>.md,
            # which nothing ever reads (recall reads by speaker user_id).
            profile_updates = data.get("profile_updates", {})
            updated_sections = []
            if scope == "channel":
                logger.info("channel scope: skipping T3 profile updates")
                profile_updates = {}
            else:
                for section, bullets in profile_updates.items():
                    if not bullets:
                        continue
                    try:
                        for bullet in bullets:
                            await self._append_profile_bullet(
                                scope_id,
                                section,
                                bullet,
                                trace_base,
                                langsmith_extra=langsmith_extra(
                                    tags=["memory", "t3", "append"],
                                    metadata={
                                        **trace_base,
                                        "workflow_step": "memory.t3_profile_append",
                                        "section": section,
                                    },
                                ),
                            )
                        updated_sections.append(section)
                    except Exception as exc:
                        logger.warning(
                            "ConsolidateMemoryTool: profile update failed section=%s: %s",
                            section, exc,
                        )

            # 7. Return result. entry_ids lets the requesting agent trim exactly
            # the entries that were summarized (kept alongside the legacy
            # messages_summarized count for backward compat).
            return json.dumps({
                "status": "ok",
                "has_meaningful_content": has_meaningful,
                "topics_stored": len(summary_ids),
                "topics_failed": topics_failed,
                "summary_ids": summary_ids,
                "profile_updates": profile_updates,
                "updated_sections": updated_sections,
                "messages_summarized": len(t1_entries),
                "entry_ids": entry_ids,
            }, ensure_ascii=False)

        except Exception as exc:
            logger.error("ConsolidateMemoryTool: execution failed: %s", exc, exc_info=True)
            raise ToolExecutionError(
                self.name, f"Lỗi khi consolidate: {exc}", original_error=exc,
            )

    @staticmethod
    def _format_messages(entries: list) -> str:
        lines = []
        for entry in entries:
            # Handle both ActiveEntry objects (attributes) and shipped dicts
            # (from the A2A entries payload).
            if isinstance(entry, dict):
                role = entry.get("role") or "user"
                content = entry.get("content", "")
                author = entry.get("author_name") or role
            else:
                role = entry.role if hasattr(entry, "role") else "user"
                content = entry.content if hasattr(entry, "content") else str(entry)
                author = getattr(entry, "author_name", None) or role
            lines.append(f"[{author}]: {content}")
        return "\n".join(lines)

    @traceable(name="memory.t1_read", run_type="retriever", tags=["memory", "t1"])
    async def _read_t1_context(
        self,
        scope: str,
        scope_id: str,
        max_messages: int,
        trace_base: dict[str, Any],
    ) -> list:
        del trace_base
        return await self.memory_manager.t1.get_context(
            scope, scope_id, limit=max_messages,
        )

    @traceable(name="memory.t1_read", run_type="retriever", tags=["memory", "t1"])
    async def _shipped_entries_as_t1(
        self,
        entries: list[dict],
        trace_base: dict[str, Any],
    ) -> list[dict]:
        """Stand-in for ``_read_t1_context`` when entries arrive shipped over
        the wire (A2A flow) instead of being read from local T1. Keeps the
        same span name so the LangSmith waterfall retains its familiar shape
        even though no actual T1 read happens here.
        """
        del trace_base
        return list(entries)

    @traceable(name="memory.t3_profile_read", run_type="retriever", tags=["memory", "t3"])
    async def _read_profile(self, scope_id: str, trace_base: dict[str, Any]) -> str:
        del trace_base
        return await self.memory_manager.profile.read_raw(scope_id)

    @traceable(name="memory.t2_embed_summary", run_type="embedding", tags=["memory", "t2"])
    async def _embed_summary(
        self,
        summary: str,
        trace_base: dict[str, Any],
        topic_item: dict[str, Any],
    ) -> list[float]:
        del trace_base, topic_item
        return await self.embedding_service.get_embedding(f"{Config.EMBEDDING_PASSAGE_PREFIX}{summary}")

    @traceable(name="memory.t2_store_summary", run_type="tool", tags=["memory", "t2"])
    async def _store_t2_summary(
        self,
        scope_id: str,
        summary: str,
        embedding: list[float],
        topic_item: dict[str, Any],
        trace_base: dict[str, Any],
    ) -> str:
        del trace_base
        return await self.timeline_summary_store.store_summary(
            user_id=scope_id,
            summary=summary,
            embedding=embedding,
            topic=topic_item.get("topic", "general"),
            topic_display=topic_item.get("topic_display", ""),
            importance=int(topic_item.get("importance", 3)),
        )

    @traceable(name="memory.t3_profile_append", run_type="tool", tags=["memory", "t3"])
    async def _append_profile_bullet(
        self,
        scope_id: str,
        section: str,
        bullet: str,
        trace_base: dict[str, Any],
    ) -> bool:
        del trace_base
        return await self.memory_manager.profile.append_raw(scope_id, section, bullet)

    def _provider_name(self) -> str:
        class_name = self.llm_service.__class__.__name__ if self.llm_service else ""
        if "Gemini" in class_name:
            return "gemini"
        return "openai_compatible"

    def _model_name(self) -> str:
        return str(getattr(self.llm_service, "model", "unknown") or "unknown")
