"""Redis Stack VECTOR HNSW timeline store for T2 memories + topics."""
from __future__ import annotations

import json
import logging
import struct
from datetime import datetime, timezone
from typing import Any

from twin.shared.memory.timeline.constants import EMBEDDING_DIM
from twin.shared.memory.timeline.models import (
    T2Memory,
    T2Topic,
    expires_at_for_importance,
    get_ttl_by_importance,
    topic_expires_at_for_importance,
    topic_ttl_for_importance,
    utc_now,
)

logger = logging.getLogger(__name__)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _pack_vec(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _to_ts(dt: datetime | None) -> float:
    if dt is None:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _decode(val: Any) -> str:
    if isinstance(val, bytes):
        return val.decode()
    return val


# Characters with special meaning inside a RediSearch TAG value clause —
# they must be backslash-escaped or the parser raises a syntax error.
_TAG_SPECIALS = set(" ,.<>{}[]\"':;!@#$%^&*()-+=~/\\?|")


def _escape_tag(value: str) -> str:
    out: list[str] = []
    for ch in value:
        if ch in _TAG_SPECIALS:
            out.append("\\")
        out.append(ch)
    return "".join(out)


class TimelineStore:
    TOPIC_PREFIX = "t2:topic"
    MEM_PREFIX = "t2:mem"
    TOPIC_INDEX = "idx:t2:topic"
    MEM_INDEX = "idx:t2:mem"

    def __init__(
        self,
        redis_client,
        *,
        vector_dim: int = EMBEDDING_DIM,
        topic_prefix: str | None = None,
        mem_prefix: str | None = None,
        topic_index: str | None = None,
        mem_index: str | None = None,
    ) -> None:
        self.redis = redis_client
        self.dim = vector_dim
        if topic_prefix is not None:
            self.TOPIC_PREFIX = topic_prefix
        if mem_prefix is not None:
            self.MEM_PREFIX = mem_prefix
        if topic_index is not None:
            self.TOPIC_INDEX = topic_index
        if mem_index is not None:
            self.MEM_INDEX = mem_index

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def initialize(self) -> None:
        await self._create_topic_index()
        await self._create_memory_index()

    async def _index_exists(self, index_name: str) -> bool:
        try:
            await self.redis.execute_command("FT.INFO", index_name)
            return True
        except Exception:
            return False

    async def _create_topic_index(self) -> None:
        if await self._index_exists(self.TOPIC_INDEX):
            return
        try:
            await self.redis.execute_command(
                "FT.CREATE", self.TOPIC_INDEX,
                "ON", "JSON",
                "PREFIX", "1", f"{self.TOPIC_PREFIX}:",
                "SCHEMA",
                "$.user_id", "AS", "user_id", "TAG",
                "$.name", "AS", "name", "TEXT",
                "$.aliases[*]", "AS", "aliases", "TEXT",
                "$.catalogs[*]", "AS", "catalogs", "TAG",
                "$.last_accessed_ts", "AS", "last_accessed", "NUMERIC", "SORTABLE",
                "$.importance", "AS", "importance", "NUMERIC",
                "$.expires_at_ts", "AS", "expires_at", "NUMERIC",
                "$.embedding", "AS", "embedding",
                "VECTOR", "HNSW", "6",
                "TYPE", "FLOAT32",
                "DIM", str(self.dim),
                "DISTANCE_METRIC", "COSINE",
            )
            logger.info("T2: created index %s", self.TOPIC_INDEX)
        except Exception as exc:
            msg = str(exc).lower()
            if "already exists" in msg or "exists" in msg:
                return
            raise

    async def _create_memory_index(self) -> None:
        if await self._index_exists(self.MEM_INDEX):
            return
        try:
            await self.redis.execute_command(
                "FT.CREATE", self.MEM_INDEX,
                "ON", "JSON",
                "PREFIX", "1", f"{self.MEM_PREFIX}:",
                "SCHEMA",
                "$.user_id", "AS", "user_id", "TAG",
                "$.topic_ids[*]", "AS", "topic_ids", "TAG",
                "$.catalogs[*]", "AS", "catalogs", "TAG",
                "$.change_type", "AS", "change_type", "TAG",
                "$.superseded_by_idx", "AS", "superseded_by", "TAG",
                "$.speaker", "AS", "speaker", "TAG",
                "$.importance", "AS", "importance", "NUMERIC",
                "$.created_at_ts", "AS", "created_at", "NUMERIC", "SORTABLE",
                "$.last_accessed_ts", "AS", "last_accessed", "NUMERIC", "SORTABLE",
                "$.expires_at_ts", "AS", "expires_at", "NUMERIC",
                "$.embedding", "AS", "embedding",
                "VECTOR", "HNSW", "6",
                "TYPE", "FLOAT32",
                "DIM", str(self.dim),
                "DISTANCE_METRIC", "COSINE",
            )
            logger.info("T2: created index %s", self.MEM_INDEX)
        except Exception as exc:
            msg = str(exc).lower()
            if "already exists" in msg or "exists" in msg:
                return
            raise

    # ------------------------------------------------------------------
    # Keys
    # ------------------------------------------------------------------
    def topic_key(self, user_id: str, topic_id: str) -> str:
        return f"{self.TOPIC_PREFIX}:{user_id}:{topic_id}"

    def mem_key(self, user_id: str, memory_id: str) -> str:
        return f"{self.MEM_PREFIX}:{user_id}:{memory_id}"

    # ------------------------------------------------------------------
    # JSON write helper
    # ------------------------------------------------------------------
    @staticmethod
    def _topic_payload(t: T2Topic) -> dict:
        data = t.model_dump(mode="json")
        data["created_at_ts"] = _to_ts(t.created_at)
        data["last_accessed_ts"] = _to_ts(t.last_accessed)
        data["expires_at_ts"] = _to_ts(t.expires_at)
        return data

    @staticmethod
    def _memory_payload(m: T2Memory) -> dict:
        data = m.model_dump(mode="json")
        data["created_at_ts"] = _to_ts(m.created_at)
        data["last_accessed_ts"] = _to_ts(m.last_accessed)
        data["expires_at_ts"] = _to_ts(m.expires_at)
        # Index sentinel so `-@superseded_by:{_active}` excludes live memories
        # and `@superseded_by:{_active}` selects them — RediSearch 2.8 lacks
        # ismissing() so we cannot rely on null absence alone.
        data["superseded_by_idx"] = m.superseded_by or "_active"
        return data

    async def _write_json(self, key: str, payload: dict, expires_at: datetime) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=_json_default)
        await self.redis.execute_command("JSON.SET", key, "$", body)
        ttl_seconds = max(60, int((expires_at - utc_now()).total_seconds()))
        await self.redis.expire(key, ttl_seconds)

    # ------------------------------------------------------------------
    # Topic CRUD
    # ------------------------------------------------------------------
    async def upsert_topic(self, t: T2Topic) -> None:
        payload = self._topic_payload(t)
        await self._write_json(self.topic_key(t.user_id, t.topic_id), payload, t.expires_at)
        logger.debug("T2: upserted topic %s (%s)", t.topic_id, t.name)

    async def get_topic(self, user_id: str, topic_id: str) -> T2Topic | None:
        raw = await self.redis.execute_command(
            "JSON.GET", self.topic_key(user_id, topic_id)
        )
        if not raw:
            return None
        data = json.loads(_decode(raw))
        # JSON.GET on $ may wrap as array; normalize.
        if isinstance(data, list):
            data = data[0]
        return T2Topic.model_validate(data)

    async def find_topic_by_name_or_alias(
        self, user_id: str, name: str
    ) -> T2Topic | None:
        needle = name.strip().lower()
        if not needle:
            return None
        # Escape spaces for RediSearch TEXT phrase.
        escaped = needle.replace('"', '\\"')
        query = (
            f"(@user_id:{{{_escape_tag(user_id)}}}) "
            f'(@name:"{escaped}" | @aliases:"{escaped}")'
        )
        try:
            res = await self.redis.execute_command(
                "FT.SEARCH", self.TOPIC_INDEX, query, "LIMIT", "0", "5", "DIALECT", "2"
            )
        except Exception as exc:
            logger.debug("T2: find_topic_by_name_or_alias failed: %s", exc)
            return None
        topics = self._parse_search_topics(res)
        for topic in topics:
            if topic.name.lower() == needle or any(
                a.lower() == needle for a in topic.aliases
            ):
                return topic
        return topics[0] if topics else None

    async def add_topic_alias(
        self, user_id: str, topic_id: str, alias: str
    ) -> None:
        topic = await self.get_topic(user_id, topic_id)
        if topic is None:
            return
        alias_l = alias.strip()
        if not alias_l:
            return
        if alias_l.lower() == topic.name.lower():
            return
        if any(a.lower() == alias_l.lower() for a in topic.aliases):
            return
        topic.aliases.append(alias_l)
        await self.upsert_topic(topic)

    async def recent_topics(self, user_id: str, k: int = 20) -> list[T2Topic]:
        query = f"@user_id:{{{_escape_tag(user_id)}}}"
        try:
            res = await self.redis.execute_command(
                "FT.SEARCH", self.TOPIC_INDEX, query,
                "SORTBY", "last_accessed", "DESC",
                "LIMIT", "0", str(k),
                "DIALECT", "2",
            )
        except Exception as exc:
            logger.debug("T2: recent_topics failed: %s", exc)
            return []
        return self._parse_search_topics(res)

    async def knn_topics(
        self, user_id: str, query_vector: list[float], k: int = 3
    ) -> list[tuple[T2Topic, float]]:
        return await self._knn(
            self.TOPIC_INDEX, user_id, query_vector, k, T2Topic
        )

    async def refresh_topic(
        self, user_id: str, topic_id: str, *, bump_access: bool = True
    ) -> None:
        topic = await self.get_topic(user_id, topic_id)
        if topic is None:
            return
        topic.last_accessed = utc_now()
        if bump_access:
            topic.access_count += 1
        topic.expires_at = topic_expires_at_for_importance(
            topic.importance, topic.last_accessed
        )
        topic.ttl_days = topic_ttl_for_importance(topic.importance)
        await self.upsert_topic(topic)

    # ------------------------------------------------------------------
    # Memory CRUD
    # ------------------------------------------------------------------
    async def upsert_memory(self, m: T2Memory) -> None:
        payload = self._memory_payload(m)
        await self._write_json(self.mem_key(m.user_id, m.memory_id), payload, m.expires_at)
        logger.debug("T2: upserted memory %s", m.memory_id)

    async def get_memory(self, user_id: str, memory_id: str) -> T2Memory | None:
        raw = await self.redis.execute_command(
            "JSON.GET", self.mem_key(user_id, memory_id)
        )
        if not raw:
            return None
        data = json.loads(_decode(raw))
        if isinstance(data, list):
            data = data[0]
        return T2Memory.model_validate(data)

    async def knn_memories(
        self,
        user_id: str,
        query_vector: list[float],
        k: int = 5,
        *,
        exclude_superseded: bool = True,
    ) -> list[tuple[T2Memory, float]]:
        filter_clause = f"@user_id:{{{_escape_tag(user_id)}}}"
        if exclude_superseded:
            filter_clause = f"{filter_clause} @superseded_by:{{_active}}"
        return await self._knn(
            self.MEM_INDEX, user_id, query_vector, k, T2Memory,
            filter_clause=filter_clause,
        )

    async def list_recent(
        self, user_id: str, hours: int = 24, limit: int = 100
    ) -> list[T2Memory]:
        cutoff = utc_now().timestamp() - hours * 3600
        query = (
            f"@user_id:{{{_escape_tag(user_id)}}} "
            f"@created_at:[{cutoff} +inf]"
        )
        try:
            res = await self.redis.execute_command(
                "FT.SEARCH", self.MEM_INDEX, query,
                "SORTBY", "created_at", "DESC",
                "LIMIT", "0", str(limit),
                "DIALECT", "2",
            )
        except Exception as exc:
            logger.debug("T2: list_recent failed: %s", exc)
            return []
        return self._parse_search_memories(res)

    async def extend_topic_memory_ttls(
        self, user_id: str, topic_id: str, top: int = 50
    ) -> int:
        query = (
            f"@user_id:{{{_escape_tag(user_id)}}} "
            f"@topic_ids:{{{_escape_tag(topic_id)}}}"
        )
        try:
            res = await self.redis.execute_command(
                "FT.SEARCH", self.MEM_INDEX, query,
                "SORTBY", "created_at", "DESC",
                "LIMIT", "0", str(top),
                "DIALECT", "2",
            )
        except Exception as exc:
            logger.debug("T2: extend_topic_memory_ttls failed: %s", exc)
            return 0
        memories = self._parse_search_memories(res)
        refreshed = 0
        now = utc_now()
        for mem in memories:
            mem.last_accessed = now
            mem.expires_at = expires_at_for_importance(mem.importance, now)
            mem.ttl_days = get_ttl_by_importance(mem.importance)
            await self.upsert_memory(mem)
            refreshed += 1
        return refreshed

    async def delete_topic(self, user_id: str, topic_id: str) -> None:
        """Delete a topic's JSON document. Memories' topic_ids are not touched."""
        await self.redis.delete(self.topic_key(user_id, topic_id))
        logger.debug("T2: deleted topic %s/%s", user_id, topic_id)

    async def rewrite_topic_id_in_memories(
        self,
        user_id: str,
        old_topic_id: str,
        new_topic_id: str,
        *,
        limit: int = 200,
    ) -> int:
        """Replace old_topic_id with new_topic_id inside memories' topic_ids list."""
        query = (
            f"@user_id:{{{_escape_tag(user_id)}}} "
            f"@topic_ids:{{{_escape_tag(old_topic_id)}}}"
        )
        try:
            res = await self.redis.execute_command(
                "FT.SEARCH", self.MEM_INDEX, query,
                "LIMIT", "0", str(limit),
                "DIALECT", "2",
            )
        except Exception as exc:
            logger.debug("T2: rewrite_topic_id_in_memories search failed: %s", exc)
            return 0
        memories = self._parse_search_memories(res)
        rewritten = 0
        for mem in memories:
            new_ids: list[str] = []
            seen: set[str] = set()
            for tid in mem.topic_ids:
                replacement = new_topic_id if tid == old_topic_id else tid
                if replacement not in seen:
                    seen.add(replacement)
                    new_ids.append(replacement)
            if new_ids != mem.topic_ids:
                mem.topic_ids = new_ids
                await self.upsert_memory(mem)
                rewritten += 1
        return rewritten

    async def mark_superseded(
        self,
        user_id: str,
        old_id: str,
        new_id: str,
        change_type: str = "correction",
        change_reason: str | None = None,
    ) -> None:
        old = await self.get_memory(user_id, old_id)
        new = await self.get_memory(user_id, new_id)
        if old is None or new is None:
            logger.warning(
                "T2: mark_superseded skipped (old=%s, new=%s)",
                old is not None, new is not None,
            )
            return
        old.superseded_by = new_id
        new.supersedes = old_id
        new.change_type = change_type  # type: ignore[assignment]
        if change_reason is not None:
            new.change_reason = change_reason
        await self.upsert_memory(old)
        await self.upsert_memory(new)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _knn(
        self,
        index: str,
        user_id: str,
        query_vector: list[float],
        k: int,
        model_cls,
        *,
        filter_clause: str | None = None,
    ) -> list[tuple[Any, float]]:
        base = (
            filter_clause
            if filter_clause
            else f"@user_id:{{{_escape_tag(user_id)}}}"
        )
        query = f"({base})=>[KNN {k} @embedding $vec AS dist]"
        try:
            res = await self.redis.execute_command(
                "FT.SEARCH", index, query,
                "PARAMS", "2", "vec", _pack_vec(query_vector),
                "SORTBY", "dist", "ASC",
                "LIMIT", "0", str(k),
                "DIALECT", "2",
            )
        except Exception as exc:
            logger.debug("T2: KNN search failed on %s: %s", index, exc)
            return []
        return self._parse_search_with_score(res, model_cls)

    @staticmethod
    def _iter_doc_fields(res: list) -> list[tuple[str, dict]]:
        """Parse FT.SEARCH response into list of (doc_key, fields_dict)."""
        if not res or not isinstance(res, list) or len(res) < 1:
            return []
        out: list[tuple[str, dict]] = []
        # Format: [total, key1, [field1, value1, field2, value2, ...], key2, [...], ...]
        i = 1
        while i < len(res):
            key = _decode(res[i])
            i += 1
            if i >= len(res):
                break
            field_list = res[i]
            i += 1
            fields: dict[str, Any] = {}
            if isinstance(field_list, list):
                for j in range(0, len(field_list) - 1, 2):
                    fname = _decode(field_list[j])
                    fval = field_list[j + 1]
                    if isinstance(fval, bytes):
                        fval = fval.decode(errors="replace")
                    fields[fname] = fval
            out.append((key, fields))
        return out

    def _parse_search_topics(self, res: list) -> list[T2Topic]:
        out: list[T2Topic] = []
        for _key, fields in self._iter_doc_fields(res):
            doc = self._extract_json_doc(fields)
            if doc is None:
                continue
            try:
                out.append(T2Topic.model_validate(doc))
            except Exception as exc:
                logger.debug("T2: topic parse failed: %s", exc)
        return out

    def _parse_search_memories(self, res: list) -> list[T2Memory]:
        out: list[T2Memory] = []
        for _key, fields in self._iter_doc_fields(res):
            doc = self._extract_json_doc(fields)
            if doc is None:
                continue
            try:
                out.append(T2Memory.model_validate(doc))
            except Exception as exc:
                logger.debug("T2: memory parse failed: %s", exc)
        return out

    def _parse_search_with_score(
        self, res: list, model_cls
    ) -> list[tuple[Any, float]]:
        out: list[tuple[Any, float]] = []
        for _key, fields in self._iter_doc_fields(res):
            doc = self._extract_json_doc(fields)
            if doc is None:
                continue
            try:
                obj = model_cls.model_validate(doc)
            except Exception as exc:
                logger.debug("T2: knn parse failed: %s", exc)
                continue
            dist_raw = fields.get("dist") or fields.get("__embedding_score") or "0"
            try:
                dist = float(dist_raw)
            except (TypeError, ValueError):
                dist = 0.0
            similarity = max(0.0, 1.0 - dist)
            out.append((obj, similarity))
        return out

    @staticmethod
    def _extract_json_doc(fields: dict) -> dict | None:
        raw = fields.get("$") or fields.get("$.embedding") or None
        if raw is None and "$" not in fields:
            # No JSON requested — fields are flat KV; not useful for hydration.
            # Fall back: maybe doc body returned under empty key.
            for v in fields.values():
                if isinstance(v, str) and v.startswith("{"):
                    raw = v
                    break
        if raw is None:
            return None
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return None
        if isinstance(parsed, list):
            parsed = parsed[0] if parsed else {}
        return parsed
