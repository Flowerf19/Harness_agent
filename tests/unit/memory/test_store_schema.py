"""Unit tests for TimelineSummaryStore schema v2."""
from __future__ import annotations

import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from twin.shared.config.settings import Config
from twin.shared.memory.timeline_summary_store import TimelineSummaryStore


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

