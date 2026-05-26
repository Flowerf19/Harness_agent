import json
from unittest.mock import AsyncMock

import pytest

from twin.evernight.agent import EvernightAgent
from twin.shared.llm.llm_response import LLMResponse
from twin.shared.memories.t2.models import T2Chunk, T2Page, generate_topic_id
from twin.shared.tools.registry import ToolExecutionError, ToolRegistry
from twin.shared.tools.modules.memory.consolidate_t2_memory_tool import ConsolidateT2MemoryTool


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def generate_response(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeT2Memory:
    def __init__(self):
        self.pages = {}
        self.upserts = []

    async def lookup_by_page_id(self, page_id):
        return self.pages.get(page_id)

    async def upsert_page_with_chunk(self, page, chunk, facts):
        self.pages[page.page_id] = page
        self.upserts.append((page, chunk, facts))
        return True


def _valid_entry(message_id="m1"):
    return {
        "canonical_topic": "Redis_T2",
        "topic_aliases": ["T2"],
        "category": "project",
        "entities": ["Redis"],
        "summary": "User discussed Redis-backed T2 memory.",
        "key_points": ["T2 stores durable memory in Redis."],
        "resolution_status": "open",
        "user_sentiment": "neutral",
        "chunk_content": "On 2026-05-16, the user discussed Redis-backed T2 memory.",
        "source_message_ids": [message_id],
        "event_date": "2026-05-16",
        "facts": ["T2 stores durable memory in Redis."],
        "decision_changes": {},
        "importance": 4,
        "confidence": 0.9,
    }


def test_registry_hides_consolidation_tool_from_march7():
    registry = ToolRegistry(agent_name="march7")
    registry.register_tool(ConsolidateT2MemoryTool())

    names = [schema["function"]["name"] for schema in registry.get_all_openai_schemas()]

    assert "consolidate_t2_memory" not in names


def test_registry_shows_consolidation_tool_to_evernight():
    registry = ToolRegistry(agent_name="evernight")
    registry.register_tool(ConsolidateT2MemoryTool())

    names = [schema["function"]["name"] for schema in registry.get_all_openai_schemas()]

    assert "consolidate_t2_memory" in names


@pytest.mark.asyncio
async def test_march7_cannot_execute_consolidation_tool():
    registry = ToolRegistry(agent_name="march7")
    registry.register_tool(ConsolidateT2MemoryTool(memory_manager=FakeT2Memory(), llm_service=FakeLLM([])))

    with pytest.raises(ToolExecutionError, match="không có quyền"):
        await registry.execute_tool(
            "consolidate_t2_memory",
            {"user_id": "123", "snapshot": [], "reason": "manual"},
        )


@pytest.mark.asyncio
async def test_consolidation_tool_rejects_missing_chunk_content():
    llm = FakeLLM([json.dumps([{**_valid_entry(), "chunk_content": ""}])])
    tool = ConsolidateT2MemoryTool(memory_manager=FakeT2Memory(), llm_service=llm)

    with pytest.raises(ToolExecutionError, match="chunk_content"):
        await tool.execute(
            user_id="123",
            snapshot=[{"message_id": "m1", "role": "user", "content": "hello"}],
            reason="manual",
        )


@pytest.mark.asyncio
async def test_consolidation_tool_writes_chunk_source_ids_and_event_date():
    memory = FakeT2Memory()
    llm = FakeLLM([json.dumps([_valid_entry()])])
    tool = ConsolidateT2MemoryTool(memory_manager=memory, llm_service=llm)

    result = await tool.execute(
        user_id="123",
        snapshot=[{"message_id": "m1", "role": "user", "content": "T2 uses Redis"}],
        reason="manual",
    )

    assert result.startswith("OK:")
    page, chunk, facts = memory.upserts[0]
    assert isinstance(page, T2Page)
    assert isinstance(chunk, T2Chunk)
    assert chunk.content == _valid_entry()["chunk_content"]
    assert chunk.source_message_ids == ["m1"]
    assert chunk.event_date.date().isoformat() == "2026-05-16"
    assert facts[0].introduced_at_chunk_id == chunk.chunk_id


@pytest.mark.asyncio
async def test_evernight_consolidate_returns_false_when_tool_not_called():
    llm = FakeLLM([LLMResponse(content="No tool call")])
    agent = EvernightAgent(llm_service=llm, tool_registry=ToolRegistry(agent_name="evernight"))

    assert await agent.consolidate("123", [{"role": "user", "content": "hello"}]) is False


@pytest.mark.asyncio
async def test_evernight_consolidate_calls_tool_and_writes_t2():
    user_id = "123"
    snapshot = [{"message_id": "m1", "role": "user", "content": "T2 uses Redis"}]
    first_response = LLMResponse(
        content="",
        tool_calls=[
            {
                "id": "call_1",
                "name": "consolidate_t2_memory",
                "arguments": {"user_id": user_id, "snapshot": snapshot, "reason": "overflow"},
            }
        ],
    )
    memory = FakeT2Memory()
    llm = FakeLLM([first_response, json.dumps([_valid_entry()])])
    registry = ToolRegistry(agent_name="evernight")
    registry.register_tool(ConsolidateT2MemoryTool(memory_manager=memory, llm_service=llm))
    agent = EvernightAgent(llm_service=llm, tool_registry=registry)

    success = await agent.consolidate(user_id, snapshot, reason="overflow")

    assert success is True
    assert generate_topic_id(user_id, "Redis_T2") in memory.pages
    assert llm.calls[0]["use_native_tools"] is True
    assert llm.calls[1]["use_native_tools"] is False
