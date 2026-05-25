import ast
import json
import logging
from datetime import datetime
from typing import Any, List

from redis.asyncio import Redis

from ..constants import SESSION_TIMEOUT_MINUTES
from ..models import MemoryEntry
from .base_storage import BaseStorage

logger = logging.getLogger(__name__)


class RedisStackStorage(BaseStorage):
    """Redis Stack JSON + Search storage for T1 Active Memory."""

    INDEX_NAME = "idx:t1:msg"
    KEY_PREFIX = "t1:msg"

    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self._ttl_seconds = SESSION_TIMEOUT_MINUTES * 60

    async def initialize(self) -> None:
        try:
            await self.redis.execute_command("FT.INFO", self.INDEX_NAME)
            return
        except Exception:
            pass

        try:
            await self.redis.execute_command(
                "FT.CREATE",
                self.INDEX_NAME,
                "ON",
                "JSON",
                "PREFIX",
                "1",
                f"{self.KEY_PREFIX}:",
                "SCHEMA",
                "$.user_id",
                "AS",
                "user_id",
                "TAG",
                "$.scope",
                "AS",
                "scope",
                "TAG",
                "$.scope_id",
                "AS",
                "scope_id",
                "TAG",
                "$.created_at_ts",
                "AS",
                "created_at_ts",
                "NUMERIC",
                "$.role",
                "AS",
                "role",
                "TAG",
                "$.entry_id",
                "AS",
                "entry_id",
                "TAG",
                "$.tokens",
                "AS",
                "tokens",
                "NUMERIC",
            )
            logger.info("RedisStackStorage: created index %s", self.INDEX_NAME)
        except Exception as e:
            raise RuntimeError(f"RedisStackStorage: FT.CREATE failed for {self.INDEX_NAME}: {e}")

    def _normalize_scope(self, scope: str, scope_id: str | None = None) -> tuple[str, str]:
        if scope_id is None:
            return "user", scope
        return scope, scope_id

    def _message_key(self, scope: str, scope_id: str, entry_id: str) -> str:
        return f"{self.KEY_PREFIX}:{scope}:{scope_id}:{entry_id}"

    def _parse_search_response(self, response: Any) -> List[str]:
        if not response:
            return []
        # NOCONTENT returns [total, key1, key2, ...]; full results include
        # [total, key1, [attrs...], key2, [attrs...], ...].
        if isinstance(response, str):
            try:
                response = ast.literal_eval(response)
            except Exception:
                return []
        if not isinstance(response, list) or len(response) < 2:
            return []
        keys: List[str] = []
        step = 2 if len(response) > 2 and isinstance(response[2], list) else 1
        for i in range(1, len(response), step):
            key = response[i]
            if isinstance(key, bytes):
                key = key.decode()
            if isinstance(key, str):
                keys.append(key)
        return keys

    async def _keys_for_scope(self, scope: str, scope_id: str) -> List[str]:
        query = f"@scope:{{{scope}}} @scope_id:{{{scope_id}}}"
        result = await self.redis.execute_command(
            "FT.SEARCH",
            self.INDEX_NAME,
            query,
            "NOCONTENT",
            "SORTBY",
            "created_at_ts",
            "ASC",
            "LIMIT",
            "0",
            "1000",
        )
        return self._parse_search_response(result)

    async def _keys_for_user(self, user_id: str) -> List[str]:
        return await self._keys_for_scope("user", user_id)

    async def save_entry(self, entry: MemoryEntry) -> None:
        payload = {
            "scope": entry.scope,
            "scope_id": entry.scope_id,
            "user_id": entry.user_id,
            "role": entry.role,
            "author_id": entry.author_id,
            "author_name": entry.author_name,
            "guild_id": entry.guild_id,
            "channel_id": entry.channel_id,
            "message_id": entry.message_id,
            "reply_to": entry.reply_to,
            "content": entry.content,
            "tokens": entry.tokens,
            "entry_id": entry.entry_id,
            "created_at": entry.timestamp.isoformat(),
            "created_at_ts": entry.timestamp.timestamp(),
        }
        key = self._message_key(entry.scope, entry.scope_id or entry.user_id, entry.entry_id)
        await self.redis.execute_command("JSON.SET", key, "$", json.dumps(payload, ensure_ascii=False))
        await self.redis.expire(key, self._ttl_seconds)

    async def get_entries(self, scope: str, scope_id: str | None = None) -> List[MemoryEntry]:
        scope, scope_id = self._normalize_scope(scope, scope_id)
        entries: List[MemoryEntry] = []
        keys = await self._keys_for_scope(scope, scope_id)

        for key in keys:
            raw = await self.redis.execute_command("JSON.GET", key)
            if not raw:
                continue
            if isinstance(raw, bytes):
                raw = raw.decode()
            data = json.loads(raw)
            entries.append(
                MemoryEntry(
                    scope=data.get("scope", scope),
                    scope_id=data.get("scope_id", scope_id),
                    user_id=data.get("user_id", scope_id if scope == "user" else data.get("author_id", "")),
                    role=data["role"],
                    author_id=data.get("author_id"),
                    author_name=data.get("author_name"),
                    guild_id=data.get("guild_id"),
                    channel_id=data.get("channel_id"),
                    message_id=data.get("message_id"),
                    reply_to=data.get("reply_to"),
                    content=data["content"],
                    tokens=int(data["tokens"]),
                    timestamp=datetime.fromisoformat(data["created_at"]),
                    entry_id=data["entry_id"],
                )
            )

        entries.sort(key=lambda x: x.timestamp)
        return entries

    async def get_total_tokens(self, scope: str, scope_id: str | None = None) -> int:
        entries = await self.get_entries(scope, scope_id)
        return sum(entry.tokens for entry in entries)

    async def delete_entries(
        self, scope: str, scope_id: str | None = None, entry_ids: List[str] | None = None
    ) -> None:
        if entry_ids is None:
            entry_ids = scope_id if isinstance(scope_id, list) else []
            scope_id = None
        if not entry_ids:
            return
        scope, scope_id = self._normalize_scope(scope, scope_id)
        keys = [self._message_key(scope, scope_id, entry_id) for entry_id in entry_ids]
        await self.redis.delete(*keys)

    async def clear_all(self, scope: str, scope_id: str | None = None) -> None:
        scope, scope_id = self._normalize_scope(scope, scope_id)
        keys = await self._keys_for_scope(scope, scope_id)
        if keys:
            await self.redis.delete(*keys)
