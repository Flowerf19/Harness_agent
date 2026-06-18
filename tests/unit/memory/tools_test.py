"""Unit tests for memory/profile system tools."""
from __future__ import annotations

import pytest

from twin.shared.tools.modules.memory.search_memory_tool import SearchMemoryTool
from twin.shared.tools.modules.profile.get_profile_tool import GetProfileTool
from twin.shared.tools.modules.profile.update_profile_tool import UpdateUserProfileTool


class FakeTimelineSearch:
    def __init__(self):
        self.calls: list[dict] = []

    async def search(self, user_id, query_embedding, limit, *, query_text=None, topic_filter=None):
        self.calls.append({
            "method": "search",
            "user_id": user_id,
            "query_embedding": query_embedding,
            "limit": limit,
            "query_text": query_text,
            "topic_filter": topic_filter,
        })
        return [
            {
                "summary_id": "sum-1",
                "user_id": user_id,
                "summary": "User thích phim tâm lý.",
                "topic": "interest",
                "importance": 3,
                "created_at": 1718360000.0,
            }
        ]

    async def get_recent(self, user_id, limit):
        self.calls.append({"method": "get_recent", "user_id": user_id, "limit": limit})
        return [
            {
                "summary_id": "sum-2",
                "user_id": user_id,
                "summary": "User nói chào Bé Bảy.",
                "importance": 4,
                "created_at": 1718370000.0,
            }
        ]


class FakeEmbeddingService:
    def __init__(self):
        self.calls: list[str] = []

    async def get_embedding(self, text):
        self.calls.append(text)
        return [0.1] * 384


class FakeProfileStore:
    def __init__(self):
        self.append_calls: list[dict] = []

    async def append_raw(self, user_id, section, content, source_memory_id=None):
        self.append_calls.append(
            {
                "user_id": user_id,
                "section": section,
                "content": content,
                "source_memory_id": source_memory_id,
            }
        )
        return content != "duplicate"

    async def read_raw(self, user_id):
        return f"## Thông tin cơ bản\n- Danh xưng: {user_id}\n"

    async def read_section(self, user_id, section):
        if section == "interest":
            return ["Phim tâm lý", "Cờ vua"]
        return []


@pytest.mark.asyncio
async def test_search_memory_tool_semantic():
    store = FakeTimelineSearch()
    embeddings = FakeEmbeddingService()
    tool = SearchMemoryTool(timeline_summary_store=store, embedding_service=embeddings)

    result = await tool.execute(user_id="12345", mode="semantic", query="phim")
    assert "Tìm thấy 1 ký ức" in result
    assert "User thích phim tâm lý" in result
    assert "summary_id=sum-1" in result
    assert store.calls[-1]["method"] == "search"
    # query prefix e5 applied
    assert embeddings.calls[-1] == "query: phim"
    # semantic mode: query_text=None (no BM25)
    assert store.calls[-1]["query_text"] is None


@pytest.mark.asyncio
async def test_search_memory_tool_hybrid():
    store = FakeTimelineSearch()
    embeddings = FakeEmbeddingService()
    tool = SearchMemoryTool(timeline_summary_store=store, embedding_service=embeddings)

    result = await tool.execute(user_id="12345", mode="hybrid", query="phim")
    assert "Tìm thấy 1 ký ức" in result
    last_call = store.calls[-1]
    assert last_call["method"] == "search"
    assert last_call["query_text"] == "phim"
    assert embeddings.calls[-1] == "query: phim"


@pytest.mark.asyncio
async def test_search_memory_tool_auto_with_query_resolves_hybrid():
    store = FakeTimelineSearch()
    embeddings = FakeEmbeddingService()
    tool = SearchMemoryTool(timeline_summary_store=store, embedding_service=embeddings)

    await tool.execute(user_id="12345", mode="auto", query="phim")
    # auto + query → hybrid
    assert store.calls[-1]["query_text"] == "phim"


@pytest.mark.asyncio
async def test_search_memory_tool_recent():
    store = FakeTimelineSearch()
    embeddings = FakeEmbeddingService()
    tool = SearchMemoryTool(timeline_summary_store=store, embedding_service=embeddings)

    result = await tool.execute(user_id="12345", mode="recent")
    assert "Tìm thấy 1 ký ức" in result
    assert "User nói chào Bé Bảy" in result
    assert "summary_id=sum-2" in result
    assert store.calls[-1]["method"] == "get_recent"


@pytest.mark.asyncio
async def test_search_memory_tool_topic_filter():
    store = FakeTimelineSearch()
    embeddings = FakeEmbeddingService()
    tool = SearchMemoryTool(timeline_summary_store=store, embedding_service=embeddings)

    await tool.execute(user_id="12345", mode="hybrid", query="phim", topic="interest")
    assert store.calls[-1]["topic_filter"] == "interest"


@pytest.mark.asyncio
async def test_update_profile_tool_appends_valid_section():
    store = FakeProfileStore()
    tool = UpdateUserProfileTool(profile_store=store)

    result = await tool.execute(
        user_id="123",
        section="interest",
        content="Thích phim tâm lý",
        source_memory_id="mem-1",
    )

    assert result.startswith("Đã cập nhật")
    assert store.append_calls == [
        {
            "user_id": "123",
            "section": "interest",
            "content": "Thích phim tâm lý",
            "source_memory_id": "mem-1",
        }
    ]


@pytest.mark.asyncio
async def test_update_profile_tool_rejects_invalid_section():
    store = FakeProfileStore()
    tool = UpdateUserProfileTool(profile_store=store)

    result = await tool.execute(user_id="123", section="bad", content="x")

    assert result.startswith("Lỗi: section")
    assert store.append_calls == []


@pytest.mark.asyncio
async def test_get_profile_tool_reads_raw_and_section():
    store = FakeProfileStore()
    tool = GetProfileTool(profile_store=store)

    raw = await tool.execute(user_id="123")
    section = await tool.execute(user_id="123", section="interest")

    assert "## Thông tin cơ bản" in raw
    assert "- Phim tâm lý" in section
    assert "- Cờ vua" in section
