"""Unit tests for memory/profile system tools."""
from __future__ import annotations

import pytest

from twin.shared.tools.modules.memory.search_memory_tool import SearchMemoryTool
from twin.shared.tools.modules.profile.get_profile_tool import GetProfileTool
from twin.shared.tools.modules.profile.update_profile_tool import UpdateUserProfileTool


class FakeTimelineSearch:
    def __init__(self):
        self.calls: list[dict] = []

    async def search(self, user_id, query_embedding, limit):
        self.calls.append({"method": "search", "user_id": user_id, "query_embedding": query_embedding, "limit": limit})
        return [
            {
                "summary_id": "sum-1",
                "user_id": user_id,
                "content": "User thích phim tâm lý.",
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
                "content": "User nói chào Bé Bảy.",
                "importance": 4,
                "created_at": 1718370000.0,
            }
        ]


class FakeEmbeddingService:
    async def get_embedding(self, text):
        return [0.1] * 1024


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
async def test_search_memory_tool_execution():
    store = FakeTimelineSearch()
    embeddings = FakeEmbeddingService()
    tool = SearchMemoryTool(timeline_summary_store=store, embedding_service=embeddings)

    # Test semantic mode
    result_semantic = await tool.execute(user_id="12345", mode="semantic", query="phim")
    assert "Tìm thấy 1 ký ức" in result_semantic
    assert "User thích phim tâm lý" in result_semantic
    assert "summary_id=sum-1" in result_semantic
    assert store.calls[-1]["method"] == "search"

    # Test recent mode
    result_recent = await tool.execute(user_id="12345", mode="recent")
    assert "Tìm thấy 1 ký ức" in result_recent
    assert "User nói chào Bé Bảy" in result_recent
    assert "summary_id=sum-2" in result_recent
    assert store.calls[-1]["method"] == "get_recent"


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
