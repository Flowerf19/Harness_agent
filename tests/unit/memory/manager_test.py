"""Integration-style tests for shared memory manager wiring."""
from __future__ import annotations

import json

import pytest

from twin.shared.memory import SharedMemoryManager
from twin.shared.memory.active import (
    ActiveMemory,
    ActiveStore,
    ActiveSummaryPolicy,
    ActiveSummaryStateRepository,
    FastPathDetector,
)
from twin.shared.memory.profile import MarkdownProfileStore
from twin.shared.memory.timeline import ConsolidationResult, T2Memory


class FakeRedis:
    def __init__(self) -> None:
        self.docs: dict[str, str] = {}
        self.zsets: dict[str, dict[str, float]] = {}
        self.hashes: dict[str, dict[str, str]] = {}

    async def execute_command(self, *args):
        if args[0] == "JSON.SET":
            self.docs[args[1]] = args[3]
            return "OK"
        if args[0] == "JSON.GET":
            return self.docs.get(args[1])
        raise RuntimeError(args[0])

    async def zadd(self, key, mapping):
        self.zsets.setdefault(key, {}).update(mapping)

    async def zrange(self, key, start, stop):
        items = sorted(self.zsets.get(key, {}).items(), key=lambda kv: kv[1])
        return [key for key, _ in items[start : stop + 1]]

    async def zrem(self, key, *members):
        for member in members:
            self.zsets.get(key, {}).pop(member, None)

    async def hset(self, key, mapping):
        self.hashes.setdefault(key, {}).update(mapping)

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def delete(self, *keys):
        for key in keys:
            self.docs.pop(key, None)
            self.zsets.pop(key, None)
            self.hashes.pop(key, None)

    async def scan_iter(self, match):
        prefix = match.removesuffix("*")
        for key in list(self.hashes):
            if key.startswith(prefix):
                yield key


class FakeTimelineSearch:
    async def preflight(self, user_id, message):
        return [
            T2Memory(
                user_id=user_id,
                content=f"Memory for {message}",
                catalogs=["interest"],
            )
        ]


class FakeConsolidator:
    def __init__(self):
        self.calls = []

    async def consolidate(self, *, scope, scope_id, user_id=None):
        self.calls.append((scope, scope_id, user_id))
        entries = await self.active.get_context(scope, scope_id)  # type: ignore[attr-defined]
        return ConsolidationResult(
            status="ok",
            scope=scope,
            scope_id=scope_id,
            summarized_entry_ids=[entry.entry_id for entry in entries],
            memory_ids=[f"mem-{user_id or scope_id}"],
        )


class CannedConsolidator:
    """Returns a caller-supplied ConsolidationResult, with scope/scope_id and
    (optionally) the live entry ids filled in at call time."""

    def __init__(self, *, status, fill_summarized_ids=False):
        self.status = status
        self.fill_summarized_ids = fill_summarized_ids
        self.calls = []

    async def consolidate(self, *, scope, scope_id, user_id=None):
        self.calls.append((scope, scope_id, user_id))
        summarized_ids: list[str] = []
        if self.fill_summarized_ids:
            entries = await self.active.get_context(scope, scope_id)  # type: ignore[attr-defined]
            summarized_ids = [e.entry_id for e in entries]
        return ConsolidationResult(
            status=self.status,
            scope=scope,
            scope_id=scope_id,
            summarized_entry_ids=summarized_ids,
        )


def _active() -> ActiveMemory:
    return ActiveMemory(
        store=ActiveStore(FakeRedis()),
        detector=FastPathDetector(),
        token_counter=lambda text: len(text.split()),
    )


async def test_manager_injects_profile_and_preflight_context(tmp_path):
    active = _active()
    profile = MarkdownProfileStore(base_path=str(tmp_path))
    await profile.append_raw("123", "interest", "Thích phim tâm lý")
    manager = SharedMemoryManager(
        active=active,
        profile_store=profile,
        timeline_search=FakeTimelineSearch(),
    )
    await manager.observe_user_message("123", "user", "nhắc lại phim")

    system_prompt, messages = await manager.get_context("123", "phim")

    assert "Thích phim tâm lý" in system_prompt
    assert "Memory for phim" in system_prompt
    assert messages == [{"role": "user", "content": "nhắc lại phim"}]


async def test_get_context_anchors_current_speaker_display_name(tmp_path):
    active = _active()
    profile = MarkdownProfileStore(base_path=str(tmp_path))
    manager = SharedMemoryManager(active=active, profile_store=profile)

    # Channel scope with multiple authors — the header must pin the live speaker.
    await manager.observe_channel_message("g1", "c1", "418", "Quang", "m1", "alo")
    await manager.observe_channel_message("g1", "c1", "726", "Hoà", "m2", "bảy ơi")

    system_prompt, messages = await manager.get_context(
        "726", "bảy ơi", channel_id="c1", user_name="Hoà"
    )

    assert "=== CURRENT USER ===" in system_prompt
    assert "Hoà" in system_prompt
    assert "726" in system_prompt
    assert messages == [
        {"role": "user", "content": "Quang [user_id=418]: alo"},
        {"role": "user", "content": "Hoà [user_id=726]: bảy ơi"},
    ]


async def test_get_context_channel_history_uses_stable_user_ids(tmp_path):
    active = _active()
    profile = MarkdownProfileStore(base_path=str(tmp_path))
    manager = SharedMemoryManager(active=active, profile_store=profile)

    await manager.observe_channel_message(
        "g1", "c1", "726302130318868500", "AI đang dùng tài khoản này", "m1",
        "mình là Hoà",
    )
    await manager.observe_channel_message(
        "g1", "c1", "481133373117693953", "Melatonin need Coffee", "m2",
        "chào Hoà",
    )

    _system_prompt, messages = await manager.get_context(
        "481133373117693953",
        "chào Hoà",
        channel_id="c1",
        user_name="Melatonin need Coffee",
    )

    assert messages == [
        {
            "role": "user",
            "content": "AI đang dùng tài khoản này [user_id=726302130318868500]: mình là Hoà",
        },
        {
            "role": "user",
            "content": "Melatonin need Coffee [user_id=481133373117693953]: chào Hoà",
        },
    ]


async def test_get_context_falls_back_to_id_without_display_name(tmp_path):
    active = _active()
    profile = MarkdownProfileStore(base_path=str(tmp_path))
    manager = SharedMemoryManager(active=active, profile_store=profile)
    await manager.observe_user_message("726", "user", "alo")

    system_prompt, _ = await manager.get_context("726", "alo")

    assert "Platform user ID: 726" in system_prompt


async def test_get_context_injects_mentioned_user_identity(tmp_path):
    active = _active()
    profile = MarkdownProfileStore(base_path=str(tmp_path))
    await profile.append_raw("726302130318868500", "basic", "Tên: Hòa")
    await profile.append_raw(
        "726302130318868500",
        "basic",
        "Được Bé Bảy gọi trực tiếp bằng tên thật",
    )
    manager = SharedMemoryManager(active=active, profile_store=profile)

    system_prompt, _ = await manager.get_context(
        "418621389449199616",
        "biết @AI đang dùng tài khoản này là ai không",
        channel_id="c1",
        user_name="Quang",
        mentioned_users=[
            {
                "user_id": "726302130318868500",
                "display_name": "AI đang dùng tài khoản này",
                "is_bot": False,
            }
        ],
    )

    assert "=== CURRENT USER ===" in system_prompt
    assert "Quang (Platform user ID: 418621389449199616)" in system_prompt
    assert "=== MENTIONED USERS ===" in system_prompt
    assert "AI đang dùng tài khoản này (Platform user ID: 726302130318868500)" in system_prompt
    assert "Tên: Hòa" in system_prompt


async def test_get_context_mentioned_user_lookup_does_not_create_profile(tmp_path):
    active = _active()
    profile = MarkdownProfileStore(base_path=str(tmp_path))
    manager = SharedMemoryManager(active=active, profile_store=profile)

    system_prompt, _ = await manager.get_context(
        "418",
        "người này là ai",
        channel_id="c1",
        user_name="Quang",
        mentioned_users=[{"user_id": "999", "display_name": "Người lạ"}],
    )

    assert "Người lạ (Platform user ID: 999)" in system_prompt
    assert not (tmp_path / "999.md").exists()


async def test_manager_channel_consolidation_extracts_once(tmp_path):
    active = _active()
    profile = MarkdownProfileStore(base_path=str(tmp_path))
    consolidator = FakeConsolidator()
    manager = SharedMemoryManager(
        active=active,
        profile_store=profile,
        consolidator=consolidator,
    )
    consolidator.active = active

    await manager.observe_channel_message("g1", "c1", "u1", "Hoà", "m1", "Hoà thích phim")
    await manager.observe_channel_message("g1", "c1", "u2", "Quang", "m2", "Quang thích game")

    result = await manager.consolidate_scope("channel", "c1")

    assert result["status"] == "ok"
    # No per-participant fan-out: the consolidator is called once for the channel
    # (it routes each memory to the right user internally by subject).
    assert consolidator.calls == [("channel", "c1", None)]
    # Shared T1 cleanup keeps the recent tail by default to preserve continuity.
    assert len(await active.get_context("channel", "c1")) == 2


async def test_manager_does_not_trim_t1_when_extraction_fails(tmp_path):
    """P0 acceptance gate: a failed consolidation must NOT flush T1 — the real
    facts stay in T1 for the next cycle to retry.

    Seeds 7 entries (> keep_recent=5) AND fills summarized_entry_ids, so the
    assertion isolates the status="failed" guard in _trim_if_complete: with a
    full trim payload present, only that guard keeps T1 intact. If the guard
    regressed, trim would delete the oldest 2 (7 -> 5) and this test fails.
    """
    active = _active()
    profile = MarkdownProfileStore(base_path=str(tmp_path))
    consolidator = CannedConsolidator(status="failed", fill_summarized_ids=True)
    manager = SharedMemoryManager(
        active=active, profile_store=profile, consolidator=consolidator,
    )
    consolidator.active = active

    facts = [
        "mình tên Hoà, làm dev backend",
        "mình sống ở Đà Nẵng",
        "công ty mình tên Acme",
        "mình thích phim Pháp",
        "số đt mình là 0901234567",
        "mình học Bách Khoa",
        "mình nuôi một con mèo tên Miu",
    ]
    for fact in facts:
        await manager.observe_user_message("u1", "user", fact)
    assert len(await active.get_context("user", "u1")) == 7

    result = await manager.consolidate_scope("user", "u1")

    assert result["status"] == "failed"
    # T1 preserved in full despite a populated summarized_entry_ids — only the
    # status="failed" guard prevents the trim (a regression would drop to 5).
    assert len(await active.get_context("user", "u1")) == 7


async def test_manager_trims_t1_when_extraction_genuinely_empty(tmp_path):
    """Counterpart to the failure case: a genuine-empty `skipped` result still
    flushes T1 (intentional). keep_recent=5, so seeding 7 lets us observe the
    shrink to the kept tail."""
    active = _active()
    profile = MarkdownProfileStore(base_path=str(tmp_path))
    consolidator = CannedConsolidator(status="skipped", fill_summarized_ids=True)
    manager = SharedMemoryManager(
        active=active, profile_store=profile, consolidator=consolidator,
    )
    consolidator.active = active

    for i in range(7):
        await manager.observe_user_message("u1", "user", f"tin nhắn phiếm số {i}")
    assert len(await active.get_context("user", "u1")) == 7

    result = await manager.consolidate_scope("user", "u1")

    assert result["status"] == "skipped"
    # Trimmed down to the kept recent tail (KEEP_RECENT_MESSAGES_AFTER_SUMMARY=5).
    assert len(await active.get_context("user", "u1")) == 5


async def test_observe_user_message_schedules_curation_for_user_turn(tmp_path):
    active = _active()
    profile = MarkdownProfileStore(base_path=str(tmp_path))
    scheduled: list[str] = []
    manager = SharedMemoryManager(
        active=active,
        profile_store=profile,
        curation_scheduler=scheduled.append,
    )

    await manager.observe_user_message("u1", "user", "alo")

    assert scheduled == ["u1"]


async def test_observe_user_message_assistant_turn_does_not_schedule(tmp_path):
    active = _active()
    profile = MarkdownProfileStore(base_path=str(tmp_path))
    scheduled: list[str] = []
    manager = SharedMemoryManager(
        active=active,
        profile_store=profile,
        curation_scheduler=scheduled.append,
    )

    await manager.observe_user_message("u1", "assistant", "chào bạn")

    # The bot's own turn must never reset the user's curation timer.
    assert scheduled == []


async def test_observe_channel_message_schedules_curation_for_author(tmp_path):
    active = _active()
    profile = MarkdownProfileStore(base_path=str(tmp_path))
    scheduled: list[str] = []
    manager = SharedMemoryManager(
        active=active,
        profile_store=profile,
        curation_scheduler=scheduled.append,
    )

    await manager.observe_channel_message("g1", "c1", "author-9", "Hoà", "m1", "alo")

    # Keyed on the speaking participant, not the channel.
    assert scheduled == ["author-9"]


async def test_active_summary_policy_triggers_active_scope(tmp_path):
    active = _active()
    calls = []

    async def trigger(scope, scope_id):
        calls.append((scope, scope_id))

    await active.observe("user", "u1", "user", "hello")
    repo = ActiveSummaryStateRepository(active)
    policy = ActiveSummaryPolicy(active, trigger, idle_minutes=0)

    assert await repo.list_active("user") == ["u1"]
    await policy.evaluate("user", "u1")

    assert calls == [("user", "u1")]
