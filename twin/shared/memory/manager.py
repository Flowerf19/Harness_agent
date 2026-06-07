"""Agent-facing shared memory manager for T1/T2/T3."""
from __future__ import annotations

import logging
from typing import Any

from twin.shared.memory.active import ActiveEntry, ActiveMemory
from twin.shared.memory.profile import MarkdownProfileStore
from twin.shared.memory.timeline import (
    ConsolidationResult,
    TimelineSearch,
    format_preflight_for_prompt,
)

logger = logging.getLogger(__name__)


class SharedMemoryManager:
    """Bridge agent chat code to the new shared memory stack."""

    def __init__(
        self,
        *,
        active: ActiveMemory,
        profile_store: MarkdownProfileStore,
        timeline_search: TimelineSearch | None = None,
        consolidator: Any = None,
    ) -> None:
        self.t1 = active
        self.profile = profile_store
        self.t3 = profile_store
        self.timeline_search = timeline_search
        self.consolidator = consolidator

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
        scope = "channel" if channel_id else "user"
        scope_id = str(channel_id or user_id)

        entries = await self.t1.get_context(scope, scope_id)
        messages = self._entries_to_messages(entries)

        # Anchor WHO is speaking right now. In a channel the transcript carries
        # many authors (each line prefixed "name: ..."), so a bare numeric ID
        # leaves the model guessing — it would grab whatever name is salient and
        # mis-attribute the turn. The display name ties the ID to the live
        # speaker and matches the transcript's author prefix.
        if user_name:
            user_id_header = (
                "=== CURRENT USER ===\n"
                f"Người đang nói chuyện với bạn ngay lúc này: {user_name} "
                f"(Platform user ID: {user_id})"
            )
        else:
            user_id_header = f"=== CURRENT USER ===\nPlatform user ID: {user_id}"
        mentioned_context = await self._mentioned_users_context(
            str(user_id),
            mentioned_users,
        )
        profile_context = await self.profile.get_system_prompt_context(str(user_id))
        t2_context = await self._preflight_context(str(user_id), current_query)
        system_parts = [user_id_header] + [
            part
            for part in (mentioned_context, profile_context, t2_context)
            if part
        ]
        return "\n\n".join(system_parts), messages

    async def get_snapshot(self, user_id: str) -> list[dict]:
        entries = await self.t1.get_context("user", str(user_id), limit=200)
        return [self._entry_to_snapshot(e) for e in entries]

    async def clear_session(self, user_id: str) -> None:
        await self.t1.reset_scope("user", str(user_id))

    # -------------------------------------------------------------- consolidate

    async def consolidate_scope(self, scope: str, scope_id: str) -> dict:
        if self.consolidator is None:
            logger.warning("T2: no consolidator configured for scope=%s/%s", scope, scope_id)
            return {"status": "failed", "scope": scope, "scope_id": scope_id, "error": "consolidator not configured"}

        # Both scopes extract once. For a channel the consolidator routes each
        # memory to the participant it is about (no per-user fan-out), so facts
        # never leak across profiles.
        result = await self.consolidator.consolidate(scope=scope, scope_id=scope_id)
        await self._trim_if_complete(result)
        return self._result_to_dict(result)

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

    async def consolidate_payload(self, payload: dict) -> dict:
        scope = str(payload.get("scope") or "user")
        scope_id = str(payload.get("scope_id") or payload.get("user_id") or "")
        if not scope_id:
            return {"status": "failed", "scope": scope, "scope_id": scope_id, "error": "scope_id required"}
        for item in payload.get("entries") or []:
            content = str(item.get("content") or "")
            if not content.strip():
                continue
            await self.t1.observe(
                scope,
                scope_id,
                self._normalize_role(str(item.get("role") or "user")),
                content,
                author_id=item.get("author_id") or item.get("user_id"),
                author_name=item.get("author_name"),
                message_id=item.get("message_id") or item.get("entry_id"),
                guild_id=payload.get("guild_id") or item.get("guild_id"),
                channel_id=payload.get("channel_id") or item.get("channel_id"),
                reply_to=item.get("reply_to"),
            )
        return await self.consolidate_scope(scope, scope_id)

    # ---------------------------------------------------------------- helpers

    async def _preflight_context(self, user_id: str, current_query: str) -> str:
        if self.timeline_search is None or not current_query:
            return ""
        try:
            memories = await self.timeline_search.preflight(user_id, current_query)
            return format_preflight_for_prompt(memories)
        except Exception as exc:
            logger.debug("T2: preflight failed user=%s: %s", user_id, exc)
            return ""

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
            if entry.scope == "channel" and entry.role == "user" and entry.author_name:
                content = f"{entry.author_name}: {content}"
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

    async def _trim_if_complete(self, result: ConsolidationResult) -> None:
        if result.status not in {"ok", "skipped"}:
            return
        if not result.scope or not result.scope_id:
            return
        await self.t1.trim(
            result.scope,
            result.scope_id,
            result.summarized_entry_ids,
        )

    @staticmethod
    def _result_to_dict(result: ConsolidationResult) -> dict:
        return {
            "status": result.status,
            "scope": result.scope,
            "scope_id": result.scope_id,
            "summarized_entry_ids": result.summarized_entry_ids,
            "memory_ids": result.memory_ids,
            "topic_ids": result.topic_ids,
            "promoted_to_t3": result.promoted_to_t3,
            "primary_catalog": result.primary_catalog,
            "primary_confidence": result.primary_confidence,
            "error": result.error,
        }
