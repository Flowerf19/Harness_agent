"""Tests for the AgentLoop orchestration: Think(Decide) -> Think(Refine) -> Act -> ... -> Think(Resolve).

Covers no-tool path, one-tool path order, first-tool-only behavior, refine JSON
validation, prerequisite routing, rejected tool switching, timeout/error behavior,
Act does not call the LLM, and prompt-scope correctness.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from twin.shared.llm.llm_response import LLMResponse
from twin.shared.agent.contract import SAFE_REFINE_FAILURE_REPLY
from twin.shared.agent.agent_loop import AgentLoop, TOOL_SELECTION_MAX_TOKENS
from twin.shared.agent.act import Act


class FakeLLM:
    """Records calls and returns queued responses."""

    def __init__(self, responses: list[Any] | None = None):
        self.responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []

    async def generate_response(
        self,
        messages,
        system_prompt=None,
        use_native_tools=False,
        include_tool_catalog=True,
        max_tokens=None,
        tool_choice=None,
    ):
        self.calls.append(
            {
                "messages": list(messages),
                "system_prompt": system_prompt,
                "use_native_tools": use_native_tools,
                "include_tool_catalog": include_tool_catalog,
                "max_tokens": max_tokens,
            }
        )
        return self.responses.pop(0)


class FakeCatalog:
    def __init__(self):
        self.loaded: list[str] = []

    def render_tool_guide(self, tool_name: str) -> str:
        self.loaded.append(tool_name)
        return f'<tool_guide name="{tool_name}">\n{tool_name}: guide\n\n## {tool_name}\nUse carefully.\n</tool_guide>'

    def render_catalog(self) -> str:
        return "catalog: get_profile, manage_user_profile, search_memory, web_search"

    def allowed_tool_names(self) -> set[str]:
        return {"get_profile", "manage_user_profile", "search_memory", "web_search"}


class FakeRegistry:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]):
        self.calls.append({"tool_name": tool_name, "arguments": arguments})
        return f"result for {tool_name}: {arguments}"


class FakeRegistryWithSchema(FakeRegistry):
    """Registry that exposes get_tool_schema so the loop can detect unmet
    required args and allow refine to route to a prerequisite tool."""

    def __init__(self, required_by_tool: dict[str, set[str]]):
        super().__init__()
        self._required = required_by_tool

    def get_tool_schema(self, tool_name: str) -> dict[str, Any] | None:
        required = self._required.get(tool_name)
        if required is None:
            return None
        return {
            "type": "function",
            "function": {
                "name": tool_name,
                "parameters": {"type": "object", "required": list(required)},
            },
        }


def _tool_response(*tool_calls):
    return LLMResponse(content="", tool_calls=list(tool_calls))


def _text_response(text: str) -> LLMResponse:
    return LLMResponse(content=text)


def _make_loop(
    llm: FakeLLM,
    registry: FakeRegistry | None = None,
    catalog: FakeCatalog | None = None,
    max_iterations: int = 10,
) -> AgentLoop:
    return AgentLoop(
        llm=llm,
        tool_registry=registry or FakeRegistry(),
        tool_prompt_catalog=catalog or FakeCatalog(),
        use_native_tools=True,
        llm_type="openai",
        logger=logging.getLogger(__name__),
        max_iterations=max_iterations,
        tool_timeout=60,
    )


# ---------------------------------------------------------------------------
# No-tool path
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_tool_path_calls_decide_then_resolve():
    """Decide(native on) -> Resolve(native off); returned content is Resolve response."""
    llm = FakeLLM([_text_response("decide draft"), _text_response("resolved answer")])
    loop = _make_loop(llm)
    messages = [{"role": "user", "content": "hello"}]

    result = await loop.run(messages=messages, system_prompt="sys")

    assert result.response == "resolved answer"
    assert result.stopped_by == "no_tool"
    assert result.tools_executed == 0
    assert result.iterations == 1
    assert len(llm.calls) == 2

    # Decide
    assert llm.calls[0]["use_native_tools"] is True
    assert llm.calls[0]["include_tool_catalog"] is True
    # Resolve
    assert llm.calls[1]["use_native_tools"] is False
    assert llm.calls[1]["include_tool_catalog"] is True


# ---------------------------------------------------------------------------
# One-tool path order
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_one_tool_path_order():
    """Decide(native on) -> Refine(native off) -> Act -> Decide(native on) -> Resolve(native off)."""
    llm = FakeLLM(
        [
            _tool_response(
                {"id": "call_1", "name": "search_memory", "arguments": {"query": "rough"}},
                {"id": "call_2", "name": "web_search", "arguments": {"query": "ignored"}},
            ),
            _text_response(
                json.dumps(
                    {
                        "action": "call_tool",
                        "tool_name": "search_memory",
                        "arguments": {"user_id": "123", "query": "refined"},
                    }
                )
            ),
            _text_response("no more tools"),
            _text_response("final answer"),
        ]
    )
    registry = FakeRegistry()
    catalog = FakeCatalog()
    messages = [{"role": "user", "content": "remember?"}]
    loop = _make_loop(llm, registry=registry, catalog=catalog)

    result = await loop.run(messages=messages, system_prompt="sys")

    assert result.response == "final answer"
    assert result.stopped_by == "no_tool"
    assert result.tools_executed == 1
    assert result.iterations == 2
    assert len(llm.calls) == 4

    # Stage sequence
    assert llm.calls[0]["use_native_tools"] is True   # Decide 1
    assert llm.calls[1]["use_native_tools"] is False  # Refine
    assert llm.calls[2]["use_native_tools"] is True   # Decide 2
    assert llm.calls[3]["use_native_tools"] is False  # Resolve

    # First-tool-only: only search_memory executed, web_search deferred
    assert registry.calls == [
        {"tool_name": "search_memory", "arguments": {"user_id": "123", "query": "refined"}}
    ]
    assert catalog.loaded == ["search_memory"]

    # Messages contain tool call and result
    assert len(messages) == 3
    assert messages[1]["role"] == "assistant"
    assert messages[1]["tool_calls"][0]["function"]["name"] == "search_memory"
    assert "web_search" not in json.dumps(messages[1], ensure_ascii=False)
    assert messages[2]["role"] == "tool"
    assert messages[2]["tool_call_id"] == "call_1"


# ---------------------------------------------------------------------------
# First-tool-only behavior
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_first_tool_only_defer_extra():
    """When Decide returns multiple tool calls, only the first is selected."""
    llm = FakeLLM(
        [
            _tool_response(
                {"id": "a", "name": "t1", "arguments": {}},
                {"id": "b", "name": "t2", "arguments": {}},
                {"id": "c", "name": "t3", "arguments": {}},
            ),
            _text_response(json.dumps({"action": "call_tool", "tool_name": "t1", "arguments": {}})),
            _text_response("done"),
            _text_response("final answer"),
        ]
    )
    registry = FakeRegistry()
    catalog = FakeCatalog()
    messages = [{"role": "user", "content": "x"}]
    loop = _make_loop(llm, registry=registry, catalog=catalog)

    result = await loop.run(messages=messages, system_prompt="sys")

    assert result.tools_executed == 1
    assert registry.calls == [{"tool_name": "t1", "arguments": {}}]
    assert catalog.loaded == ["t1"]


# ---------------------------------------------------------------------------
# Refine JSON validation and safe failure reply
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_invalid_refine_json_returns_safe_failure_reply():
    """Bad refine JSON stops the loop and Resolve returns the safe failure text."""
    llm = FakeLLM(
        [
            _tool_response({"id": "call_1", "name": "web_search", "arguments": {"query": "x"}}),
            _text_response("not json"),
            _text_response("safe answer"),
        ]
    )
    registry = FakeRegistry()
    messages = [{"role": "user", "content": "hello"}]
    loop = _make_loop(llm, registry=registry)

    result = await loop.run(messages=messages, system_prompt="sys")

    assert result.stopped_by == "error"
    assert result.response == "safe answer"
    assert registry.calls == []


@pytest.mark.asyncio
async def test_refine_respond_routes_through_resolve():
    """Refine respond does not become output directly; Resolve synthesizes it."""
    llm = FakeLLM(
        [
            _tool_response({"id": "call_1", "name": "web_search", "arguments": {"query": "x"}}),
            _text_response(json.dumps({"action": "respond", "response": "Khong can search."})),
            _text_response("resolved: Khong can search."),
        ]
    )
    registry = FakeRegistry()
    messages = [{"role": "user", "content": "hello"}]
    loop = _make_loop(llm, registry=registry)

    result = await loop.run(messages=messages, system_prompt="sys")

    assert result.stopped_by == "respond"
    assert result.response == "resolved: Khong can search."
    assert registry.calls == []
    # A context note was appended so Resolve knows why
    assert any("Khong can search" in str(m.get("content", "")) for m in messages)


# ---------------------------------------------------------------------------
# Prerequisite routing when required args are missing
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_refine_routes_to_prerequisite_when_required_arg_missing():
    llm = FakeLLM(
        [
            _tool_response(
                {
                    "id": "call_1",
                    "name": "manage_user_profile",
                    "arguments": {"user_id": "123", "reason": "dedup"},
                }
            ),
            _text_response(
                json.dumps(
                    {
                        "action": "call_tool",
                        "tool_name": "get_profile",
                        "arguments": {"user_id": "123"},
                    }
                )
            ),
            _text_response("done"),
            _text_response("final answer"),
        ]
    )
    registry = FakeRegistryWithSchema(
        {
            "manage_user_profile": {"user_id", "expected_profile_hash", "reason"},
            "get_profile": {"user_id"},
        }
    )
    catalog = FakeCatalog()
    messages = [{"role": "user", "content": "curate my profile"}]
    loop = _make_loop(llm, registry=registry, catalog=catalog)

    result = await loop.run(messages=messages, system_prompt="sys")

    assert result.response == "final answer"
    assert registry.calls == [{"tool_name": "get_profile", "arguments": {"user_id": "123"}}]
    assert messages[-1]["role"] == "tool"
    assert "get_profile" in messages[-1]["content"]


# ---------------------------------------------------------------------------
# Rejected tool switching when required args are satisfied
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_refine_cannot_switch_when_required_args_satisfied():
    llm = FakeLLM(
        [
            _tool_response(
                {
                    "id": "call_1",
                    "name": "manage_user_profile",
                    "arguments": {
                        "user_id": "123",
                        "expected_profile_hash": "deadbeef",
                        "reason": "dedup",
                    },
                }
            ),
            _text_response(
                json.dumps(
                    {
                        "action": "call_tool",
                        "tool_name": "get_profile",
                        "arguments": {"user_id": "123"},
                    }
                )
            ),
            _text_response("safe answer"),
        ]
    )
    registry = FakeRegistryWithSchema(
        {
            "manage_user_profile": {"user_id", "expected_profile_hash", "reason"},
            "get_profile": {"user_id"},
        }
    )
    messages = [{"role": "user", "content": "curate"}]
    loop = _make_loop(llm, registry=registry)

    result = await loop.run(messages=messages, system_prompt="sys")

    assert result.stopped_by == "error"
    assert result.response == "safe answer"
    assert registry.calls == []


@pytest.mark.asyncio
async def test_refine_cannot_switch_to_unknown_tool_even_with_missing_args():
    llm = FakeLLM(
        [
            _tool_response(
                {"id": "call_1", "name": "search_memory", "arguments": {"query": "x"}}
            ),
            _text_response(
                json.dumps(
                    {
                        "action": "call_tool",
                        "tool_name": "web_search",
                        "arguments": {"query": "switched"},
                    }
                )
            ),
            _text_response("safe answer"),
        ]
    )
    registry = FakeRegistry()
    messages = [{"role": "user", "content": "hello"}]
    loop = _make_loop(llm, registry=registry)

    result = await loop.run(messages=messages, system_prompt="sys")

    assert result.stopped_by == "error"
    assert result.response == "safe answer"
    assert registry.calls == []


# ---------------------------------------------------------------------------
# Timeout / error behavior
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tool_timeout_is_handled():
    """Act converts timeout into a string error result; loop continues to Resolve."""
    import asyncio

    class SlowRegistry(FakeRegistry):
        async def execute_tool(self, tool_name, arguments):
            await asyncio.sleep(1000)
            return "never"

    llm = FakeLLM(
        [
            _tool_response({"id": "c1", "name": "search_memory", "arguments": {"query": "x"}}),
            _text_response(json.dumps({"action": "call_tool", "tool_name": "search_memory", "arguments": {"query": "x"}})),
            _text_response("done"),
            _text_response("final answer"),
        ]
    )
    registry = SlowRegistry()
    messages = [{"role": "user", "content": "hello"}]
    loop = _make_loop(llm, registry=registry, max_iterations=2)
    loop.act = Act(registry, tool_timeout=0, llm_type="openai", logger=logging.getLogger(__name__))

    result = await loop.run(messages=messages, system_prompt="sys")

    assert result.tools_executed == 1
    assert "timeout" in messages[-1]["content"].lower()
    assert result.response == "final answer"


@pytest.mark.asyncio
async def test_max_iterations_stops_and_resolves():
    """On max_iterations, loop stops and Resolve returns a note about the limit."""
    llm = FakeLLM(
        [
            _tool_response({"id": "c1", "name": "search_memory", "arguments": {"query": "x"}}),
            _text_response(json.dumps({"action": "call_tool", "tool_name": "search_memory", "arguments": {"query": "x"}})),
            _text_response("final answer"),
        ]
    )
    registry = FakeRegistry()
    messages = [{"role": "user", "content": "hello"}]
    loop = _make_loop(llm, registry=registry, max_iterations=1)

    result = await loop.run(messages=messages, system_prompt="sys")

    assert result.stopped_by == "max_iterations"
    assert result.iterations == 1
    assert result.tools_executed == 1
    # Resolve context should mention the limit
    assert "giới hạn" in llm.calls[-1]["messages"][-1]["content"]


# ---------------------------------------------------------------------------
# Act does not call the LLM
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_act_does_not_call_llm():
    """During Act execution, fake LLM call count must stay unchanged and registry records exactly one execution."""
    llm = FakeLLM(
        [
            _tool_response({"id": "c1", "name": "search_memory", "arguments": {"query": "x"}}),
            _text_response(json.dumps({"action": "call_tool", "tool_name": "search_memory", "arguments": {"query": "x"}})),
            _text_response("done"),
            _text_response("final answer"),
        ]
    )
    registry = FakeRegistry()
    messages = [{"role": "user", "content": "hello"}]
    loop = _make_loop(llm, registry=registry)

    call_count_before = len(llm.calls)
    result = await loop.run(messages=messages, system_prompt="sys")
    call_count_after = len(llm.calls)

    # Act should add 0 LLM calls; total should be 4 (Decide, Refine, Decide, Resolve)
    assert call_count_after == 4
    assert call_count_before == 0
    assert registry.calls == [{"tool_name": "search_memory", "arguments": {"query": "x"}}]
    assert result.response == "final answer"


# ---------------------------------------------------------------------------
# Prompt-scope tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_prompt_scope_tool_catalog_included_for_decide_and_resolve():
    """Tool catalog is included for Decide and Resolve, excluded for Refine."""
    llm = FakeLLM(
        [
            _tool_response({"id": "c1", "name": "search_memory", "arguments": {"query": "x"}}),
            _text_response(json.dumps({"action": "call_tool", "tool_name": "search_memory", "arguments": {"query": "x"}})),
            _text_response("done"),
            _text_response("final answer"),
        ]
    )
    loop = _make_loop(llm)
    messages = [{"role": "user", "content": "hello"}]

    await loop.run(messages=messages, system_prompt="sys")

    assert llm.calls[0]["include_tool_catalog"] is True   # Decide
    assert llm.calls[1]["include_tool_catalog"] is False  # Refine
    assert llm.calls[2]["include_tool_catalog"] is True    # Decide (post-act)
    assert llm.calls[3]["include_tool_catalog"] is True    # Resolve


@pytest.mark.asyncio
async def test_prompt_scope_selected_tool_guide_only_for_refine():
    """The selected tool guide appears in the Refine system prompt only."""
    llm = FakeLLM(
        [
            _tool_response({"id": "c1", "name": "search_memory", "arguments": {"query": "x"}}),
            _text_response(json.dumps({"action": "call_tool", "tool_name": "search_memory", "arguments": {"query": "x"}})),
            _text_response("done"),
            _text_response("final answer"),
        ]
    )
    catalog = FakeCatalog()
    loop = _make_loop(llm, catalog=catalog)
    messages = [{"role": "user", "content": "hello"}]

    await loop.run(messages=messages, system_prompt="sys")

    # Refine system prompt contains the selected tool guide
    assert "=== HƯỚNG DẪN TOOL ĐÃ CHỌN ===" in llm.calls[1]["system_prompt"]
    assert "<tool_guide" in llm.calls[1]["system_prompt"]
    # Decide and Resolve do not contain the guide
    assert "=== HƯỚNG DẪN TOOL ĐÃ CHỌN ===" not in llm.calls[0]["system_prompt"]
    assert "=== HƯỚNG DẪN TOOL ĐÃ CHỌN ===" not in llm.calls[3]["system_prompt"]
