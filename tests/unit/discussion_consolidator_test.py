"""Unit tests for DiscussionConsolidator."""
from __future__ import annotations

import pytest

from twin.shared.memories.discussion_consolidator import (
    DiscussionConsolidator,
    extract_json_object,
)


class _StubLLMResponse:
    def __init__(self, text: str):
        self.content = text


class _StubLLM:
    def __init__(self, text: str):
        self._text = text
        self.calls: list[dict] = []

    async def generate_response(self, *, messages, system_prompt, use_native_tools):
        self.calls.append({
            "messages": messages,
            "system_prompt": system_prompt,
            "use_native_tools": use_native_tools,
        })
        return _StubLLMResponse(self._text)


class _StubT2:
    """Captures embed_page calls; configurable lookup result."""

    def __init__(self, existing: dict | None = None):
        self.existing = existing or {}
        self.embedded: list = []

    async def lookup_by_page_id(self, page_id: str):
        return self.existing.get(page_id)

    async def embed_page(self, page):
        self.embedded.append(page)
        return True


# ---------------------------------------------------------------------------
# extract_json_object
# ---------------------------------------------------------------------------

def test_extract_json_object_plain():
    text = '{"canonical_topic": "a", "status": "ok"}'
    assert extract_json_object(text) == text


def test_extract_json_object_with_markdown_fence():
    text = 'Sure thing!\n```json\n{"canonical_topic": "a"}\n```\nDone.'
    assert extract_json_object(text) == '{"canonical_topic": "a"}'


def test_extract_json_object_bare_in_text():
    text = 'Output: {"canonical_topic": "a"} extra commentary'
    assert extract_json_object(text) == '{"canonical_topic": "a"}'


def test_extract_json_object_rejects_empty():
    with pytest.raises(ValueError):
        extract_json_object("")


def test_extract_json_object_rejects_no_json():
    with pytest.raises(ValueError):
        extract_json_object("This is just prose.")


# ---------------------------------------------------------------------------
# consolidate happy path — single user (1-1 chat)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_consolidate_single_user_creates_one_page():
    llm = _StubLLM(
        '{"canonical_topic": "Python style", "category": "tech",'
        ' "current_summary": "Discussed PEP8.", "key_points": ["pep8"],'
        ' "participants": ["u1"], "active_participants": ["u1"],'
        ' "importance": 3, "confidence": 0.9, "status": "ok"}'
    )
    t2 = _StubT2()
    consolidator = DiscussionConsolidator(llm=llm, t2_memory=t2)

    payload = {
        "scope": "user",
        "scope_id": "u1",
        "reason": "token_limit",
        "from_entry_id": "e1",
        "to_entry_id": "e2",
        "from_ts": "2026-05-25T00:00:00+00:00",
        "to_ts": "2026-05-25T00:05:00+00:00",
        "entries": [
            {"entry_id": "e1", "author_id": "u1", "role": "user", "content": "ask"},
            {"entry_id": "e2", "author_id": "u1", "role": "assistant", "content": "reply"},
        ],
    }

    result = await consolidator.consolidate(payload)
    assert result["status"] == "ok"
    assert result["scope"] == "user"
    assert result["scope_id"] == "u1"
    assert len(result["page_ids"]) == 1
    assert result["summarized_entry_ids"] == ["e1", "e2"]
    assert len(t2.embedded) == 1
    assert t2.embedded[0].user_id == "u1"


# ---------------------------------------------------------------------------
# consolidate happy path — channel multi-user fan-out
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_consolidate_channel_fans_out_to_active_participants():
    llm = _StubLLM(
        '{"canonical_topic": "Python style", "category": "tech",'
        ' "current_summary": "Discussion.", "key_points": ["pep8"],'
        ' "participants": ["alice", "bob", "carol"],'
        ' "active_participants": ["alice", "bob"],'
        ' "importance": 4, "confidence": 0.8, "status": "ok"}'
    )
    t2 = _StubT2()
    consolidator = DiscussionConsolidator(llm=llm, t2_memory=t2)

    payload = {
        "scope": "channel",
        "scope_id": "1234",
        "channel_id": "1234",
        "guild_id": "9999",
        "reason": "idle",
        "from_entry_id": "e1",
        "to_entry_id": "e3",
        "entries": [
            {"entry_id": "e1", "author_id": "alice", "author_name": "Alice", "content": "a"},
            {"entry_id": "e2", "author_id": "bob", "author_name": "Bob", "content": "b"},
            {"entry_id": "e3", "author_id": "carol", "author_name": "Carol", "content": "c"},
        ],
    }

    result = await consolidator.consolidate(payload)
    assert result["status"] == "ok"
    # fan-out only to active_participants (alice + bob), not carol
    assert sorted(result["active_participants"]) == ["alice", "bob"]
    assert len(t2.embedded) == 2
    assert {p.user_id for p in t2.embedded} == {"alice", "bob"}
    # every embedded page knows the full participant list + source_ref
    for page in t2.embedded:
        assert sorted(page.participants) == ["alice", "bob", "carol"]
        assert page.source_refs[0]["channel_id"] == "1234"


# ---------------------------------------------------------------------------
# skipped status — LLM judges noise, no pages created
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_consolidate_skipped_status_creates_no_pages():
    llm = _StubLLM('{"status": "skipped", "canonical_topic": null}')
    t2 = _StubT2()
    consolidator = DiscussionConsolidator(llm=llm, t2_memory=t2)

    payload = {
        "scope": "user",
        "scope_id": "u1",
        "entries": [
            {"entry_id": "e1", "author_id": "u1", "content": "hi"},
        ],
    }
    result = await consolidator.consolidate(payload)
    assert result["status"] == "skipped"
    assert result["page_ids"] == []
    assert result["summarized_entry_ids"] == ["e1"]
    assert t2.embedded == []


# ---------------------------------------------------------------------------
# failure modes — malformed JSON, LLM exception
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_consolidate_handles_malformed_json():
    llm = _StubLLM("not actually json")
    t2 = _StubT2()
    consolidator = DiscussionConsolidator(llm=llm, t2_memory=t2)

    payload = {"scope": "user", "scope_id": "u1", "entries": []}
    result = await consolidator.consolidate(payload)
    assert result["status"] == "failed"
    assert "reason" in result
    assert "retry_after_seconds" in result


@pytest.mark.asyncio
async def test_consolidate_handles_llm_with_markdown_fence():
    """LLM wraps JSON in ```json ... ``` — extract_json_object should rescue it."""
    llm = _StubLLM(
        '```json\n'
        '{"canonical_topic": "x", "current_summary": "s", "key_points": [],'
        ' "participants": ["u1"], "active_participants": ["u1"],'
        ' "status": "ok"}\n'
        '```'
    )
    t2 = _StubT2()
    consolidator = DiscussionConsolidator(llm=llm, t2_memory=t2)

    payload = {
        "scope": "user",
        "scope_id": "u1",
        "entries": [{"entry_id": "e1", "author_id": "u1", "content": "hi"}],
    }
    result = await consolidator.consolidate(payload)
    assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# merge — existing page on lookup is merged, not replaced
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_consolidate_merges_existing_page():
    from twin.shared.memories.t2.models import T2Page, generate_topic_id

    canonical_topic = "Python style"
    page_id = generate_topic_id("u1", canonical_topic)

    existing = T2Page(
        page_id=page_id,
        user_id="u1",
        topic_id=page_id,
        canonical_topic=canonical_topic,
        current_summary="Old summary",
        key_points=["pep8"],
        participants=["u1"],
        source_refs=[{"channel_id": "old"}],
        access_count=0,
    )

    llm = _StubLLM(
        '{"canonical_topic": "Python style", "current_summary": "New summary",'
        ' "key_points": ["pep8", "type hints"], "participants": ["u1"],'
        ' "active_participants": ["u1"], "importance": 4, "confidence": 0.9,'
        ' "status": "ok"}'
    )
    t2 = _StubT2(existing={page_id: existing})
    consolidator = DiscussionConsolidator(llm=llm, t2_memory=t2)

    payload = {
        "scope": "user",
        "scope_id": "u1",
        "channel_id": "new",
        "entries": [{"entry_id": "e1", "author_id": "u1", "content": "x"}],
    }
    result = await consolidator.consolidate(payload)
    assert result["status"] == "ok"
    assert len(t2.embedded) == 1
    merged = t2.embedded[0]
    assert merged.current_summary == "New summary"          # newer wins
    assert merged.key_points == ["pep8", "type hints"]      # deduped union
    assert len(merged.source_refs) == 2                     # appended
    assert merged.access_count == 1                         # bumped
