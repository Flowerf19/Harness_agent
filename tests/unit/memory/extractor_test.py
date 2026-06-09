"""Unit tests for the T2 Extractor (1 LLM call, JSON parse, filter + cap)."""
from __future__ import annotations

import json

import pytest

from twin.shared.memory.timeline import (
    CandidateMemory,
    Extractor,
    ExtractResult,
    T2Topic,
)


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


def _payload(memories: list[dict], primary_catalog: str = "interest",
             primary_confidence: float = 0.7) -> str:
    return json.dumps({
        "memories": memories,
        "primary_catalog": primary_catalog,
        "primary_confidence": primary_confidence,
    })


def _mem(**kw) -> dict:
    base = {
        "content": "Hoà thích phim Pháp.",
        "topic_names": ["phim ảnh"],
        "catalogs": ["interest"],
        "importance": 3,
        "confidence": 0.8,
        "speaker": "user",
        "source_msg_ids": ["m1"],
        "change_type_hint": "new",
    }
    base.update(kw)
    return base


async def test_extract_empty_transcript_returns_empty():
    llm = FakeLLM(_payload([], primary_catalog="discussion", primary_confidence=0.1))
    ex = Extractor(llm)
    res = await ex.extract("")
    assert isinstance(res, ExtractResult)
    assert res.memories == []
    # No LLM call for empty transcript.
    assert llm.calls == []


async def test_extract_parses_valid_json():
    llm = FakeLLM(_payload([
        _mem(content="Hoà thích phim Pháp."),
        _mem(content="Hoà làm dev backend.", catalogs=["work"], topic_names=["công việc"]),
    ]))
    ex = Extractor(llm)
    res = await ex.extract("transcript here")
    assert len(res.memories) == 2
    assert res.memories[0].content.startswith("Hoà thích")
    assert res.memories[1].catalogs == ["work"]
    assert res.primary_catalog == "interest"


async def test_extract_strips_markdown_fence():
    inner = _payload([_mem()])
    llm = FakeLLM(f"```json\n{inner}\n```")
    ex = Extractor(llm)
    res = await ex.extract("anything")
    assert len(res.memories) == 1


async def test_extract_drops_invalid_catalog():
    llm = FakeLLM(_payload([
        _mem(catalogs=["banana"]),
        _mem(content="kept", catalogs=["interest"]),
    ]))
    ex = Extractor(llm)
    res = await ex.extract("x")
    # Invalid-catalog memory dropped; valid kept.
    assert len(res.memories) == 1
    assert res.memories[0].content == "kept"


async def test_extract_caps_max_candidates():
    mems = [_mem(content=f"m{i}") for i in range(10)]
    llm = FakeLLM(_payload(mems))
    ex = Extractor(llm)
    res = await ex.extract("x")
    assert len(res.memories) == 5  # MAX_CANDIDATES_PER_TRANSCRIPT


async def test_extract_caps_catalogs_per_memory():
    llm = FakeLLM(_payload([
        _mem(catalogs=["interest", "habit", "work", "identity"]),
    ]))
    ex = Extractor(llm)
    res = await ex.extract("x")
    assert len(res.memories) == 1
    assert len(res.memories[0].catalogs) == 2


async def test_extract_coerces_string_catalog_to_list():
    llm = FakeLLM(_payload([
        _mem(catalogs="emotion"),
    ]))
    ex = Extractor(llm)
    res = await ex.extract("x")
    assert len(res.memories) == 1
    assert res.memories[0].catalogs == ["emotion"]


async def test_extract_invalid_json_returns_empty():
    llm = FakeLLM("garbage not json")
    ex = Extractor(llm)
    res = await ex.extract("x")
    assert res.memories == []
    assert res.primary_catalog == "discussion"


async def test_extract_llm_raises_returns_empty():
    llm = FakeLLM(RuntimeError("boom"))
    ex = Extractor(llm)
    res = await ex.extract("x")
    assert res.memories == []
    assert res.primary_catalog == "discussion"


async def test_extract_parses_json_amid_reasoning_prose():
    """Reasoning model wraps the answer in chain-of-thought — brace scan finds it."""
    inner = _payload([_mem(content="kept")])
    noisy = f"Chúng ta cần phân tích...\nĐầu tiên xác định người dùng.\n{inner}\nDone."
    ex = Extractor(FakeLLM(noisy))
    res = await ex.extract("x")
    assert len(res.memories) == 1
    assert res.memories[0].content == "kept"


async def test_extract_retries_once_when_first_call_has_no_json():
    """First call returns pure reasoning (no JSON) → retry with strict prompt succeeds."""
    valid = _payload([_mem(content="kept")])
    llm = FakeLLM(["Chúng ta cần phân tích đoạn hội thoại, không có JSON ở đây.", valid])
    ex = Extractor(llm)
    res = await ex.extract("x")
    assert len(res.memories) == 1
    assert len(llm.calls) == 2  # retried exactly once
    # The retry tightened the system prompt to demand JSON only.
    assert "KHÔNG suy luận" in llm.calls[1][1]


async def test_extract_gives_up_after_retry():
    """Both attempts return no JSON → empty result, no raise, capped at 2 calls."""
    llm = FakeLLM("chỉ là văn bản, không JSON")
    ex = Extractor(llm)
    res = await ex.extract("x")
    assert res.memories == []
    assert res.primary_catalog == "discussion"
    assert len(llm.calls) == 2


async def test_extract_keeps_subject_field():
    llm = FakeLLM(_payload([_mem(subject="Hoà", subject_user_id="726")]))
    ex = Extractor(llm)
    res = await ex.extract("x")
    assert res.memories[0].subject == "Hoà"
    assert res.memories[0].subject_user_id == "726"


async def test_extract_prompt_includes_bot_and_participants():
    llm = FakeLLM(_payload([]))
    ex = Extractor(llm)
    await ex.extract(
        "Hoà: hi\nBot: chào",
        participants={"726": "Hoà", "418": "Quang"},
        bot_name="Bé Bảy",
    )
    user_msg = llm.calls[0][0][0]["content"]
    assert "Bé Bảy" in user_msg
    assert "Hoà (Platform user ID: 726)" in user_msg
    assert "Quang (Platform user ID: 418)" in user_msg


async def test_extract_prompt_requires_subject_user_id():
    llm = FakeLLM(_payload([]))
    ex = Extractor(llm)
    await ex.extract(
        "Melatonin need Coffee [user_id=481]: chào Hoà",
        participants={"481": "Melatonin need Coffee", "726": "AI đang dùng tài khoản này"},
    )
    system_prompt = llm.calls[0][1]
    user_msg = llm.calls[0][0][0]["content"]
    assert "subject_user_id" in system_prompt
    assert "chọn từ === NGƯỜI THAM GIA ===" in system_prompt
    assert "Melatonin need Coffee (Platform user ID: 481)" in user_msg
    assert "AI đang dùng tài khoản này (Platform user ID: 726)" in user_msg


async def test_extract_passes_generous_max_tokens():
    from twin.shared.memory.timeline.constants import EXTRACT_MAX_TOKENS
    llm = FakeLLM(_payload([]))
    ex = Extractor(llm)
    await ex.extract("x")
    assert llm.calls[0][3] == EXTRACT_MAX_TOKENS


async def test_extract_with_glossary_includes_topics_in_prompt():
    glossary = [
        T2Topic(user_id="u1", name="phim ảnh", aliases=["film"], catalogs=["interest"]),
    ]
    llm = FakeLLM(_payload([]))
    ex = Extractor(llm)
    await ex.extract("x", topic_glossary=glossary)
    assert llm.calls, "LLM should be called"
    user_msg = llm.calls[0][0][0]["content"]
    assert "phim ảnh" in user_msg
    assert "film" in user_msg
