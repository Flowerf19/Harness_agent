"""Timeline index DDL and FT.INFO introspection for T2 (schema v3).

FT.CREATE for a fresh index, plus best-effort FT.INFO parsing (indexed
DIM, field names) and FT.ALTER to add diary-model fields (day,
period_start, period_end) to a pre-existing v2 index.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def create_timeline_index(
    redis: Any, index_name: str, prefix: str, embedding_dim: int,
) -> None:
    """FT.CREATE the schema-v3 timeline index (arg order preserved byte-for-byte).

    Tolerates a transient FT.INFO flap (the caller only lands here when FT.INFO
    raised): if the index actually already exists, FT.CREATE replies "already
    exists" — swallow that one and proceed rather than crashing startup. Any
    other create error (bad schema, permissions) still propagates.
    """
    try:
        await redis.execute_command(
            "FT.CREATE", index_name,
            "ON", "HASH",
            "PREFIX", "1", f"{prefix}:",
            "SCHEMA",
            "user_id",       "TAG",
            "topic",         "TAG",
            "topic_display", "TEXT",
            "summary",       "TEXT",
            "importance",    "NUMERIC", "SORTABLE",
            "created_at",    "NUMERIC", "SORTABLE",
            "version",       "NUMERIC",
            "day",           "TAG",
            "period_start",  "NUMERIC", "SORTABLE",
            "period_end",    "NUMERIC", "SORTABLE",
            "embedding",     "VECTOR", "HNSW", "6",
            "TYPE", "FLOAT32",
            "DIM", str(embedding_dim),
            "DISTANCE_METRIC", "COSINE",
        )
        logger.info("Created timeline index (schema v3, dim=%d)", embedding_dim)
    except Exception as exc:
        msg = str(exc).lower()
        if "already exists" in msg:
            logger.info("Timeline index %r already exists — reusing it", index_name)
            return
        raise


def _flatten_info(seq: Any) -> list[Any]:
    """Flatten one FT.INFO reply chunk: RESP3 dict -> [k, v, ...] pairs,
    RESP2 sequence -> list(seq) unchanged.
    """
    if isinstance(seq, dict):
        flat: list[Any] = []
        for k, v in seq.items():
            flat.append(k)
            flat.append(v)
        return flat
    return list(seq)


def extract_indexed_dim(info: Any) -> int | None:
    """Best-effort VECTOR field DIM from an FT.INFO reply (RESP2 or RESP3
    shape). Returns None on any unrecognized shape rather than raising —
    this is a diagnostic, not something that should break startup.
    """
    try:
        top = _flatten_info(info)
        for i, key in enumerate(top):
            key_str = key.decode() if isinstance(key, bytes) else key
            if key_str == "attributes" and i + 1 < len(top):
                for attr in top[i + 1]:
                    fields = _flatten_info(attr)
                    field_map = {}
                    for j in range(0, len(fields) - 1, 2):
                        fk = fields[j]
                        fk = fk.decode() if isinstance(fk, bytes) else fk
                        field_map[fk] = fields[j + 1]
                    field_type = field_map.get("type")
                    field_type = field_type.decode() if isinstance(field_type, bytes) else field_type
                    if field_type == "VECTOR" and "dim" in field_map:
                        return int(field_map["dim"])
        return None
    except Exception:
        return None


def extract_field_names(info: Any) -> set[str]:
    """Best-effort schema field-name extraction from an FT.INFO reply
    (mirrors extract_indexed_dim). Returns an empty set — never raises —
    on any unrecognized shape, so a schema probe can't crash startup.
    """
    try:
        names: set[str] = set()
        top = _flatten_info(info)
        for i, key in enumerate(top):
            key_str = key.decode() if isinstance(key, bytes) else key
            if key_str == "attributes" and i + 1 < len(top):
                for attr in top[i + 1]:
                    fields = _flatten_info(attr)
                    field_map = {}
                    for j in range(0, len(fields) - 1, 2):
                        fk = fields[j]
                        fk = fk.decode() if isinstance(fk, bytes) else fk
                        field_map[fk] = fields[j + 1]
                    identifier = field_map.get("identifier") or field_map.get("attribute")
                    identifier = identifier.decode() if isinstance(identifier, bytes) else identifier
                    if identifier:
                        names.add(identifier)
        return names
    except Exception:
        return set()


async def ensure_diary_fields(redis: Any, index_name: str, info: Any) -> None:
    """Best-effort FT.ALTER for an index predating the diary-model fields
    (schema v2 -> v3, P2.1); adds whichever of day/period_start/period_end
    are missing. Never raises — an index that can't be altered just keeps
    working without these fields (diary merge finds no same-day candidate).
    """
    try:
        existing = extract_field_names(info)
    except Exception:
        return
    to_add = [
        ("day", ["TAG"]),
        ("period_start", ["NUMERIC", "SORTABLE"]),
        ("period_end", ["NUMERIC", "SORTABLE"]),
    ]
    for field_name, field_args in to_add:
        if field_name in existing:
            continue
        try:
            await redis.execute_command(
                "FT.ALTER", index_name, "SCHEMA", "ADD", field_name, *field_args,
            )
            logger.info("Timeline index: added missing field %r via FT.ALTER", field_name)
        except Exception as exc:
            logger.warning(
                "Timeline index: FT.ALTER add %r failed (continuing without it): %s",
                field_name, exc,
            )
