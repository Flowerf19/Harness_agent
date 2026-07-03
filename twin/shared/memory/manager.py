"""Agent-facing shared memory manager for T1/T2/T3."""
from __future__ import annotations

import logging
from typing import Any, Callable

from twin.shared.memory.active import ActiveEntry, ActiveMemory
from twin.shared.memory.profile import MarkdownProfileStore
from twin.shared.observability.langsmith import add_current_run_metadata, traceable

logger = logging.getLogger(__name__)


class SharedMemoryManager:
    """Bridge agent chat code to the new shared memory stack."""

    def __init__(
        self,
        *,
        active: ActiveMemory,
        profile_store: MarkdownProfileStore,
        timeline_summary_store: Any = None,
        embedding_service: Any = None,
        consolidation_client: Any = None,
        local_consolidator: Any = None,
    ) -> None:
        self.t1 = active
        self.profile = profile_store
        self.t3 = profile_store
        self.timeline_summary_store = timeline_summary_store
        self.embedding_service = embedding_service
        self.consolidation_client = consolidation_client
        self.local_consolidator = local_consolidator

    # ------------------------------------------------------------------ writes

    async def add_message(self, user_id: str, role: str, content: str) -> None:
        await self.observe_user_message(user_id=user_id, role=role, content=content)

    async def observe_user_message(self, user_id: str, role: str, content: str) -> None:
        await self.t1.observe(
            "user",
            str(user_id),
            self._normalize_role(role),
            content,
            author_id=str(user_id) if role != "assistant" else None,
            author_name=str(user_id) if role != "assistant" else None,
        )

    async def add_assistant_message(
        self,
        user_id: str,
        content: str,
        *,
        channel_id: str | None = None,
        guild_id: str | None = None,
        bot_id: str | None = None,
        bot_name: str | None = None,
    ) -> None:
        if channel_id:
            await self.t1.observe(
                "channel",
                str(channel_id),
                "assistant",
                content,
                author_id=bot_id or "march7",
                author_name=bot_name or "March7",
                guild_id=guild_id,
                channel_id=str(channel_id),
            )
            return
        await self.t1.observe(
            "user",
            str(user_id),
            "assistant",
            content,
            author_id=bot_id,
            author_name=bot_name,
        )

    async def observe_channel_message(
        self,
        guild_id: str,
        channel_id: str,
        author_id: str,
        author_name: str,
        message_id: str,
        content: str,
        reply_to: str | None = None,
    ) -> None:
        await self.t1.observe(
            "channel",
            str(channel_id),
            "user",
            content,
            author_id=str(author_id),
            author_name=author_name,
            message_id=message_id,
            guild_id=str(guild_id),
            channel_id=str(channel_id),
            reply_to=reply_to,
        )

    # ------------------------------------------------------------------- reads

    async def get_context(
        self,
        user_id: str,
        current_query: str,
        channel_id: str | None = None,
        user_name: str | None = None,
        mentioned_users: list[dict[str, Any]] | None = None,
    ) -> tuple[str, list[dict]]:
        # Decision 2026-07-03 — T2 recall is TOOL-ONLY via the search_memory
        # tool (see tools/prompts/guides/search_memory.md). Automatic T2
        # preflight injection has been removed twice already; do NOT re-add it
        # without new measured data. `current_query` stays in the signature for
        # existing callers even though nothing embeds it here anymore.
        del current_query
        scope = "channel" if channel_id else "user"
        scope_id = str(channel_id or user_id)

        entries = await self.t1.get_context(scope, scope_id)
        messages = self._entries_to_messages(entries)

        # Anchor WHO is speaking right now. In a channel the transcript carries
        # many authors, so every author line includes both display name and
        # stable platform ID. The header pins the current speaker explicitly.
        if user_name:
            user_id_header = (
                "=== CURRENT USER ===\n"
                f"Người đang nói chuyện với bạn ngay lúc này: {user_name} "
                f"(Platform user ID: {user_id})"
            )
        else:
            user_id_header = f"=== CURRENT USER ===\nPlatform user ID: {user_id}"
        if channel_id:
            # The search_memory tool recalls channel summaries via their scope
            # id (T2 stores them under user_id=channel_id) — expose the id so
            # the model can pass `channel_id` when it calls the tool.
            user_id_header += (
                f"\nĐang chat trong kênh chung (Platform channel ID: {scope_id})"
            )
        mentioned_context = await self._mentioned_users_context(
            str(user_id),
            mentioned_users,
        )
        profile_context = await self.profile.get_system_prompt_context(str(user_id))
        system_parts = [user_id_header] + [
            part
            for part in (mentioned_context, profile_context)
            if part
        ]
        return "\n\n".join(system_parts), messages

    async def get_snapshot(self, user_id: str) -> list[dict]:
        entries = await self.t1.get_context("user", str(user_id), limit=200)
        return [self._entry_to_snapshot(e) for e in entries]

    async def clear_session(self, user_id: str) -> None:
        await self.t1.reset_scope("user", str(user_id))

    # -------------------------------------------------------------- consolidate

    @traceable(
        name="memory.request_consolidation",
        run_type="chain",
        tags=["memory", "consolidation", "request"],
    )
    async def consolidate_scope(
        self,
        scope: str,
        scope_id: str,
        entries: list[dict] | None = None,
    ) -> dict:
        """Consolidate T1 messages, then trim on success.

        Uses the remote A2A client if configured (March7 → Evernight), else a
        local consolidator if set (Evernight worker), else fails.

        On the A2A path the caller's OWN T1 entries are shipped over the wire so
        Evernight consolidates this agent's messages (not its own T1, which is
        empty for this agent's scopes). ``entries`` may be supplied directly by a
        payload that already carries them; otherwise we read them here.
        """
        if self.consolidation_client is not None:
            if entries is None:
                t1_entries = await self.t1.get_context(scope, scope_id, limit=200)
                entries = [self._entry_to_snapshot(e) for e in t1_entries]
            logger.info(
                "Consolidating via A2A client scope=%s/%s entries=%d",
                scope, scope_id, len(entries),
            )
            result_dict = await self.consolidation_client.consolidate_scope(
                scope=scope,
                scope_id=scope_id,
                reason="auto",
                entries=entries,
            )
        elif self.local_consolidator is not None:
            logger.info(
                "Consolidating locally scope=%s/%s", scope, scope_id,
            )
            result_dict = await self.local_consolidator(
                scope=scope,
                scope_id=scope_id,
                reason="auto",
                entries=entries,
            )
        else:
            logger.error("No consolidator configured (neither client nor local)")
            add_current_run_metadata({
                "entries_shipped": len(entries or []),
                "trimmed": 0,
                "trim_skipped_reason": "no_consolidator_configured",
            })
            return {"status": "failed", "scope": scope, "scope_id": scope_id, "error": "consolidator not configured"}

        # Trim T1 by the EXACT entry_ids the consolidator summarized. Trimming by
        # count (the old path) could delete entries that were never summarized —
        # a remote agent's own T1, or messages that raced in mid-consolidation.
        # If no entry_ids came back, skip trimming rather than risk data loss.
        trimmed = 0
        trim_skipped_reason: str | None = None
        if result_dict.get("status") == "ok":
            entry_ids = result_dict.get("entry_ids")
            if entry_ids:
                await self.t1.trim(scope, scope_id, entry_ids)
                trimmed = len(entry_ids)
                logger.info(
                    "Trimmed T1 after consolidation: %d entries", trimmed,
                )
            else:
                trim_skipped_reason = "no_entry_ids"
                logger.warning(
                    "Consolidation ok but no entry_ids returned scope=%s/%s — "
                    "skipping trim to avoid deleting un-summarized entries",
                    scope, scope_id,
                )
        else:
            trim_skipped_reason = f"status_{result_dict.get('status')}"

        add_current_run_metadata({
            "entries_shipped": len(entries or []),
            "trimmed": trimmed,
            "trim_skipped_reason": trim_skipped_reason,
        })
        return result_dict

    async def consolidate_snapshot(
        self,
        user_id: str,
        snapshot: list[dict],
        reason: str = "manual",
    ) -> bool:
        del reason
        for item in snapshot or []:
            role = self._normalize_role(str(item.get("role") or "user"))
            content = str(item.get("content") or "")
            if not content.strip():
                continue
            await self.t1.observe(
                "user",
                str(user_id),
                role,
                content,
                author_id=str(user_id) if role == "user" else None,
                author_name=str(user_id) if role == "user" else None,
                message_id=str(item.get("message_id") or item.get("id") or "") or None,
            )
        result = await self.consolidate_scope("user", str(user_id))
        return result.get("status") in {"ok", "skipped"}

    # ---------------------------------------------------------------- helpers

    async def _mentioned_users_context(
        self,
        current_user_id: str,
        mentioned_users: list[dict[str, Any]] | None,
    ) -> str:
        users = self._normalize_mentioned_users(current_user_id, mentioned_users)
        if not users:
            return ""

        lines = [
            "=== MENTIONED USERS ===",
            "Những người được nhắc tới trong tin nhắn hiện tại. "
            "Đây không phải người đang nói, trừ khi trùng với CURRENT USER.",
        ]
        for user in users:
            user_id = user["user_id"]
            display_name = user.get("display_name") or user_id
            lines.append(f"- {display_name} (Platform user ID: {user_id})")
            for bullet in await self._mentioned_user_basic_bullets(user_id):
                lines.append(f"  - {bullet}")
        return "\n".join(lines)

    async def _mentioned_user_basic_bullets(self, user_id: str) -> list[str]:
        reader = getattr(self.profile, "read_section_if_exists", None)
        if reader is None:
            return []
        try:
            bullets = await reader(str(user_id), "basic")
        except Exception as exc:
            logger.debug("T3: mentioned profile read failed user=%s: %s", user_id, exc)
            return []
        return list(bullets[:3])

    @staticmethod
    def _normalize_mentioned_users(
        current_user_id: str,
        mentioned_users: list[dict[str, Any]] | None,
    ) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in mentioned_users or []:
            raw_id = item.get("user_id") or item.get("platform_id")
            user_id = str(raw_id or "").strip()
            if not user_id or user_id == current_user_id or user_id in seen:
                continue
            seen.add(user_id)
            display_name = str(item.get("display_name") or "").strip()
            normalized.append({"user_id": user_id, "display_name": display_name})
        return normalized

    @staticmethod
    def _normalize_role(role: str) -> str:
        if role == "assistant":
            return "assistant"
        if role == "system":
            return "system"
        return "user"

    @staticmethod
    def _entries_to_messages(entries: list[ActiveEntry]) -> list[dict]:
        messages: list[dict] = []
        for entry in entries:
            role = "assistant" if entry.role == "assistant" else "user"
            content = entry.content
            if entry.role == "assistant":
                lowered = content.lower()
                # Only mark prior assistant turns that look like host-state
                # output — narrow tokens avoid over-marking casual chat. The
                # marker nudges the LLM to re-call host_system instead of reusing
                # stale numbers when the user asks again about realtime host.
                if any(
                    token in lowered
                    for token in (
                        "uptime",
                        "load average",
                        "df -h",
                        "docker ps",
                        "docker logs",
                        "container",
                        "systemctl",
                    )
                ):
                    content = (
                        "[context cũ — số liệu host có thể stale; nếu user hỏi lại trạng thái host BẮT BUỘC gọi host_system lại] "
                        + content
                    )
            if entry.scope == "channel" and entry.role == "user" and entry.author_name:
                label = entry.author_name
                if entry.author_id:
                    label = f"{label} [user_id={entry.author_id}]"
                content = f"{label}: {content}"
            messages.append({"role": role, "content": content})
        return messages

    @staticmethod
    def _entry_to_snapshot(entry: ActiveEntry) -> dict:
        return {
            "entry_id": entry.entry_id,
            "message_id": entry.message_id,
            "role": entry.role,
            "content": entry.content,
            "author_id": entry.author_id,
            "author_name": entry.author_name,
            "timestamp": entry.created_at.isoformat(),
        }
