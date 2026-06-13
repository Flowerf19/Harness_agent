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
    expires_at_for_importance,
    get_ttl_by_importance,
    utc_now,
)

logger = logging.getLogger(__name__)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _pack_vec(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _fit_embedding(vec: list[float], dim: int) -> list[float]:
    if not vec or len(vec) == dim:
        return vec
    if len(vec) > dim:
        return vec[:dim]
    return vec + [0.0] * (dim - len(vec))


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
    MEM_PREFIX = "t2:mem"
    MEM_INDEX = "idx:t2:mem"

    def __init__(
        self,
        redis_client,
        *,
        vector_dim: int = EMBEDDING_DIM,
        mem_prefix: str | None = None,
        mem_index: str | None = None,
    ) -> None:
        self.redis = redis_client
        self.dim = vector_dim
        if mem_prefix is not None:
            self.MEM_PREFIX = mem_prefix
        if mem_index is not None:
            self.MEM_INDEX = mem_index

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def initialize(self) -> None:
        await self._create_memory_index()

    async def _index_exists(self, index_name: str) -> bool:
        try:
            await self.redis.execute_command("FT.INFO", index_name)
            return True
        except Exception:
            return False

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
                "$.catalogs[*]", "AS", "catalogs", "TAG",
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
    def mem_key(self, user_id: str, memory_id: str) -> str:
        return f"{self.MEM_PREFIX}:{user_id}:{memory_id}"

    # ------------------------------------------------------------------
    # JSON write helper
    # ------------------------------------------------------------------
    def _memory_payload(self, m: T2Memory) -> dict:
        data = m.model_dump(mode="json")
        if data.get("embedding"):
            original = len(data["embedding"])
            data["embedding"] = _fit_embedding(data["embedding"], self.dim)
            if original != len(data["embedding"]):
                logger.warning(
                    "T2: memory embedding dim mismatch memory=%s got=%d expected=%d",
                    m.memory_id,
                    original,
                    self.dim,
                )
        data["created_at_ts"] = _to_ts(m.created_at)
        data["last_accessed_ts"] = _to_ts(m.last_accessed)
        data["expires_at_ts"] = _to_ts(m.expires_at)
        return data

    async def _write_json(self, key: str, payload: dict, expires_at: datetime) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=_json_default)
        await self.redis.execute_command("JSON.SET", key, "$", body)
        ttl_seconds = max(60, int((expires_at - utc_now()).total_seconds()))
        await self.redis.expire(key, ttl_seconds)


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
        catalog: str | None = None,
        min_importance: int | None = None,
    ) -> list[tuple[T2Memory, float]]:
        filter_clause = f"@user_id:{{{_escape_tag(user_id)}}}"
        if exclude_superseded:
            filter_clause = f"{filter_clause} @superseded_by:{{_active}}"
        if catalog:
            filter_clause = f"{filter_clause} @catalogs:{{{_escape_tag(catalog)}}}"
        if min_importance is not None:
            filter_clause = f"{filter_clause} @importance:[{min_importance} 5]"
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
