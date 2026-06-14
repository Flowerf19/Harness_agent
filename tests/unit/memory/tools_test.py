"""Unit tests for memory/profile system tools."""
from __future__ import annotations

import pytest

from twin.shared.tools.modules.memory.search_memory_tool import SearchMemoryTool
from twin.shared.tools.modules.profile.get_profile_tool import GetProfileTool
from twin.shared.tools.modules.profile.update_profile_tool import UpdateUserProfileTool


class FakeTimelineSearch:
    def __init__(self):
        self.calls: list[dict] = []

    async def search(self, **kwargs):
        self.calls.append(kwargs)
        return [
            {
                "memory_id": "mem-1",
                "user_id": kwargs["user_id"],
                "content": "User thích phim tâm lý.",
                "catalogs": ["interest"],
            }
        ]


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
async def test_search_memory_tool_returns_disabled_message():
    tool = SearchMemoryTool(timeline_search=None)
    result = await tool.execute(user_id="123", mode="semantic", query="phim")
    assert "vô hiệu hóa" in result


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
