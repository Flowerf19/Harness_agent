"""Redis JSON-backed scope-aware store for T1 active memory."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from twin.shared.memory.active.models import ActiveEntry

logger = logging.getLogger(__name__)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class ActiveStore:
    """Redis JSON-backed store, scope-aware (user|channel).

    Keys:
      entry: ``active:{scope}:{scope_id}:{entry_id}`` (JSON document)
      state: ``active_state:{scope}:{scope_id}`` (HASH)
      index: ``active_index:{scope}:{scope_id}`` (ZSET ts -> entry_id)
    """

    def __init__(self, redis_client) -> None:
        self.redis = redis_client

    @staticmethod
    def _entry_key(scope: str, scope_id: str, entry_id: str) -> str:
        return f"active:{scope}:{scope_id}:{entry_id}"

    @staticmethod
    def _state_key(scope: str, scope_id: str) -> str:
        return f"active_state:{scope}:{scope_id}"

    @staticmethod
    def _index_key(scope: str, scope_id: str) -> str:
        return f"active_index:{scope}:{scope_id}"

    async def save(self, entry: ActiveEntry) -> None:
        key = self._entry_key(entry.scope, entry.scope_id, entry.entry_id)
        payload = json.dumps(entry.model_dump(mode="json"), ensure_ascii=False, default=_json_default)
        await self.redis.execute_command("JSON.SET", key, "$", payload)
        await self.redis.zadd(
            self._index_key(entry.scope, entry.scope_id),
            {entry.entry_id: entry.created_at.timestamp()},
        )
        logger.debug("T1: saved entry %s scope=%s/%s", entry.entry_id, entry.scope, entry.scope_id)

    async def list_entries(
        self, scope: str, scope_id: str, limit: int = 50
    ) -> list[ActiveEntry]:
        # Read the `limit` most-recent entries (ZSET ordered by ascending ts),
        # then keep chronological order. Reading the head would pin the window
        # to the oldest messages once a scope exceeds `limit`.
        ids = await self.redis.zrange(self._index_key(scope, scope_id), -limit, -1)
        entries: list[ActiveEntry] = []
        for raw_id in ids:
            entry_id = raw_id.decode() if isinstance(raw_id, bytes) else raw_id
            data = await self._load_entry(scope, scope_id, entry_id)
            if data is not None:
                entries.append(data)
        return entries

    async def _load_entry(
        self, scope: str, scope_id: str, entry_id: str
    ) -> ActiveEntry | None:
        raw = await self.redis.execute_command(
            "JSON.GET", self._entry_key(scope, scope_id, entry_id)
        )
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode()
        return ActiveEntry.model_validate(json.loads(raw))

    async def delete_entries(
        self, scope: str, scope_id: str, entry_ids: list[str]
    ) -> None:
        if not entry_ids:
            return
        keys = [self._entry_key(scope, scope_id, eid) for eid in entry_ids]
        await self.redis.delete(*keys)
        await self.redis.zrem(self._index_key(scope, scope_id), *entry_ids)
        logger.debug("T1: deleted %d entries scope=%s/%s", len(entry_ids), scope, scope_id)

    async def clear_scope(self, scope: str, scope_id: str) -> None:
        entries = await self.list_entries(scope, scope_id, limit=10_000)
        if entries:
            await self.delete_entries(scope, scope_id, [e.entry_id for e in entries])
        await self.redis.delete(self._index_key(scope, scope_id))
        await self.reset_state(scope, scope_id, keep_recent_catalogs=False)

    async def list_active_scope_ids(self, scope: str) -> list[str]:
        pattern = self._state_key(scope, "*")
        if not hasattr(self.redis, "scan_iter"):
            return []
        active: list[str] = []
        prefix = self._state_key(scope, "")
        async for raw_key in self.redis.scan_iter(match=pattern):
            key = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
            scope_id = key[len(prefix):]
            state = await self.get_state(scope, scope_id)
            if int(state.get("unsummarized_tokens") or 0) > 0:
                active.append(scope_id)
        return active

    async def get_state(self, scope: str, scope_id: str) -> dict:
        raw = await self.redis.hgetall(self._state_key(scope, scope_id))
        if not raw:
            return {
                "unsummarized_tokens": 0,
                "last_entry_ts": None,
                "recent_catalogs": [],
            }
        decoded = {
            (k.decode() if isinstance(k, bytes) else k): (
                v.decode() if isinstance(v, bytes) else v
            )
            for k, v in raw.items()
        }
        return {
            "unsummarized_tokens": int(decoded.get("unsummarized_tokens", 0) or 0),
            "last_entry_ts": float(decoded["last_entry_ts"])
            if decoded.get("last_entry_ts")
            else None,
            "recent_catalogs": json.loads(decoded.get("recent_catalogs") or "[]"),
        }

    async def update_state(
        self,
        scope: str,
        scope_id: str,
        *,
        unsummarized_tokens: int | None = None,
        recent_catalogs: list[str] | None = None,
        last_entry_ts: float | None = None,
    ) -> None:
        updates: dict[str, str] = {}
        if unsummarized_tokens is not None:
            updates["unsummarized_tokens"] = str(int(unsummarized_tokens))
        if recent_catalogs is not None:
            updates["recent_catalogs"] = json.dumps(recent_catalogs, ensure_ascii=False)
        if last_entry_ts is not None:
            updates["last_entry_ts"] = str(float(last_entry_ts))
        if not updates:
            return
        await self.redis.hset(self._state_key(scope, scope_id), mapping=updates)

    async def reset_state(
        self, scope: str, scope_id: str, *, keep_recent_catalogs: bool = True
    ) -> None:
        current = await self.get_state(scope, scope_id)
        await self.redis.delete(self._state_key(scope, scope_id))
        if keep_recent_catalogs and current.get("recent_catalogs"):
            await self.update_state(
                scope, scope_id, recent_catalogs=current["recent_catalogs"]
            )
