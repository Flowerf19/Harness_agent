"""Unit tests for TimelineSummaryStore schema v2."""
from __future__ import annotations

import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from twin.shared.memory.timeline_summary_store import TimelineSummaryStore


class FakeRedis:
    def __init__(self):
        self.hset_calls: list[dict] = []
        self.expire_calls: list[tuple] = []
        self.ft_info_raises = True  # simulate index not existing

    async def execute_command(self, *args):
        if args[0] == "FT.INFO":
            if self.ft_info_raises:
                raise Exception("Unknown index name")
            return {}
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
async def test_store_summary_warns_on_dim_mismatch(caplog):
    import logging
    redis = FakeRedis()
    store = TimelineSummaryStore(redis_client=redis, embedding_dim=384)

    with caplog.at_level(logging.WARNING):
        await store.store_summary(
            user_id="333",
            summary="Dim mismatch test.",
            embedding=[0.1] * 100,  # wrong dim
        )

    assert "dim mismatch" in caplog.text.lower() or "mismatch" in caplog.text.lower()


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

