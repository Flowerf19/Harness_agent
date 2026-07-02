"""Unit tests for ConsolidateMemoryTool shipped-entries path (Cách B, Bug 2/4).

When entries are shipped over A2A, the tool must consolidate THOSE dicts and
return their entry_ids WITHOUT reading the local T1 store (which belongs to the
requesting agent, not Evernight).
"""
from __future__ import annotations

import json

import pytest

from twin.shared.tools.modules.memory.consolidate_memory_tool import ConsolidateMemoryTool


class FakeT1:
    def __init__(self) -> None:
        self.get_context_calls: list[dict] = []

    async def get_context(self, scope, scope_id, *, limit: int = 50):
        self.get_context_calls.append({"scope": scope, "scope_id": scope_id, "limit": limit})
        return []


class FakeProfileStore:
    def __init__(self) -> None:
        self.read_raw_calls: list[str] = []
        self.append_raw_calls: list[tuple] = []

    async def read_raw(self, scope_id):
        self.read_raw_calls.append(scope_id)
        return ""

    async def append_raw(self, scope_id, section, bullet, source_memory_id=None):
        self.append_raw_calls.append((scope_id, section, bullet))
        return True


class FakeMemoryManager:
    def __init__(self) -> None:
        self.t1 = FakeT1()
        self.profile = FakeProfileStore()


class FakeLLM:
    model = "fake-model"

    async def generate_response(self, *args, **kwargs):
        return json.dumps({
            "has_meaningful_content": True,
            "topics": [
                {"topic": "work", "topic_display": "Công việc", "summary": "User đang bận dự án.", "importance": 4}
            ],
            "profile_updates": {},
        })


class FakeEmbeddingService:
    async def get_embedding(self, text):
        return [0.1] * 8


class FakeTimelineStore:
    async def store_summary(self, *, user_id, summary, embedding, topic, topic_display, importance):
        return f"sum-{topic}"


class FakeTimelineStoreAllFail:
    """store_summary always raises — models T2 fully down (dim mismatch or
    Redis error). Every topic store attempt fails, so nothing lands in T2."""

    def __init__(self) -> None:
        self.calls = 0

    async def store_summary(self, *, user_id, summary, embedding, topic, topic_display, importance):
        self.calls += 1
        raise ValueError("embedding dim mismatch")


class FakeLLMWithProfileUpdates:
    """LLM stub that also returns non-empty profile_updates, to prove the
    channel-scope path genuinely skips step 6 rather than happening to have
    nothing to write."""

    model = "fake-model"

    async def generate_response(self, *args, **kwargs):
        return json.dumps({
            "has_meaningful_content": True,
            "topics": [
                {"topic": "work", "topic_display": "Công việc", "summary": "User đang bận dự án.", "importance": 4}
            ],
            "profile_updates": {"work": ["Đang làm dự án X"]},
        })


@pytest.mark.asyncio
async def test_execute_with_shipped_entries_returns_ids_and_skips_local_t1():
    memory = FakeMemoryManager()
    tool = ConsolidateMemoryTool(
        memory_manager=memory,
        llm_service=FakeLLM(),
        embedding_service=FakeEmbeddingService(),
        timeline_summary_store=FakeTimelineStore(),
    )

    entries = [
        {"entry_id": "e1", "role": "user", "content": "dự án deadline tuần tới", "author_name": "Hoà"},
        {"entry_id": "e2", "role": "assistant", "content": "ghi nhận nhé"},
    ]

    result_str = await tool.execute(
        scope="channel",
        scope_id="chan1",
        reason="discussion",
        entries=entries,
    )
    result = json.loads(result_str)

    assert result["status"] == "ok"
    assert result["entry_ids"] == ["e1", "e2"]
    assert result["messages_summarized"] == 2
    # Shipped-entries path must NOT read the local T1 store.
    assert memory.t1.get_context_calls == []


@pytest.mark.asyncio
async def test_channel_scope_skips_profile_read_and_write():
    memory = FakeMemoryManager()
    tool = ConsolidateMemoryTool(
        memory_manager=memory,
        llm_service=FakeLLMWithProfileUpdates(),
        embedding_service=FakeEmbeddingService(),
        timeline_summary_store=FakeTimelineStore(),
    )

    entries = [
        {"entry_id": "e1", "role": "user", "content": "dự án deadline tuần tới", "author_name": "Hoà"},
    ]

    result_str = await tool.execute(
        scope="channel",
        scope_id="chan1",
        reason="discussion",
        entries=entries,
    )
    result = json.loads(result_str)

    assert result["status"] == "ok"
    # Channel scope must neither read nor write memories/<channel_id>.md, even
    # though the LLM returned non-empty profile_updates.
    assert memory.profile.read_raw_calls == []
    assert memory.profile.append_raw_calls == []
    assert result["updated_sections"] == []


@pytest.mark.asyncio
async def test_all_t2_stores_fail_returns_failed_no_trim_shape():
    """When every meaningful T2 store attempt raises, the tool must report
    status=failed with no trim-triggering entry_ids (Finding 1 regression).

    The manager trims T1 on status=="ok" + entry_ids; returning "ok" here would
    delete the transcript while nothing landed in T2 (silent data loss). T1 must
    stay untouched — the tool must not present the trim-triggering shape.
    """
    memory = FakeMemoryManager()
    store = FakeTimelineStoreAllFail()
    tool = ConsolidateMemoryTool(
        memory_manager=memory,
        llm_service=FakeLLM(),
        embedding_service=FakeEmbeddingService(),
        timeline_summary_store=store,
    )

    entries = [
        {"entry_id": "e1", "role": "user", "content": "dự án deadline tuần tới", "author_name": "Hoà"},
    ]

    result_str = await tool.execute(
        scope="channel",
        scope_id="chan1",
        reason="discussion",
        entries=entries,
    )
    result = json.loads(result_str)

    # The store was attempted (meaningful topic) and it raised → nothing stored.
    assert store.calls == 1
    assert result["topics_stored"] == 0
    # Must NOT be the trim-triggering shape: manager trims only on status==ok,
    # and there must be no entry_ids to trim by.
    assert result["status"] == "failed"
    assert not result.get("entry_ids")
    # Shipped-entries path never reads local T1 — and certainly must not trim it.
    assert memory.t1.get_context_calls == []
