from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from twin.march7.memories.memory_manager import MemoryManager
from twin.shared.memories.t2 import T2Chunk, T2Embedder, T2Fact, T2Page, T2Search, get_ttl_by_importance


class DummyDispatcher:
    def subscribe(self, *_args, **_kwargs):
        pass


def test_t2_models_serialize_roundtrip(sample_user_id):
    page = T2Page(
        page_id="p1",
        user_id=sample_user_id,
        topic_id="t1",
        canonical_topic="Redis_T2",
        current_summary="Redis Stack backs T2 memory.",
    )
    chunk = T2Chunk(user_id=sample_user_id, topic_id="t1", content="Implemented Redis T2.")
    fact = T2Fact(user_id=sample_user_id, topic_id="t1", claim="T2 uses Redis Stack.")

    assert T2Page.model_validate(page.model_dump()).page_id == "p1"
    assert T2Chunk.model_validate(chunk.model_dump()).content == "Implemented Redis T2."
    assert T2Fact.model_validate(fact.model_dump()).claim == "T2 uses Redis Stack."


def test_ttl_by_importance():
    assert get_ttl_by_importance(5) == 90
    assert get_ttl_by_importance(1) == 7
    assert get_ttl_by_importance(999) == 30


@pytest.mark.asyncio
async def test_embedding_text_builders(sample_user_id):
    embedder = T2Embedder(AsyncMock())
    page = T2Page(
        page_id="p1",
        user_id=sample_user_id,
        topic_id="t1",
        canonical_topic="Redis_T2",
        current_summary="Current state",
        key_points=["point"],
        entities=["Redis"],
    )
    fact = T2Fact(user_id=sample_user_id, topic_id="t1", claim="Active fact")
    chunk = T2Chunk(user_id=sample_user_id, topic_id="t1", content="Latest chunk")

    assert "Active fact" in embedder.build_summary_text(page, [fact])
    assert "Latest chunk" in embedder.build_latest_chunk_text(page, chunk)


@pytest.mark.asyncio
async def test_time_search_hard_filters_range(sample_user_id):
    store = AsyncMock()
    embedder = AsyncMock()
    search = T2Search(store, embedder)
    start = datetime(2026, 5, 16, tzinfo=timezone.utc)
    end = datetime(2026, 5, 16, 23, 59, tzinfo=timezone.utc)
    store.list_chunks.return_value = [
        T2Chunk(user_id=sample_user_id, topic_id="t1", content="inside", event_date=start + timedelta(hours=1))
    ]

    result = await search.search(
        sample_user_id,
        mode="time",
        start_date="2026-05-16",
        end_date="2026-05-16",
    )

    assert "inside" in result
    args = store.list_chunks.await_args.kwargs
    assert args["start"].date() == start.date()
    assert args["end"].date() == end.date()
