"""Unit tests for the T3 ProfileCurator (1 LLM call, dedup → replace_all)."""
from __future__ import annotations

import json

from twin.shared.memory.profile import MarkdownProfileStore
from twin.shared.memory.profile.curator import ProfileCurator
from twin.shared.memory.profile.markdown_store import profile_hash

USER = "user_123"


class _Response:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeLLM:
    def __init__(self, payload: str | Exception = "{}") -> None:
        # A single payload, or a list consumed one-per-call (for retry tests).
        self.payload = payload
        self.calls: list[tuple] = []

    async def generate_response(
        self, messages, system_prompt=None, use_native_tools=False, max_tokens=None
    ):
        self.calls.append((messages, system_prompt, use_native_tools, max_tokens))
        payload = self.payload
        if isinstance(payload, list):
            payload = payload[min(len(self.calls) - 1, len(payload) - 1)]
        if isinstance(payload, Exception):
            raise payload
        return _Response(payload)


def _store(tmp_path) -> MarkdownProfileStore:
    return MarkdownProfileStore(base_path=str(tmp_path))


def _sections_payload(sections: dict) -> str:
    return json.dumps({"sections": sections})


async def test_curate_skips_trivial_profile_without_llm_call(tmp_path):
    store = _store(tmp_path)
    # 3 bullets < PROFILE_CURATION_MIN_BULLETS (4) => skip, no LLM call.
    for i in range(3):
        await store.append_raw(USER, "interest", f"item-{i}")
    llm = FakeLLM(_sections_payload({}))
    curator = ProfileCurator(store, llm)

    result = await curator.curate(USER)

    assert result == {"status": "skip_trivial"}
    assert llm.calls == []


async def test_curate_skips_when_hash_unchanged(tmp_path):
    store = _store(tmp_path)
    for i in range(5):
        await store.append_raw(USER, "interest", f"item-{i}")
    current = await store.read_raw(USER)
    llm = FakeLLM(_sections_payload({}))
    curator = ProfileCurator(store, llm)
    # Seed the marker with the current hash so curation is idempotent.
    curator._set_last_curated_hash(USER, profile_hash(current))

    result = await curator.curate(USER)

    assert result == {"status": "skip_unchanged"}
    assert llm.calls == []


async def test_curate_happy_path_dedups_and_updates_marker(tmp_path):
    store = _store(tmp_path)
    await store.append_raw(USER, "interest", "Cờ vua")
    await store.append_raw(USER, "interest", "cờ vua (chess)")
    await store.append_raw(USER, "interest", "Phim tâm lý")
    await store.append_raw(USER, "basic", "Tên: Quang")
    await store.append_raw(USER, "basic", "Tên: Q")
    await store.append_raw(USER, "basic", "Tuổi: 24")
    # LLM returns a deduped map (6 -> 4 bullets: within the shrink guard, and
    # the result stays above the trivial floor so a re-run is skip_unchanged).
    llm = FakeLLM(_sections_payload({
        "interest": ["Cờ vua", "Phim tâm lý"],
        "basic": ["Tên: Quang", "Tuổi: 24"],
    }))
    curator = ProfileCurator(store, llm)

    result = await curator.curate(USER)

    assert result["status"] == "ok"
    assert len(llm.calls) == 1
    assert await store.read_section(USER, "interest") == ["Cờ vua", "Phim tâm lý"]
    assert await store.read_section(USER, "basic") == ["Tên: Quang", "Tuổi: 24"]
    # Marker updated to the new profile hash so a re-run is a no-op.
    new_hash = profile_hash(await store.read_raw(USER))
    assert curator._last_curated_hash(USER) == new_hash
    # Re-run reads the same (now-deduped) profile → marker matches → skip.
    rerun = await curator.curate(USER)
    assert rerun == {"status": "skip_unchanged"}
    assert len(llm.calls) == 1  # no second LLM call


async def test_curate_parse_failure_does_not_write(tmp_path):
    store = _store(tmp_path)
    for i in range(5):
        await store.append_raw(USER, "interest", f"item-{i}")
    before = await store.read_raw(USER)
    # Both attempts return non-JSON => parse_failed, no write, no marker.
    llm = FakeLLM("chỉ là văn bản, không JSON")
    curator = ProfileCurator(store, llm)

    result = await curator.curate(USER)

    assert result == {"status": "parse_failed"}
    assert len(llm.calls) == 2  # retried once before giving up
    assert await store.read_raw(USER) == before
    assert curator._last_curated_hash(USER) == ""


async def test_curate_conflict_does_not_write_marker(tmp_path):
    store = _store(tmp_path)
    for i in range(5):
        await store.append_raw(USER, "interest", f"item-{i}")

    # replace_all sees a stale expected hash (profile mutated mid-curate) =>
    # conflict, no marker write. Simulate by stubbing replace_all to conflict.
    async def _conflict(*args, **kwargs):
        return {"ok": False, "conflict": True, "written": False}

    store.replace_all = _conflict  # type: ignore[assignment]
    llm = FakeLLM(_sections_payload({"interest": ["item-0", "item-1", "item-2"]}))
    curator = ProfileCurator(store, llm)

    result = await curator.curate(USER)

    assert result == {"status": "conflict"}
    assert curator._last_curated_hash(USER) == ""


async def test_curate_never_raises_on_llm_exception(tmp_path):
    store = _store(tmp_path)
    for i in range(5):
        await store.append_raw(USER, "interest", f"item-{i}")
    before = await store.read_raw(USER)
    llm = FakeLLM(RuntimeError("boom"))
    curator = ProfileCurator(store, llm)

    result = await curator.curate(USER)

    # LLM error maps to parse_failed (no usable output) — must not raise.
    assert result["status"] in {"parse_failed", "error"}
    assert await store.read_raw(USER) == before
    assert curator._last_curated_hash(USER) == ""
