# src/services/memories/activate_memory/storage/redis_storage.py
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool

from ..constants import SESSION_TIMEOUT_MINUTES
from ..models import MemoryEntry
from .base_storage import BaseStorage

logger = logging.getLogger(__name__)


class RedisStorage(BaseStorage):
    """Redis-based storage for T1 Active Memory."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        redis_password: Optional[str] = None,
        redis_db: int = 0,
    ):
        self._pool: ConnectionPool = ConnectionPool.from_url(
            redis_url,
            password=redis_password,
            db=redis_db,
            decode_responses=True,
            max_connections=10,
        )
        self._redis: Redis = Redis(connection_pool=self._pool)
        self._ttl_seconds = SESSION_TIMEOUT_MINUTES * 60

        logger.debug(f"🔴 RedisStorage: Initialized with TTL={SESSION_TIMEOUT_MINUTES}min")

    @property
    def redis(self) -> Redis:
        """Expose the underlying Redis client for direct access."""
        return self._redis

    async def close(self) -> None:
        """Close Redis connection pool gracefully."""
        await self._redis.close()
        await self._pool.disconnect()
        logger.debug("🔴 RedisStorage: Connection pool closed")

    async def health_check(self) -> bool:
        """Check if Redis connection is healthy."""
        try:
            await self._redis.ping()
            return True
        except redis.RedisError as e:
            logger.warning(f"🔴 RedisStorage: Health check failed - {e}")
            return False

    # === Helper Methods ===

    def _normalize_scope(self, scope: str, scope_id: str | None = None) -> tuple[str, str]:
        if scope_id is None:
            return "user", scope
        return scope, scope_id

    def _get_redis_key(self, scope: str, scope_id: str | None = None) -> str:
        """Generate Redis key for scoped memory entries."""
        scope, scope_id = self._normalize_scope(scope, scope_id)
        return f"active_memory:{scope}:{scope_id}"

    def _get_utc_now_iso(self) -> str:
        """Get current UTC datetime as ISO string."""
        return datetime.now(timezone.utc).isoformat()

    def _entry_to_message_dict(self, entry: MemoryEntry) -> Dict[str, Any]:
        """Convert MemoryEntry to dict for storage."""
        return {
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
            "timestamp": entry.timestamp.isoformat(),
            "entry_id": entry.entry_id,
        }

    def _message_dict_to_entry(self, msg: Dict[str, Any], scope: str, scope_id: str) -> MemoryEntry:
        """Reconstruct MemoryEntry from stored dict."""
        return MemoryEntry(
            scope=msg.get("scope", scope),
            scope_id=msg.get("scope_id", scope_id),
            user_id=msg.get("user_id", scope_id if scope == "user" else msg.get("author_id", "")),
            role=msg["role"],
            author_id=msg.get("author_id"),
            author_name=msg.get("author_name"),
            guild_id=msg.get("guild_id"),
            channel_id=msg.get("channel_id"),
            message_id=msg.get("message_id"),
            reply_to=msg.get("reply_to"),
            content=msg["content"],
            tokens=msg["tokens"],
            timestamp=datetime.fromisoformat(msg["timestamp"]),
            entry_id=msg["entry_id"],
        )

    async def _reset_ttl(self, scope: str, scope_id: str | None = None) -> None:
        """Reset TTL for scope key on new activity."""
        key = self._get_redis_key(scope, scope_id)
        await self._redis.expire(key, self._ttl_seconds)

    # === BaseStorage Interface Implementation ===

    async def save_entry(self, entry: MemoryEntry) -> None:
        """Save a new message entry to Redis HASH."""
        key = self._get_redis_key(entry.scope, entry.scope_id)

        current = await self._redis.hgetall(key)
        now_iso = self._get_utc_now_iso()

        if current:
            messages = json.loads(current.get("messages", "[]"))
            total_tokens = int(current.get("total_tokens", 0))
            started_at = current.get("started_at", now_iso)
        else:
            messages = []
            total_tokens = 0
            started_at = now_iso

        messages.append(self._entry_to_message_dict(entry))
        total_tokens += entry.tokens

        await self._redis.hset(
            key,
            mapping={
                "messages": json.dumps(messages),
                "total_tokens": str(total_tokens),
                "started_at": started_at,
                "last_activity": now_iso,
            },
        )

        await self._reset_ttl(entry.scope, entry.scope_id)

        logger.debug(
            f"📥 RedisStorage: Saved entry ({entry.scope}:{entry.scope_id} | Tokens: {entry.tokens})"
        )

    async def get_entries(self, scope: str, scope_id: str | None = None) -> List[MemoryEntry]:
        """Retrieve all entries for a scope."""
        scope, scope_id = self._normalize_scope(scope, scope_id)
        key = self._get_redis_key(scope, scope_id)
        messages_json = await self._redis.hget(key, "messages")

        if not messages_json:
            return []

        messages = json.loads(messages_json)
        entries = [self._message_dict_to_entry(msg, scope, scope_id) for msg in messages]

        logger.debug(f"📤 RedisStorage: Retrieved {len(entries)} entries ({scope}:{scope_id})")
        return entries

    async def get_total_tokens(self, scope: str, scope_id: str | None = None) -> int:
        """Get total tokens for a scope - O(1) via HASH field."""
        key = self._get_redis_key(scope, scope_id)
        total = await self._redis.hget(key, "total_tokens")

        if total is None:
            return 0

        return int(total)

    async def delete_entries(
        self, scope: str, scope_id: str | None = None, entry_ids: List[str] | None = None
    ) -> None:
        """Delete specific entries by entry_id."""
        if entry_ids is None:
            entry_ids = scope_id if isinstance(scope_id, list) else []
            scope_id = None
        scope, scope_id = self._normalize_scope(scope, scope_id)
        key = self._get_redis_key(scope, scope_id)
        current = await self._redis.hgetall(key)

        if not current:
            return

        messages = json.loads(current.get("messages", "[]"))
        ids_to_remove = set(entry_ids)

        kept_messages = []
        deleted_tokens = 0

        for msg in messages:
            if msg.get("entry_id") in ids_to_remove:
                deleted_tokens += msg.get("tokens", 0)
            else:
                kept_messages.append(msg)

        if not kept_messages:
            await self._redis.delete(key)
            return

        new_total = max(0, int(current.get("total_tokens", 0)) - deleted_tokens)

        await self._redis.hset(
            key,
            mapping={
                "messages": json.dumps(kept_messages),
                "total_tokens": str(new_total),
                "last_activity": self._get_utc_now_iso(),
            },
        )
        await self._reset_ttl(scope, scope_id)

        logger.debug(f"🗑️ RedisStorage: Deleted entries ({scope}:{scope_id})")

    async def clear_all(self, scope: str, scope_id: str | None = None) -> None:
        """Clear all entries for a scope."""
        scope, scope_id = self._normalize_scope(scope, scope_id)
        key = self._get_redis_key(scope, scope_id)
        await self._redis.delete(key)
        logger.debug(f"🧹 RedisStorage: Cleared all ({scope}:{scope_id})")


def create_redis_storage(
    redis_url: str,
    redis_password: Optional[str] = None,
    redis_db: int = 0,
) -> RedisStorage:
    """Factory function to create RedisStorage instance."""
    return RedisStorage(
        redis_url=redis_url,
        redis_password=redis_password,
        redis_db=redis_db,
    )
