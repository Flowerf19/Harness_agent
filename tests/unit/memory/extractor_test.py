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
        self.payload = payload
        self.calls: list[tuple] = []

    async def generate_response(
        self, messages, system_prompt=None, use_native_tools=False
    ):
        self.calls.append((messages, system_prompt, use_native_tools))
        if isinstance(self.payload, Exception):
            raise self.payload
        return _Response(self.payload)


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
