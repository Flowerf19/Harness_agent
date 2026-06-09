"""Unit tests for the T2 Consolidator (Pass 1 orchestrator)."""
from __future__ import annotations

import pytest

from twin.shared.memory.active.models import ActiveEntry
from twin.shared.memory.timeline import (
    CandidateMemory,
    Consolidator,
    ExtractResult,
    T2Memory,
    T2Topic,
)


# ---------------------------------------------------------------- Fakes


class FakeActiveMemory:
    def __init__(self, entries=None):
        self.entries = entries or []

    async def get_context(self, scope, scope_id, *, limit=200):
        return list(self.entries)


class FakeStore:
    def __init__(self, recent=None):
        self.topics: dict[str, T2Topic] = {}
        self.memories: dict[str, T2Memory] = {}
        self.recent = recent or []

    async def upsert_memory(self, m: T2Memory):
        self.memories[m.memory_id] = m

    async def upsert_topic(self, t: T2Topic):
        self.topics[t.topic_id] = t

    async def recent_topics(self, user_id, k=20):
        return list(self.recent)


class FakeResolver:
    """Returns one T2Topic per topic_name, persisted into a fake store."""

    def __init__(self, store: FakeStore, *, raise_on=None):
        self.store = store
        self.calls: list[tuple] = []
        self.raise_on = raise_on

    async def resolve(self, user_id, proposed_name, *, catalogs=None,
                      content_hint=None, importance=3):
        self.calls.append((user_id, proposed_name, catalogs, content_hint, importance))
        if self.raise_on is not None:
            raise self.raise_on
        # Stable topic_id per (user, name).
        topic_id = f"topic_{user_id}_{proposed_name}"
        existing = self.store.topics.get(topic_id)
        if existing is not None:
            return existing
        topic = T2Topic(
            topic_id=topic_id,
            user_id=user_id,
            name=proposed_name.lower(),
            catalogs=list(catalogs or [])[:4],
            embedding=[0.1] * 8,
            importance=importance,
        )
        await self.store.upsert_topic(topic)
        return topic


class FakeEmbedder:
    def __init__(self):
        self.calls: list[str] = []

    async def get_embedding(self, text):
        self.calls.append(text)
        return [0.1] * 1024


class FakeExtractor:
    """Returns canned ExtractResult."""

    def __init__(self, result: ExtractResult):
        self.result = result
        self.calls: list[tuple] = []

    async def extract(self, transcript, *, t3_snapshot="",
                      topic_glossary=None, participants=None, bot_name=None):
        self.calls.append((transcript, t3_snapshot, topic_glossary, participants, bot_name))
        return self.result


def _entry(content="hello", role="user", author_id="u1", author_name="Hoà"):
    return ActiveEntry(
        scope="user",
        scope_id="u1",
        role=role,
        author_id=author_id,
        author_name=author_name,
        content=content,
        tokens=len(content.split()),
    )


def _cand(**kw) -> CandidateMemory:
    base = dict(
        content="Hoà thích phim Pháp.",
        topic_names=["phim ảnh"],
        catalogs=["interest"],
        importance=3,
        confidence=0.7,
        speaker="user",
        source_msg_ids=["m1"],
        change_type_hint="new",
    )
    base.update(kw)
    return CandidateMemory(**base)


def _build(active_entries=None, extract_result=None, *,
           appender_recorder=None, scheduler_recorder=None,
           profile_reader=None, resolver_raises=None):
    active = FakeActiveMemory(active_entries)
    store = FakeStore()
    resolver = FakeResolver(store, raise_on=resolver_raises)
    extractor = FakeExtractor(extract_result or ExtractResult(
        memories=[], primary_catalog="discussion", primary_confidence=0.2,
    ))
    embedder = FakeEmbedder()

    appender = None
    if appender_recorder is not None:
        async def appender(user_id, section, content, memory_id):
            appender_recorder.append((user_id, section, content, memory_id))

    scheduler = None
    if scheduler_recorder is not None:
        async def scheduler(user_id):
            scheduler_recorder.append(user_id)

    consolidator = Consolidator(
        active=active, store=store, resolver=resolver,
        extractor=extractor, embedder=embedder,
        profile_reader=profile_reader,
        profile_appender=appender,
        cleanup_scheduler=scheduler,
    )
    return consolidator, store, resolver, extractor, embedder


# ---------------------------------------------------------------- Tests


async def test_consolidate_empty_t1_skipped():
    cons, *_ = _build(active_entries=[])
    res = await cons.consolidate(scope="user", scope_id="u1")
    assert res.status == "skipped"
    assert res.memory_ids == []


async def test_consolidate_no_candidates_skipped():
    cons, *_ = _build(
        active_entries=[_entry("hi"), _entry("hello", role="assistant")],
        extract_result=ExtractResult(
            memories=[], primary_catalog="discussion", primary_confidence=0.3,
        ),
    )
    res = await cons.consolidate(scope="user", scope_id="u1")
    assert res.status == "skipped"
    assert len(res.summarized_entry_ids) == 2


async def test_consolidate_writes_memory():
    cons, store, *_ = _build(
        active_entries=[_entry("Hoà thích phim Pháp")],
        extract_result=ExtractResult(
            memories=[_cand()], primary_catalog="interest", primary_confidence=0.8,
        ),
    )
    res = await cons.consolidate(scope="user", scope_id="u1")
    assert res.status == "ok"
    assert len(res.memory_ids) == 1
    assert res.memory_ids[0] in store.memories
    mem = store.memories[res.memory_ids[0]]
    assert mem.content.startswith("Hoà")
    assert mem.catalogs == ["interest"]


async def test_consolidate_resolves_topics():
    cons, store, resolver, *_ = _build(
        active_entries=[_entry("about films")],
        extract_result=ExtractResult(
            memories=[_cand(topic_names=["phim"])],
            primary_catalog="interest", primary_confidence=0.8,
        ),
    )
    res = await cons.consolidate(scope="user", scope_id="u1")
    assert res.status == "ok"
    assert len(resolver.calls) == 1
    assert resolver.calls[0][1] == "phim"
    mem = store.memories[res.memory_ids[0]]
    assert mem.topic_ids == ["topic_u1_phim"]


async def test_consolidate_promotes_to_t3_when_eligible():
    recorder = []
    cons, *_ = _build(
        active_entries=[_entry("Tên là Hoà")],
        extract_result=ExtractResult(
            memories=[_cand(
                content="Tên người dùng là Hoà.",
                catalogs=["identity"],
                importance=5,
                confidence=0.9,
            )],
            primary_catalog="identity", primary_confidence=0.9,
        ),
        appender_recorder=recorder,
    )
    res = await cons.consolidate(scope="user", scope_id="u1")
    assert res.status == "ok"
    assert len(recorder) == 1
    user_id, section, content, mem_id = recorder[0]
    assert section == "basic"
    assert user_id == "u1"
    assert len(res.promoted_to_t3) == 1
    assert res.promoted_to_t3[0]["section"] == "basic"


async def test_consolidate_does_not_promote_low_importance():
    recorder = []
    cons, *_ = _build(
        active_entries=[_entry("x")],
        extract_result=ExtractResult(memories=[_cand(
            catalogs=["identity"], importance=2, confidence=0.9,
        )]),
        appender_recorder=recorder,
    )
    res = await cons.consolidate(scope="user", scope_id="u1")
    assert res.status == "ok"
    assert recorder == []


async def test_consolidate_does_not_promote_when_catalog_not_promotable():
    recorder = []
    cons, *_ = _build(
        active_entries=[_entry("x")],
        extract_result=ExtractResult(memories=[_cand(
            catalogs=["event"], importance=5, confidence=0.95,
        )]),
        appender_recorder=recorder,
    )
    res = await cons.consolidate(scope="user", scope_id="u1")
    assert res.status == "ok"
    assert recorder == []


@pytest.mark.parametrize("catalog", ["discussion", "event", "emotion", "decision"])
async def test_consolidate_does_not_promote_t2only_catalogs(catalog):
    recorder = []
    cons, *_ = _build(
        active_entries=[_entry("x")],
        extract_result=ExtractResult(memories=[_cand(
            catalogs=[catalog], importance=5, confidence=0.95,
        )]),
        appender_recorder=recorder,
    )
    res = await cons.consolidate(scope="user", scope_id="u1")
    assert res.status == "ok"
    assert recorder == [], f"catalog {catalog} should not promote"


async def test_consolidate_schedules_cleanup_on_success():
    scheduled = []
    cons, *_ = _build(
        active_entries=[_entry("x")],
        extract_result=ExtractResult(memories=[_cand()]),
        scheduler_recorder=scheduled,
    )
    res = await cons.consolidate(scope="user", scope_id="u1")
    assert res.status == "ok"
    # Cleanup scheduled is fire-and-forget; let the loop run.
    import asyncio as _aio
    await _aio.sleep(0)
    assert scheduled == ["u1"]


async def test_consolidate_no_cleanup_on_skipped():
    scheduled = []
    cons, *_ = _build(
        active_entries=[_entry("x")],
        extract_result=ExtractResult(memories=[]),
        scheduler_recorder=scheduled,
    )
    res = await cons.consolidate(scope="user", scope_id="u1")
    import asyncio as _aio
    await _aio.sleep(0)
    assert res.status == "skipped"
    assert scheduled == []


async def test_consolidate_catches_exception():
    cons, *_ = _build(
        active_entries=[_entry("x")],
        extract_result=ExtractResult(memories=[_cand()]),
        resolver_raises=RuntimeError("nope"),
    )
    res = await cons.consolidate(scope="user", scope_id="u1")
    assert res.status == "failed"
    assert res.error is not None
    assert "nope" in res.error


async def test_consolidate_caps_catalogs_2_per_memory():
    # Even if upstream slipped through, consolidator must cap to MAX_CATALOGS_PER_MEMORY.
    # Manually build a CandidateMemory with 3 catalogs to test consolidator's own cap.
    cand = CandidateMemory(
        content="x", topic_names=["t"], catalogs=["interest", "habit", "work"],
        importance=3, confidence=0.7, speaker="user",
        source_msg_ids=[], change_type_hint="new",
    )
    cons, store, *_ = _build(
        active_entries=[_entry("x")],
        extract_result=ExtractResult(memories=[cand]),
    )
    res = await cons.consolidate(scope="user", scope_id="u1")
    assert res.status == "ok"
    mem = store.memories[res.memory_ids[0]]
    assert len(mem.catalogs) <= 2


async def test_consolidate_uses_profile_reader():
    seen = []

    async def reader(uid):
        seen.append(uid)
        return "T3 snapshot text"

    cons, _store, _resolver, extractor, _emb = _build(
        active_entries=[_entry("x")],
        extract_result=ExtractResult(memories=[]),
        profile_reader=reader,
    )
    await cons.consolidate(scope="user", scope_id="u1")
    assert seen == ["u1"]
    assert extractor.calls[0][1] == "T3 snapshot text"


async def test_consolidate_channel_routes_memory_by_subject():
    """Channel: one extraction, each memory filed under the participant it's about;
    bot-subject memories are dropped (no cross-profile contamination)."""
    entries = [
        _entry("hôm nay đi làm", author_id="u1", author_name="Hoà"),
        _entry("tớ thích game", author_id="u2", author_name="Quang"),
        _entry("chào cả nhà", role="assistant", author_id=None, author_name="Bé Bảy"),
    ]
    extract_result = ExtractResult(
        memories=[
            _cand(content="Hoà đi làm hôm nay.", subject="Hoà", subject_user_id="u1"),
            _cand(content="Quang thích game.", subject="Quang", subject_user_id="u2"),
            _cand(content="Bé Bảy là trợ lý.", subject="Bé Bảy"),  # bot → dropped
            _cand(
                content="Ai đó nói gì đó.",
                subject="NgườiLạ",
                subject_user_id="unknown",
            ),  # unmatched → dropped
        ],
        primary_catalog="interest", primary_confidence=0.8,
    )
    cons, store, *_ = _build(active_entries=entries, extract_result=extract_result)

    res = await cons.consolidate(scope="channel", scope_id="ch1")

    assert res.status == "ok"
    by_user = {m.content: m.user_id for m in store.memories.values()}
    assert by_user == {"Hoà đi làm hôm nay.": "u1", "Quang thích game.": "u2"}
    # Bot + unknown-subject memories never reached the store.
    assert "Bé Bảy là trợ lý." not in by_user
    assert "Ai đó nói gì đó." not in by_user


async def test_consolidate_channel_drops_name_only_subject_to_avoid_cross_profile_contamination():
    entries = [
        _entry("mình là Hoà", author_id="u1", author_name="AI đang dùng tài khoản này"),
        _entry("chào Hoà", author_id="u2", author_name="Melatonin need Coffee"),
    ]
    extract_result = ExtractResult(
        memories=[
            _cand(
                content="Melatonin need Coffee được gọi là Hoà.",
                subject="Melatonin need Coffee",
                subject_user_id="",
                catalogs=["identity"],
                importance=5,
                confidence=0.95,
            ),
        ],
        primary_catalog="identity",
        primary_confidence=0.95,
    )
    cons, store, *_ = _build(active_entries=entries, extract_result=extract_result)

    res = await cons.consolidate(scope="channel", scope_id="ch1")

    assert res.status == "skipped"
    assert store.memories == {}


async def test_consolidate_channel_routes_by_subject_user_id_not_display_name():
    entries = [
        _entry("mình là Hoà", author_id="u1", author_name="AI đang dùng tài khoản này"),
        _entry("tớ nghe rồi", author_id="u2", author_name="Melatonin need Coffee"),
    ]
    extract_result = ExtractResult(
        memories=[
            _cand(
                content="AI đang dùng tài khoản này 24 tuổi.",
                subject="AI đang dùng tài khoản này",
                subject_user_id="u1",
                catalogs=["identity"],
                importance=5,
                confidence=0.95,
            ),
            _cand(
                content="Melatonin need Coffee nhắc tới Hoà nhưng chưa xác nhận là Hoà.",
                subject="Melatonin need Coffee",
                subject_user_id="u2",
                catalogs=["discussion"],
                importance=2,
                confidence=0.7,
            ),
        ],
        primary_catalog="identity",
        primary_confidence=0.95,
    )
    cons, store, *_ = _build(active_entries=entries, extract_result=extract_result)

    res = await cons.consolidate(scope="channel", scope_id="ch1")

    assert res.status == "ok"
    by_content = {m.content: m.user_id for m in store.memories.values()}
    assert by_content["AI đang dùng tài khoản này 24 tuổi."] == "u1"
    assert by_content[
        "Melatonin need Coffee nhắc tới Hoà nhưng chưa xác nhận là Hoà."
    ] == "u2"


async def test_consolidate_channel_extracts_once_with_bot_name():
    """Channel consolidation makes a single extraction call and passes the bot name."""
    entries = [
        _entry("hi", author_id="u1", author_name="Hoà"),
        _entry("yo", role="assistant", author_id=None, author_name="Bé Bảy"),
    ]
    cons, _store, _resolver, extractor, _emb = _build(
        active_entries=entries,
        extract_result=ExtractResult(memories=[]),
    )
    await cons.consolidate(scope="channel", scope_id="ch1")
    assert len(extractor.calls) == 1
    # extract() call tuple: (transcript, t3_snapshot, topic_glossary, participants, bot_name)
    assert "Hoà [user_id=u1]: hi" in extractor.calls[0][0]
    assert extractor.calls[0][4] == "Bé Bảy"
    assert extractor.calls[0][3] == {"u1": "Hoà"}


async def test_consolidate_channel_no_match_skipped():
    entries = [_entry("hi", author_id="u1", author_name="Hoà")]
    extract_result = ExtractResult(
        memories=[
            _cand(
                content="về người khác",
                subject="KhôngAi",
                subject_user_id="unknown",
            )
        ],
        primary_catalog="interest", primary_confidence=0.6,
    )
    cons, store, *_ = _build(active_entries=entries, extract_result=extract_result)
    res = await cons.consolidate(scope="channel", scope_id="ch1")
    assert res.status == "skipped"
    assert store.memories == {}
    # T1 still flushed so the channel doesn't get stuck re-processing.
    assert len(res.summarized_entry_ids) == 1
