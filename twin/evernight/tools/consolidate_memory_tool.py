"""ConsolidateMemoryTool - Evernight tool to consolidate T1 into T2/T3."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from twin.shared.tools.registry.base import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)

_SUMMARIZER_PROMPT = """Bạn là Memory Summarizer. Đọc cuộc trò chuyện và trích xuất thông tin đáng nhớ.

=== HỒ SƠ HIỆN TẠI ===
{profile}

=== TIN NHẮN GẦN ĐÂY ===
{messages}

Nhiệm vụ:
1. Tóm tắt cuộc trò chuyện (2-3 câu, tập trung vào topics chính)
2. Trích xuất facts mới đáng lưu vào hồ sơ
3. Nếu fact mới mâu thuẫn với hồ sơ cũ → ghi đè
4. Nếu fact mới đã có trong hồ sơ → bỏ qua

Return JSON:
{{
  "timeline_summary": "User nói về...",
  "profile_updates": {{
    "basic": [],
    "work": ["Đang làm dự án X"],
    "interest": ["Thích Rust"],
    "relationship": [],
    "habit": [],
    "psychological": [],
    "rules": [],
    "contact": []
  }},
  "importance": 4
}}

Rules:
- importance 5: identity/contact critical
- importance 4: work/relationship/habit quan trọng  
- importance 3: interest/event thông thường
- importance 2-1: casual, temporary

Chỉ return JSON, không giải thích."""


class ConsolidateMemoryTool(BaseTool):
    """Evernight tool: consolidate T1 messages into T2 timeline + T3 profile."""

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
            },
            "required": ["scope_id", "reason"],
        }

    @property
    def visible_to_agents(self) -> Optional[set[str]]:
        return {"evernight"}

    async def execute(
        self,
        scope: str,
        scope_id: str,
        reason: str,
        max_messages: int = 200,
    ) -> str:
        scope_id = str(scope_id or "").strip()
        scope = str(scope or "user").strip()
        if not scope_id:
            return "Lỗi: Thiếu scope_id."

        logger.info(
            "ConsolidateMemoryTool: scope=%s scope_id=%s reason=%s max_messages=%d",
            scope, scope_id, reason, max_messages,
        )

        try:
            # 1. Read T1 messages
            t1_entries = await self.memory_manager.t1.get_context(
                scope, scope_id, limit=max_messages,
            )
            if not t1_entries:
                return json.dumps({
                    "status": "skipped",
                    "reason": "no_messages",
                    "messages_summarized": 0,
                })

            messages_text = self._format_messages(t1_entries)

            # 2. Read current profile (channel scope may not have profile)
            profile_text = ""
            try:
                profile_text = await self.memory_manager.profile.read_raw(scope_id)
            except Exception as exc:
                logger.debug("ConsolidateMemoryTool: no profile for scope_id=%s: %s", scope_id, exc)

            # 3. LLM call with Summarizer prompt
            prompt = _SUMMARIZER_PROMPT.format(
                profile=profile_text,
                messages=messages_text,
            )
            response = await self.llm_service.generate_response(
                messages=[{"role": "user", "content": prompt}],
            )
            content = getattr(response, "content", None) or str(response)

            # 4. Parse JSON
            try:
                data = json.loads(content)
            except json.JSONDecodeError as exc:
                logger.error("ConsolidateMemoryTool: JSON parse failed: %s", exc)
                return json.dumps({
                    "status": "failed",
                    "reason": "parse_failed",
                    "error": str(exc),
                })

            timeline_summary = data.get("timeline_summary", "")
            profile_updates = data.get("profile_updates", {})
            importance = data.get("importance", 3)

            # 5. Store timeline summary in T2
            summary_id = None
            if timeline_summary:
                try:
                    embedding = await self.embedding_service.get_embedding(timeline_summary)
                    summary_id = await self.timeline_summary_store.store_summary(
                        user_id=scope_id,
                        content=timeline_summary,
                        embedding=embedding,
                        importance=importance,
                    )
                except Exception as exc:
                    logger.warning("ConsolidateMemoryTool: timeline store failed: %s", exc)

            # 6. Update profile T3
            updated_sections = []
            for section, bullets in profile_updates.items():
                if not bullets:
                    continue
                try:
                    for bullet in bullets:
                        await self.memory_manager.profile.append_raw(
                            scope_id, section, bullet,
                        )
                    updated_sections.append(section)
                except Exception as exc:
                    logger.warning(
                        "ConsolidateMemoryTool: profile update failed section=%s: %s",
                        section, exc,
                    )

            # 7. Return result
            return json.dumps({
                "status": "ok",
                "timeline_summary": timeline_summary,
                "summary_id": summary_id,
                "profile_updates": profile_updates,
                "updated_sections": updated_sections,
                "messages_summarized": len(t1_entries),
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
            role = entry.role if hasattr(entry, "role") else "user"
            content = entry.content if hasattr(entry, "content") else str(entry)
            author = getattr(entry, "author_name", None) or role
            lines.append(f"[{author}]: {content}")
        return "\n".join(lines)
