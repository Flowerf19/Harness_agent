"""Unit tests for T3 MarkdownProfileStore."""
from __future__ import annotations

import asyncio

import pytest

from twin.shared.memory.profile import (
    DEFAULT_PROFILE_DIR,
    SECTION_HEADERS,
    SECTIONS,
    MarkdownProfileStore,
    ProfileSection,
)
from twin.shared.memory.profile.constants import (
    EMPTY_PLACEHOLDER,
    PROFILE_FOOTER_HINT,
    PROFILE_HEADER,
)


USER = "user_123"


def _store(tmp_path) -> MarkdownProfileStore:
    return MarkdownProfileStore(base_path=str(tmp_path))


async def test_read_raw_creates_default_skeleton_for_new_user(tmp_path):
    store = _store(tmp_path)
    text = await store.read_raw(USER)
    for header in SECTION_HEADERS.values():
        assert f"## {header}" in text
    # Eight placeholder lines, one per section.
    assert text.count(f"- {EMPTY_PLACEHOLDER}") == len(SECTIONS)
    assert (tmp_path / f"{USER}.md").exists()


async def test_read_section_returns_empty_list_when_only_placeholder(tmp_path):
    store = _store(tmp_path)
    for section in SECTIONS:
        assert await store.read_section(USER, section) == []


async def test_append_raw_replaces_placeholder_first_time(tmp_path):
    store = _store(tmp_path)
    appended = await store.append_raw(USER, "basic", "Danh xưng: Quang")
    assert appended is True
    bullets = await store.read_section(USER, "basic")
    assert bullets == ["Danh xưng: Quang"]
    raw = await store.read_raw(USER)
    # No placeholder under basic (other empty sections still hold one each).
    basic_block = raw.split(f"## {SECTION_HEADERS['basic']}", 1)[1].split("## ", 1)[0]
    assert EMPTY_PLACEHOLDER not in basic_block


async def test_append_raw_appends_after_existing_bullets(tmp_path):
    store = _store(tmp_path)
    assert await store.append_raw(USER, "interest", "Phim tâm lý") is True
    assert await store.append_raw(USER, "interest", "Cờ vua") is True
    bullets = await store.read_section(USER, "interest")
    assert bullets == ["Phim tâm lý", "Cờ vua"]


async def test_append_raw_skips_exact_duplicate_case_insensitive(tmp_path):
    store = _store(tmp_path)
    assert await store.append_raw(USER, "interest", "Phim tâm lý") is True
    assert await store.append_raw(USER, "interest", "phim TÂM lý") is False
    bullets = await store.read_section(USER, "interest")
    assert bullets == ["Phim tâm lý"]


async def test_append_raw_skips_empty_content(tmp_path):
    store = _store(tmp_path)
    assert await store.append_raw(USER, "basic", "   ") is False
    assert await store.read_section(USER, "basic") == []


async def test_append_raw_invalid_section_raises(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        await store.append_raw(USER, "not_a_section", "anything")


async def test_invalid_user_id_raises(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        await store.read_raw("../etc/passwd")
    with pytest.raises(ValueError):
        await store.append_raw("../etc/passwd", "basic", "x")
    with pytest.raises(ValueError):
        await store.read_raw("")


async def test_write_raw_overwrites_atomically(tmp_path):
    store = _store(tmp_path)
    custom = "## Custom\n- one\n- two\n"
    assert await store.write_raw(USER, custom) is True
    assert await store.read_raw(USER) == custom


async def test_get_system_prompt_context_skips_empty_sections(tmp_path):
    store = _store(tmp_path)
    await store.append_raw(USER, "interest", "Phim tâm lý")
    rendered = await store.get_system_prompt_context(USER)
    assert PROFILE_HEADER in rendered
    assert f"## {SECTION_HEADERS['interest']}" in rendered
    assert "- Phim tâm lý" in rendered
    # Empty sections must NOT be present.
    for key in SECTIONS:
        if key == "interest":
            continue
        assert f"## {SECTION_HEADERS[key]}" not in rendered
    assert EMPTY_PLACEHOLDER not in rendered
    assert PROFILE_FOOTER_HINT in rendered


async def test_get_system_prompt_context_empty_returns_empty_string(tmp_path):
    store = _store(tmp_path)
    assert await store.get_system_prompt_context(USER) == ""


async def test_concurrent_appends_serialize(tmp_path):
    store = _store(tmp_path)
    items = [f"item-{i}" for i in range(10)]
    results = await asyncio.gather(
        *(store.append_raw(USER, "interest", item) for item in items)
    )
    assert all(results)
    bullets = await store.read_section(USER, "interest")
    assert sorted(bullets) == sorted(items)
    assert len(bullets) == 10
    raw = await store.read_raw(USER)
    # File well-formed: each section header appears exactly once.
    for header in SECTION_HEADERS.values():
        assert raw.count(f"## {header}") == 1


async def test_section_order_is_canonical(tmp_path):
    store = _store(tmp_path)
    await store.append_raw(USER, "rules", "Không nói tục")
    await store.append_raw(USER, "basic", "Danh xưng: Quang")
    await store.append_raw(USER, "interest", "Cờ vua")
    raw = await store.read_raw(USER)
    positions = [(key, raw.index(f"## {SECTION_HEADERS[key]}")) for key in SECTIONS]
    keys_in_order = [key for key, _ in sorted(positions, key=lambda kv: kv[1])]
    assert keys_in_order == SECTIONS


async def test_read_raw_round_trips_after_writes(tmp_path):
    store = _store(tmp_path)
    await store.append_raw(USER, "basic", "Danh xưng: Quang")
    await store.append_raw(USER, "basic", "Tuổi: 24")
    await store.append_raw(USER, "interest", "Phim tâm lý")
    snapshot = await store.read_raw(USER)
    assert await store.write_raw(USER, snapshot) is True
    assert await store.read_raw(USER) == snapshot


async def test_profile_section_enum_values_match_sections_constant():
    assert [s.value for s in ProfileSection] == SECTIONS
    assert DEFAULT_PROFILE_DIR == "memories"
