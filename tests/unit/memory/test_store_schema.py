"""Unit tests for TimelineSummaryStore schema v2/v3 (diary model)."""
from __future__ import annotations

import json
import struct
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from twin.shared.config.settings import Config
from twin.shared.memory.diary.codec import decode_fields, escape_tag_value, parse_results
from twin.shared.memory.diary import TimelineSummaryStore


class FakeRedis:
    def __init__(self):
        self.hset_calls: list[dict] = []
        self.expire_calls: list[tuple] = []
        self.ft_info_raises = True  # simulate index not existing
        self.ft_info_reply: object = {}

    async def execute_command(self, *args):
        if args[0] == "FT.INFO":
            if self.ft_info_raises:
                raise Exception("Unknown index name")
            return self.ft_info_reply
        if args[0] == "FT.CREATE":
            return "OK"
        return []

    async def hset(self, key, mapping):
        self.hset_calls.append({"key": key, "mapping": mapping})

    async def expire(self, key, seconds):
        self.expire_calls.append((key, seconds))


@pytest.mark.asyncio
async def test_store_summary_v2_mapping():
    redis = FakeRedis()
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=384)

    embedding = [0.1] * 384
    sid = await store.store_summary(
        user_id="111",
        summary="User đang làm dự án X.",
        embedding=embedding,
        topic="work",
        topic_display="Công việc",
        importance=4,
    )

    assert len(redis.hset_calls) == 1
    mapping = redis.hset_calls[0]["mapping"]

    # Required v2 fields
    assert mapping["summary"] == "User đang làm dự án X."
    assert mapping["topic"] == "work"
    assert mapping["topic_display"] == "Công việc"
    assert mapping["importance"] == 4
    assert mapping["version"] == 2
    assert mapping["user_id"] == "111"

    # 'content' field must NOT be present in stored mapping (v2 stores 'summary')
    assert "content" not in mapping

    # Embedding packed as bytes
    assert isinstance(mapping["embedding"], bytes)
    expected_bytes = struct.pack(f"{384}f", *embedding)
    assert mapping["embedding"] == expected_bytes

    # TTL set
    assert len(redis.expire_calls) == 1
    key_used = redis.expire_calls[0][0]
    assert key_used.startswith("timeline:summary:")
    assert sid in key_used


@pytest.mark.asyncio
async def test_store_summary_defaults():
    redis = FakeRedis()
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=384)

    await store.store_summary(
        user_id="222",
        summary="Casual chat.",
        embedding=[0.0] * 384,
    )

    mapping = redis.hset_calls[0]["mapping"]
    assert mapping["topic"] == "general"
    assert mapping["topic_display"] == ""
    assert mapping["importance"] == 3


@pytest.mark.asyncio
async def test_initialize_creates_schema_v2():
    redis = FakeRedis()
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=384)

    # Track FT.CREATE calls
    create_args = []
    original = redis.execute_command

    async def patched(*args):
        if args[0] == "FT.CREATE":
            create_args.extend(args)
        return await original(*args)

    redis.execute_command = patched
    await store.initialize()

    schema_str = " ".join(str(a) for a in create_args)
    assert "summary" in schema_str
    assert "topic" in schema_str
    assert "version" in schema_str
    assert "384" in schema_str


@pytest.mark.asyncio
async def test_initialize_tolerates_create_already_exists(caplog):
    """A transient FT.INFO flap on an index that DOES exist makes FT.CREATE
    reply "already exists" — initialize() must swallow that and proceed
    rather than crash startup (ops hardening, review finding #3)."""
    class FlapRedis(FakeRedis):
        async def execute_command(self, *args):
            if args[0] == "FT.INFO":
                raise Exception("connection timed out")  # transient flap
            if args[0] == "FT.CREATE":
                raise Exception("Index already exists")
            return []
    redis = FlapRedis()
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=384)
    await store.initialize()  # must not raise


@pytest.mark.asyncio
async def test_initialize_logs_error_on_existing_index_dim_mismatch(caplog):
    import logging

    redis = FakeRedis()
    redis.ft_info_raises = False  # index already exists
    redis.ft_info_reply = [
        b"index_name", b"timeline_summaries",
        b"attributes", [
            [b"identifier", b"embedding", b"attribute", b"embedding",
             b"type", b"VECTOR", b"dim", 999, b"distance_metric", b"COSINE"],
        ],
    ]
    # Configured for 384 but the index was built with dim=999.
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=384)

    with caplog.at_level(logging.ERROR):
        await store.initialize()

    assert any(
        "reindex" in rec.message.lower() and rec.levelno == logging.ERROR
        for rec in caplog.records
    )


@pytest.mark.asyncio
async def test_initialize_no_error_when_dim_matches(caplog):
    import logging

    redis = FakeRedis()
    redis.ft_info_raises = False
    redis.ft_info_reply = [
        b"index_name", b"timeline_summaries",
        b"attributes", [
            [b"identifier", b"embedding", b"attribute", b"embedding",
             b"type", b"VECTOR", b"dim", 384, b"distance_metric", b"COSINE"],
        ],
    ]
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=384)

    with caplog.at_level(logging.ERROR):
        await store.initialize()

    assert not any(rec.levelno == logging.ERROR for rec in caplog.records)


@pytest.mark.asyncio
async def test_store_summary_raises_on_dim_mismatch():
    # Storing anyway (old behavior: warn-and-store) made RediSearch fail to
    # index the hash, leaving the summary silently unsearchable forever.
    redis = FakeRedis()
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=384)

    with pytest.raises(ValueError, match="dim mismatch"):
        await store.store_summary(
            user_id="333",
            summary="Dim mismatch test.",
            embedding=[0.1] * 100,  # wrong dim
        )

    # Must not have written anything for a rejected embedding.
    assert redis.hset_calls == []


class CapturingRedis:
    """Redis stub that records FT.SEARCH query strings."""

    def __init__(self):
        self.search_queries: list[str] = []

    async def execute_command(self, *args):
        if args[0] == "FT.SEARCH":
            # args = ("FT.SEARCH", index, query, ...)
            self.search_queries.append(args[2])
        return []


@pytest.mark.asyncio
async def test_bm25_query_ors_terms():
    """BM25 must OR query terms — RediSearch ANDs by default, which would make
    keyword recall almost never fire on natural multi-word queries."""
    redis = CapturingRedis()
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=384)

    await store._search_bm25("111", "PC build thế nào", limit=5, topic_filter=None)

    assert len(redis.search_queries) == 1
    q = redis.search_queries[0]
    # terms OR-joined, not space-ANDed
    assert "|" in q
    assert "PC | build" in q
    # user filter preserved
    assert "@user_id:{111}" in q


@pytest.mark.asyncio
async def test_bm25_query_applies_topic_filter():
    redis = CapturingRedis()
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=384)

    await store._search_bm25("111", "ryzen amd", limit=5, topic_filter="tech")

    q = redis.search_queries[0]
    assert "@topic:{tech}" in q


@pytest.mark.asyncio
async def test_hybrid_search_bm25_cannot_bypass_gate(monkeypatch):
    """A doc dropped by the cosine gate from KNN must not reappear via BM25
    in the fused hybrid result (Fix 2 regression)."""
    monkeypatch.setattr(Config, "T2_MIN_COSINE", 0.5)
    store = TimelineSummaryStore(redis_client=MagicMock(), embedding_dim=384)

    # "gated" has score=0.9 -> similarity=0.1, below the 0.5 floor.
    # "kept" has score=0.1 -> similarity=0.9, above the floor.
    knn_hits = [
        {"summary_id": "kept", "score": 0.1},
        {"summary_id": "gated", "score": 0.9},
    ]
    # BM25 (ungated) resurfaces the same "gated" doc, plus a pure-BM25-only doc.
    bm25_hits = [
        {"summary_id": "gated"},
        {"summary_id": "bm25_only"},
    ]

    async def fake_search_knn(user_id, query_embedding, limit, topic_filter):
        return list(knn_hits)

    async def fake_search_bm25(user_id, query_text, limit, topic_filter):
        return list(bm25_hits)

    monkeypatch.setattr(store, "_search_knn", fake_search_knn)
    monkeypatch.setattr(store, "_search_bm25", fake_search_bm25)

    results = await store.search("111", [0.0] * 384, limit=5, query_text="anything")
    ids = {r["summary_id"] for r in results}

    assert "gated" not in ids
    assert "kept" in ids
    assert "bm25_only" in ids


@pytest.mark.asyncio
async def test_hybrid_search_gates_before_limit(monkeypatch):
    """The cosine gate must run BEFORE the final limit (Finding 2 regression).

    A gated doc ranked high in the fused list must not consume a slot and drop a
    valid doc below the limit. With limit=3, three valid docs, and one gated doc
    that ranks BM25 rank-1 (landing inside the fused top-3), truncating first
    would evict a valid doc and return only 2. Gating first must return all 3.
    """
    monkeypatch.setattr(Config, "T2_MIN_COSINE", 0.5)
    store = TimelineSummaryStore(redis_client=MagicMock(), embedding_dim=384)

    # 3 valid docs (sim >= 0.5) + 1 gated doc (sim 0.1). The gated doc ranks
    # rank-1 in BM25, giving it a strong fused RRF score that lands it at fused
    # rank-2 — so truncating to limit=3 first (old behaviour) would push "v3"
    # out and, after stripping "gated", leave only 2 docs.
    knn_hits = [
        {"summary_id": "v1", "score": 0.1},    # sim 0.9 kept
        {"summary_id": "v2", "score": 0.2},    # sim 0.8 kept
        {"summary_id": "v3", "score": 0.3},    # sim 0.7 kept
        {"summary_id": "gated", "score": 0.9},  # sim 0.1 gated
    ]
    bm25_hits = [
        {"summary_id": "gated"},  # BM25 rank-1 → high fused score
        {"summary_id": "v1"},
    ]

    async def fake_search_knn(user_id, query_embedding, limit, topic_filter):
        return list(knn_hits)

    async def fake_search_bm25(user_id, query_text, limit, topic_filter):
        return list(bm25_hits)

    monkeypatch.setattr(store, "_search_knn", fake_search_knn)
    monkeypatch.setattr(store, "_search_bm25", fake_search_bm25)

    results = await store.search("111", [0.0] * 384, limit=3, query_text="anything")
    ids = [r["summary_id"] for r in results]

    assert "gated" not in ids
    assert set(ids) == {"v1", "v2", "v3"}
    assert len(results) == 3


@pytest.mark.asyncio
async def test_pure_knn_search_still_gated(monkeypatch):
    """No query_text -> pure KNN path must still apply the cosine gate."""
    monkeypatch.setattr(Config, "T2_MIN_COSINE", 0.5)
    store = TimelineSummaryStore(redis_client=MagicMock(), embedding_dim=384)

    async def fake_search_knn(user_id, query_embedding, limit, topic_filter):
        return [
            {"summary_id": "kept", "score": 0.1},
            {"summary_id": "gated", "score": 0.9},
        ]

    monkeypatch.setattr(store, "_search_knn", fake_search_knn)

    results = await store.search("111", [0.0] * 384, limit=5)
    ids = {r["summary_id"] for r in results}

    assert ids == {"kept"}



# ---------------------------------------------------------------- B8: RESP2 parse
# Production clients (connect_redis — no protocol=3) get RESP2 FT.SEARCH
# replies: [count, key, [k1, v1, k2, v2, ...], ...]. _decode_fields used to
# accept only dicts, so this shape crashed and every T2 read returned [].
# These fixtures mirror the byte-for-byte reply shape observed against the
# real Redis Stack (see scripts/calibrate_t2.py debugging, 2026-07-03).


def test_parse_results_resp2_flat_pair_list():
    store = TimelineSummaryStore(redis_client=MagicMock(), embedding_dim=4)
    emb = struct.pack("4f", 1.0, 0.0, 0.0, 0.0)
    reply = [
        2,
        b"timeline:summary:aaa",
        [
            b"user_id", b"u1",
            b"topic", b"food",
            b"summary", "phở bò".encode(),
            b"importance", b"4",
            b"created_at", b"1751500000.0",
            b"version", b"2",
            b"embedding", emb,
            b"score", b"0.25",
        ],
        b"timeline:summary:bbb",
        [b"topic", b"pet", b"summary", b"meo Mun"],
    ]

    docs = parse_results(reply, store.prefix)

    assert len(docs) == 2
    assert docs[0]["summary_id"] == "aaa"
    assert docs[0]["topic"] == "food"
    assert docs[0]["summary"] == "phở bò"
    assert docs[0]["content"] == "phở bò"  # back-compat alias
    assert docs[0]["importance"] == 4
    assert docs[0]["created_at"] == 1751500000.0
    assert docs[0]["score"] == 0.25  # KNN AS score → float
    assert docs[0]["embedding"] == [1.0, 0.0, 0.0, 0.0]
    assert docs[1]["summary_id"] == "bbb"


def test_parse_results_resp2_withscores():
    # BM25 WITHSCORES shape: [count, key, score, [fields], ...]
    store = TimelineSummaryStore(redis_client=MagicMock(), embedding_dim=4)
    reply = [
        1,
        b"timeline:summary:ccc",
        b"1.5",
        [b"topic", b"work", b"summary", b"debug"],
    ]

    docs = parse_results(reply, store.prefix, has_scores=True)

    assert len(docs) == 1
    assert docs[0]["summary_id"] == "ccc"
    assert docs[0]["_score"] == 1.5
    assert docs[0]["topic"] == "work"


def test_decode_fields_still_accepts_dict():
    store = TimelineSummaryStore(redis_client=MagicMock(), embedding_dim=4)
    decoded = decode_fields({b"topic": b"pet", b"importance": b"3"})
    assert decoded == {"topic": "pet", "importance": 3}


# ---------------------------------------------------------------- P2.1: schema v3


def _ts(dt: datetime) -> float:
    return dt.timestamp()


@pytest.mark.asyncio
async def test_initialize_creates_schema_v3_diary_fields():
    redis = FakeRedis()
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=384)

    create_args = []
    original = redis.execute_command

    async def patched(*args):
        if args[0] == "FT.CREATE":
            create_args.extend(args)
        return await original(*args)

    redis.execute_command = patched
    await store.initialize()

    schema_str = " ".join(str(a) for a in create_args)
    assert "day" in schema_str
    assert "period_start" in schema_str
    assert "period_end" in schema_str


class AlterTrackingRedis(FakeRedis):
    """FT.INFO succeeds (index exists); records FT.ALTER invocations."""

    def __init__(self, *, alter_fails: bool = False):
        super().__init__()
        self.ft_info_raises = False
        self.alter_calls: list[tuple] = []
        self.alter_fails = alter_fails

    async def execute_command(self, *args):
        if args[0] == "FT.ALTER":
            self.alter_calls.append(args)
            if self.alter_fails:
                raise Exception("ALTER not supported")
            return "OK"
        return await super().execute_command(*args)


def _v2_ft_info_reply(dim: int = 384):
    """FT.INFO shape for an old v2 index: has embedding but no diary fields."""
    return [
        b"index_name", b"timeline_summaries",
        b"attributes", [
            [b"identifier", b"user_id", b"attribute", b"user_id", b"type", b"TAG"],
            [b"identifier", b"embedding", b"attribute", b"embedding",
             b"type", b"VECTOR", b"dim", dim, b"distance_metric", b"COSINE"],
        ],
    ]


def _v3_ft_info_reply(dim: int = 384):
    """FT.INFO shape for an index that already has all diary fields."""
    return [
        b"index_name", b"timeline_summaries",
        b"attributes", [
            [b"identifier", b"user_id", b"attribute", b"user_id", b"type", b"TAG"],
            [b"identifier", b"day", b"attribute", b"day", b"type", b"TAG"],
            [b"identifier", b"period_start", b"attribute", b"period_start", b"type", b"NUMERIC"],
            [b"identifier", b"period_end", b"attribute", b"period_end", b"type", b"NUMERIC"],
            [b"identifier", b"embedding", b"attribute", b"embedding",
             b"type", b"VECTOR", b"dim", dim, b"distance_metric", b"COSINE"],
        ],
    ]


@pytest.mark.asyncio
async def test_initialize_alters_existing_v2_index_to_add_diary_fields():
    redis = AlterTrackingRedis()
    redis.ft_info_reply = _v2_ft_info_reply()
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=384)

    await store.initialize()

    altered = {call[4] for call in redis.alter_calls}  # FT.ALTER idx SCHEMA ADD <name>
    assert altered == {"day", "period_start", "period_end"}
    # One field per FT.ALTER (command grammar) and SORTABLE on the numerics.
    for call in redis.alter_calls:
        assert call[1] == "timeline_summaries"
        assert call[2:4] == ("SCHEMA", "ADD")
        if call[4] in {"period_start", "period_end"}:
            assert "SORTABLE" in call
        else:
            assert "TAG" in call


@pytest.mark.asyncio
async def test_initialize_skips_alter_when_fields_already_present():
    redis = AlterTrackingRedis()
    redis.ft_info_reply = _v3_ft_info_reply()
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=384)

    await store.initialize()

    assert redis.alter_calls == []


@pytest.mark.asyncio
async def test_initialize_survives_alter_failure(caplog):
    """FT.ALTER failing (old Redis, ACL, whatever) must log a warning and
    NOT crash startup, and must NOT fall through to FT.CREATE."""
    import logging

    redis = AlterTrackingRedis(alter_fails=True)
    redis.ft_info_reply = _v2_ft_info_reply()
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=384)

    with caplog.at_level(logging.WARNING):
        await store.initialize()  # must not raise

    assert len(redis.alter_calls) == 3  # attempted all three, each failed
    assert any("FT.ALTER" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------- diary write path


class DiaryRedis(FakeRedis):
    """FakeRedis whose FT.SEARCH returns a canned RESP2 flat-list reply —
    the byte-for-byte shape the production RESP2 client hands back."""

    def __init__(self, search_reply=None):
        super().__init__()
        self.search_reply = search_reply if search_reply is not None else [0]
        self.search_calls: list[tuple] = []

    async def execute_command(self, *args):
        if args[0] == "FT.SEARCH":
            self.search_calls.append(args)
            return self.search_reply
        return await super().execute_command(*args)


def _resp2_diary_hit(
    *, summary_id: str, summary: str, score: float, dim: int = 8,
    importance: int = 3, period_start: float | None = None,
    period_end: float | None = None, source_entry_ids: list[str] | None = None,
):
    """RESP2 flat pair-list FT.SEARCH reply with one same-day KNN hit."""
    fields = [
        b"user_id", b"u1",
        b"summary", summary.encode(),
        b"importance", str(importance).encode(),
        b"embedding", struct.pack(f"{dim}f", *([1.0] + [0.0] * (dim - 1))),
        b"score", str(score).encode(),
    ]
    if period_start is not None:
        fields += [b"period_start", str(period_start).encode()]
    if period_end is not None:
        fields += [b"period_end", str(period_end).encode()]
    if source_entry_ids is not None:
        fields += [b"source_entry_ids", json.dumps(source_entry_ids).encode()]
    return [1, f"timeline:summary:{summary_id}".encode(), fields]


@pytest.mark.asyncio
async def test_store_summary_writes_diary_fields():
    redis = FakeRedis()
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=8)

    ps = _ts(datetime(2026, 7, 2, 3, 0, tzinfo=timezone.utc))   # 10:00 VN 02/07
    pe = _ts(datetime(2026, 7, 2, 5, 0, tzinfo=timezone.utc))
    await store.store_summary(
        user_id="u1",
        summary="Nhật ký hôm nay.",
        embedding=[0.1] * 8,
        period_start=ps,
        period_end=pe,
        source_entry_ids=["e1", "e2"],
    )

    mapping = redis.hset_calls[0]["mapping"]
    assert mapping["day"] == "2026-07-02"  # VN day of period_start
    assert mapping["period_start"] == ps
    assert mapping["period_end"] == pe
    assert json.loads(mapping["source_entry_ids"]) == ["e1", "e2"]


@pytest.mark.asyncio
async def test_store_summary_day_uses_vn_timezone_not_utc():
    redis = FakeRedis()
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=8)

    # 2026-07-02 20:00 UTC == 2026-07-03 03:00 VN — day must be the VN one.
    ps = _ts(datetime(2026, 7, 2, 20, 0, tzinfo=timezone.utc))
    await store.store_summary(
        user_id="u1", summary="Khuya rồi.", embedding=[0.1] * 8, period_start=ps,
    )

    assert redis.hset_calls[0]["mapping"]["day"] == "2026-07-03"


@pytest.mark.asyncio
async def test_store_summary_appends_without_knn_lookup():
    """store_summary is append-only — zero FT.SEARCH on the write path."""
    redis = DiaryRedis()
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=8)

    await store.store_summary(user_id="u1", summary="A.", embedding=[0.1] * 8)

    assert redis.search_calls == []
    assert len(redis.hset_calls) == 1


def test_escape_tag_value_escapes_specials():
    esc = escape_tag_value
    assert esc("2026-07-03") == "2026\\-07\\-03"
    assert esc("plain") == "plain"
    assert esc("a.b c") == "a\\.b\\ c"


def test_decode_fields_parses_diary_fields():
    store = TimelineSummaryStore(redis_client=MagicMock(), embedding_dim=4)
    decoded = decode_fields([
        b"period_start", b"1751500000.0",
        b"period_end", b"1751503600.5",
        b"source_entry_ids", b'["e1", "e2"]',
        b"day", b"2026-07-03",
    ])
    assert decoded["period_start"] == 1751500000.0
    assert decoded["period_end"] == 1751503600.5
    assert decoded["source_entry_ids"] == ["e1", "e2"]
    assert decoded["day"] == "2026-07-03"


def test_decode_fields_source_entry_ids_garbage_becomes_empty_list():
    store = TimelineSummaryStore(redis_client=MagicMock(), embedding_dim=4)
    decoded = decode_fields([b"source_entry_ids", b"not json"])
    assert decoded["source_entry_ids"] == []


# ---------------------------------------------------------------- P3.2: time filter
# since_ts/until_ts on search()/get_recent() — RediSearch has no COALESCE, so a
# doc missing period_end (pre-v3) must fall back to created_at. See
# TimelineSummaryStore._time_filter_clause's docstring for the OR/negation shape.


def test_time_filter_clause_none_when_both_unset():
    assert TimelineSummaryStore._time_filter_clause(None, None) is None


def test_time_filter_clause_or_fallback_shape():
    clause = TimelineSummaryStore._time_filter_clause(1000.0, 2000.0)
    assert clause is not None
    assert "@period_end:[1000.0 2000.0]" in clause
    assert "-@period_end:[-inf +inf]" in clause
    assert "@created_at:[1000.0 2000.0]" in clause
    assert clause.count("|") == 1  # single top-level OR


def test_time_filter_clause_open_ended_bounds():
    since_only = TimelineSummaryStore._time_filter_clause(1000.0, None)
    assert "@period_end:[1000.0 +inf]" in since_only
    assert "@created_at:[1000.0 +inf]" in since_only

    until_only = TimelineSummaryStore._time_filter_clause(None, 2000.0)
    assert "@period_end:[-inf 2000.0]" in until_only
    assert "@created_at:[-inf 2000.0]" in until_only


@pytest.mark.asyncio
async def test_knn_query_applies_time_filter():
    redis = CapturingRedis()
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=4)

    await store._search_knn(
        "111", [0.0] * 4, limit=5, topic_filter=None,
        since_ts=1000.0, until_ts=2000.0,
    )

    q = redis.search_queries[0]
    assert "@user_id:{111}" in q
    assert "@period_end:[1000.0 2000.0]" in q
    assert "@created_at:[1000.0 2000.0]" in q


@pytest.mark.asyncio
async def test_knn_query_omits_time_filter_when_unset():
    redis = CapturingRedis()
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=4)

    await store._search_knn("111", [0.0] * 4, limit=5, topic_filter=None)

    q = redis.search_queries[0]
    assert "period_end" not in q
    assert "created_at" not in q


@pytest.mark.asyncio
async def test_bm25_query_applies_time_filter():
    redis = CapturingRedis()
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=4)

    await store._search_bm25(
        "111", "pho bo", limit=5, topic_filter=None,
        since_ts=1000.0, until_ts=None,
    )

    q = redis.search_queries[0]
    assert "@period_end:[1000.0 +inf]" in q
    assert "@created_at:[1000.0 +inf]" in q


@pytest.mark.asyncio
async def test_get_recent_no_time_filter_omits_dialect():
    """Unfiltered get_recent must keep its exact pre-P3.2 argument list —
    no DIALECT param was ever passed for the plain tag-only query."""
    redis = DiaryRedis([0])
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=8)

    await store.get_recent("u1", limit=10)

    args = redis.search_calls[-1]
    assert args[2] == "@user_id:{u1}"
    assert "DIALECT" not in args


@pytest.mark.asyncio
async def test_get_recent_applies_since_ts_and_dialect2():
    """DIALECT 2 is added only once the OR/negation time_clause is in play —
    same construct _search_knn/_search_bm25 already rely on DIALECT 2 for."""
    redis = DiaryRedis(_resp2_diary_hit(
        summary_id="r1", summary="tin tuc hom qua", score=0.1, period_end=5000.0,
    ))
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=8)

    results = await store.get_recent("u1", limit=10, since_ts=1000.0)

    assert len(results) == 1
    assert results[0]["summary_id"] == "r1"
    args = redis.search_calls[-1]
    assert "@period_end:[1000.0 +inf]" in args[2]
    assert "DIALECT" in args and "2" in args


# ---------------------------------------------------------------- P3.5: BM25-only gate
# fix B3: a doc KNN never scored has no cosine distance to gate on, so without
# this it bypasses T2_MIN_COSINE entirely via a strong lexical-only match.


@pytest.mark.asyncio
async def test_hybrid_search_gates_bm25_only_doc_by_cosine(monkeypatch):
    """BM25-only doc below the cosine floor is dropped despite ranking first
    (strongest BM25 score); one above the floor is kept."""
    monkeypatch.setattr(Config, "T2_MIN_COSINE", 0.35)
    store = TimelineSummaryStore(redis_client=MagicMock(), embedding_dim=4)

    query_embedding = [1.0, 0.0, 0.0, 0.0]
    # BM25 rank-1 (strongest score) but orthogonal to the query -> cosine 0.0.
    # BM25 rank-2, embedding == query -> cosine 1.0.
    bm25_hits = [
        {"summary_id": "low_cos", "embedding": [0.0, 1.0, 0.0, 0.0]},
        {"summary_id": "high_cos", "embedding": [1.0, 0.0, 0.0, 0.0]},
    ]

    async def fake_search_knn(user_id, query_embedding, limit, topic_filter):
        return []

    async def fake_search_bm25(user_id, query_text, limit, topic_filter):
        return list(bm25_hits)

    monkeypatch.setattr(store, "_search_knn", fake_search_knn)
    monkeypatch.setattr(store, "_search_bm25", fake_search_bm25)

    results = await store.search("111", query_embedding, limit=5, query_text="anything")
    ids = {r["summary_id"] for r in results}

    assert "low_cos" not in ids
    assert "high_cos" in ids


def test_gate_bm25_only_by_cosine_noop_when_floor_zero():
    store = TimelineSummaryStore(redis_client=MagicMock(), embedding_dim=4)
    fused = [{"summary_id": "a", "embedding": [0.0, 1.0, 0.0, 0.0]}]

    out = store._gate_bm25_only_by_cosine(fused, knn_results=[], query_embedding=[1.0, 0.0, 0.0, 0.0])

    assert out == fused  # Config.T2_MIN_COSINE default 0.0 -> no-op


def test_gate_bm25_only_by_cosine_skips_docs_already_seen_by_knn(monkeypatch):
    """A doc already in knn_results was already gated by _gate_by_similarity —
    must not be re-scored here even if its embedding would fail the floor."""
    monkeypatch.setattr(Config, "T2_MIN_COSINE", 0.9)
    store = TimelineSummaryStore(redis_client=MagicMock(), embedding_dim=4)
    fused = [{"summary_id": "seen", "embedding": [0.0, 1.0, 0.0, 0.0]}]
    knn_results = [{"summary_id": "seen", "score": 0.05}]

    out = store._gate_bm25_only_by_cosine(fused, knn_results, query_embedding=[1.0, 0.0, 0.0, 0.0])

    assert out == fused


def test_gate_bm25_only_by_cosine_keeps_doc_missing_embedding(monkeypatch):
    """Fail open: nothing to score against, so a doc with no embedding field
    passes through rather than being dropped."""
    monkeypatch.setattr(Config, "T2_MIN_COSINE", 0.9)
    store = TimelineSummaryStore(redis_client=MagicMock(), embedding_dim=4)
    fused = [{"summary_id": "no_embedding"}]

    out = store._gate_bm25_only_by_cosine(fused, knn_results=[], query_embedding=[1.0, 0.0, 0.0, 0.0])

    assert out == fused
