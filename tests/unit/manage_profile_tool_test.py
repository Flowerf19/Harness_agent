import pytest

from twin.shared.tools.modules.profile.manage_profile_tool import ManageUserProfileTool


class Store:
    def __init__(self, response=None, replace_all_response=None):
        self.calls = []
        self.all_calls = []
        self.response = response or {
            "ok": True,
            "conflict": False,
            "profile_hash": "new_hash",
            "written": True,
            "old_count": 1,
            "new_count": 2,
        }
        self.replace_all_response = replace_all_response or {
            "ok": True,
            "conflict": False,
            "profile_hash": "all_hash",
            "written": True,
            "old_total": 3,
            "new_total": 5,
            "sections_changed": ["basic"],
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

    async def replace_all(
        self,
        user_id,
        sections,
        expected_profile_hash=None,
        *,
        allow_shrink=False,
    ):
        self.all_calls.append((user_id, sections, expected_profile_hash, allow_shrink))
        return self.replace_all_response


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


@pytest.mark.asyncio
async def test_manage_user_profile_tool_all_mode_calls_replace_all():
    store = Store()
    tool = ManageUserProfileTool(profile_store=store)

    result = await tool.execute(
        user_id="123",
        expected_profile_hash="old_hash",
        reason="dedup whole profile",
        sections={"basic": ["Tên: Quang"], "interest": ["Code"]},
    )

    assert "Đã ghi toàn bộ hồ sơ user 123" in result
    assert "3 -> 5 bullet" in result
    assert "all_hash" in result
    assert store.calls == []
    assert store.all_calls == [
        ("123", {"basic": ["Tên: Quang"], "interest": ["Code"]}, "old_hash", False)
    ]


@pytest.mark.asyncio
async def test_manage_user_profile_tool_all_mode_rejects_unknown_section():
    store = Store()
    tool = ManageUserProfileTool(profile_store=store)

    result = await tool.execute(
        user_id="123",
        expected_profile_hash="old_hash",
        reason="dedup",
        sections={"bogus": ["x"]},
    )

    assert "section 'bogus' không hợp lệ" in result
    assert store.all_calls == []


@pytest.mark.asyncio
async def test_manage_user_profile_tool_all_mode_reports_shrink_blocked():
    store = Store(replace_all_response={
        "ok": False,
        "shrink_blocked": True,
        "old_total": 8,
        "new_total": 2,
        "profile_hash": "cur_hash",
        "written": False,
    })
    tool = ManageUserProfileTool(profile_store=store)

    result = await tool.execute(
        user_id="123",
        expected_profile_hash="old_hash",
        reason="aggressive dedup",
        sections={"basic": ["Tên: Quang", "Sống ở Hà Nội"]},
    )

    assert "mất >50% bullet" in result
    assert "8 -> 2" in result
    assert "allow_shrink=true" in result


@pytest.mark.asyncio
async def test_manage_user_profile_tool_all_mode_passes_allow_shrink():
    store = Store()
    tool = ManageUserProfileTool(profile_store=store)

    await tool.execute(
        user_id="123",
        expected_profile_hash="old_hash",
        reason="intentional shrink",
        sections={"basic": ["Tên: Quang"]},
        allow_shrink=True,
    )

    assert store.all_calls == [("123", {"basic": ["Tên: Quang"]}, "old_hash", True)]
