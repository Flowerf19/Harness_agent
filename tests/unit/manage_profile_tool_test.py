import pytest

from twin.shared.tools.modules.profile.manage_profile_tool import ManageUserProfileTool


class Store:
    def __init__(self, response=None):
        self.calls = []
        self.response = response or {
            "ok": True,
            "conflict": False,
            "profile_hash": "new_hash",
            "written": True,
            "old_count": 1,
            "new_count": 2,
        }

    async def replace_section(
        self,
        user_id,
        section,
        bullets,
        expected_profile_hash=None,
    ):
        self.calls.append((user_id, section, bullets, expected_profile_hash))
        return self.response


@pytest.mark.asyncio
async def test_manage_user_profile_tool_replaces_one_section():
    store = Store()
    tool = ManageUserProfileTool(profile_store=store)

    result = await tool.execute(
        user_id="123",
        section="basic",
        bullets=["Tên: Quang", "Sống ở Hà Nội"],
        expected_profile_hash="old_hash",
        reason="merge duplicate",
    )

    assert "Đã thay section basic" in result
    assert "1 -> 2 bullet" in result
    assert store.calls == [
        ("123", "basic", ["Tên: Quang", "Sống ở Hà Nội"], "old_hash")
    ]


@pytest.mark.asyncio
async def test_manage_user_profile_tool_reports_conflict_without_success_message():
    tool = ManageUserProfileTool(
        profile_store=Store({
            "ok": False,
            "conflict": True,
            "profile_hash": "fresh_hash",
            "written": False,
        })
    )

    result = await tool.execute(
        user_id="123",
        section="basic",
        bullets=["Tên: Quang"],
        expected_profile_hash="stale_hash",
        reason="resolve conflict",
    )

    assert "Conflict" in result
    assert "fresh_hash" in result


@pytest.mark.asyncio
async def test_manage_user_profile_tool_validates_inputs_before_store_call():
    store = Store()
    tool = ManageUserProfileTool(profile_store=store)

    assert "user_id" in await tool.execute("abc", "basic", ["x"], "h", "r")
    assert "section" in await tool.execute("123", "missing", ["x"], "h", "r")
    assert "bullets phải là list" in await tool.execute("123", "basic", "x", "h", "r")
    assert "prefix" in await tool.execute("123", "basic", ["- x"], "h", "r")
    assert "expected_profile_hash" in await tool.execute("123", "basic", ["x"], "", "r")
    assert "reason" in await tool.execute("123", "basic", ["x"], "h", "")
    assert store.calls == []
