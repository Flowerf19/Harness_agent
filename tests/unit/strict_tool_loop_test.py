import json
import logging

import pytest

from twin.shared.llm.llm_response import LLMResponse
from twin.shared.llm.tool_loop import SAFE_REFINE_FAILURE_REPLY, run_strict_tool_loop


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def generate_response(
        self,
        messages,
        system_prompt=None,
        use_native_tools=False,
        max_tokens=None,
    ):
        self.calls.append(
            {
                "messages": list(messages),
                "system_prompt": system_prompt,
                "use_native_tools": use_native_tools,
            }
        )
        return self.responses.pop(0)


class FakeCatalog:
    def __init__(self):
        self.loaded = []

    def render_tool_guide(self, tool_name):
        self.loaded.append(tool_name)
        return f'<tool_guide name="{tool_name}">\n{tool_name}: guide\n\n## {tool_name}\nUse carefully.\n</tool_guide>'


class FakeRegistry:
    def __init__(self):
        self.calls = []

    async def execute_tool(self, tool_name, arguments):
        self.calls.append({"tool_name": tool_name, "arguments": arguments})
        return f"result for {tool_name}: {arguments}"


def _tool_response(*tool_calls):
    return LLMResponse(content="", tool_calls=list(tool_calls))


def _text_response(text):
    return LLMResponse(content=text)


@pytest.mark.asyncio
async def test_no_tool_response_returns_after_one_llm_call():
    llm = FakeLLM([_text_response("plain answer")])
    registry = FakeRegistry()
    catalog = FakeCatalog()
    messages = [{"role": "user", "content": "hello"}]

    response = await run_strict_tool_loop(
        llm=llm,
        tool_registry=registry,
        tool_prompt_catalog=catalog,
        messages=messages,
        system_prompt="sys",
        use_native_tools=True,
        llm_type="openai",
        logger=logging.getLogger(__name__),
    )

    assert isinstance(response, LLMResponse)
    assert response.content == "plain answer"
    assert len(llm.calls) == 1
    assert llm.calls[0]["use_native_tools"] is True
    assert registry.calls == []
    assert catalog.loaded == []
    assert messages == [{"role": "user", "content": "hello"}]


@pytest.mark.asyncio
async def test_strict_loop_executes_only_first_tool_call_and_continues():
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
            _text_response("final answer"),
        ]
    )
    registry = FakeRegistry()
    catalog = FakeCatalog()
    messages = [{"role": "user", "content": "remember?"}]

    response = await run_strict_tool_loop(
        llm=llm,
        tool_registry=registry,
        tool_prompt_catalog=catalog,
        messages=messages,
        system_prompt="sys",
        use_native_tools=True,
        llm_type="openai",
        logger=logging.getLogger(__name__),
    )

    assert isinstance(response, LLMResponse)
    assert response.content == "final answer"
    assert catalog.loaded == ["search_memory"]
    assert registry.calls == [
        {"tool_name": "search_memory", "arguments": {"user_id": "123", "query": "refined"}}
    ]
    assert len(messages) == 3
    assert messages[1]["tool_calls"][0]["id"] == "call_1"
    assert messages[1]["tool_calls"][0]["function"]["name"] == "search_memory"
    assert "web_search" not in json.dumps(messages[1], ensure_ascii=False)
    assert messages[2]["role"] == "tool"
    assert messages[2]["tool_call_id"] == "call_1"
    assert llm.calls[0]["use_native_tools"] is True
    assert llm.calls[1]["use_native_tools"] is False
    assert "<tool_guide" in llm.calls[1]["system_prompt"]
    assert "=== HƯỚNG DẪN TOOL ĐÃ CHỌN ===" in llm.calls[1]["system_prompt"]
    assert llm.calls[2]["messages"] == messages


@pytest.mark.asyncio
async def test_refine_respond_skips_execution():
    llm = FakeLLM(
        [
            _tool_response({"id": "call_1", "name": "web_search", "arguments": {"query": "x"}}),
            _text_response(
                json.dumps(
                    {
                        "action": "respond",
                        "response": "Không cần search.",
                    }
                )
            ),
        ]
    )
    registry = FakeRegistry()
    messages = [{"role": "user", "content": "hello"}]

    response = await run_strict_tool_loop(
        llm=llm,
        tool_registry=registry,
        tool_prompt_catalog=FakeCatalog(),
        messages=messages,
        system_prompt="sys",
        use_native_tools=True,
        llm_type="openai",
        logger=logging.getLogger(__name__),
    )

    assert isinstance(response, LLMResponse)
    assert response.content == "Không cần search."
    assert registry.calls == []
    assert messages == [{"role": "user", "content": "hello"}]


@pytest.mark.asyncio
async def test_invalid_refine_json_skips_execution():
    llm = FakeLLM(
        [
            _tool_response({"id": "call_1", "name": "web_search", "arguments": {"query": "x"}}),
            _text_response("not json"),
        ]
    )
    registry = FakeRegistry()

    response = await run_strict_tool_loop(
        llm=llm,
        tool_registry=registry,
        tool_prompt_catalog=FakeCatalog(),
        messages=[{"role": "user", "content": "hello"}],
        system_prompt="sys",
        use_native_tools=True,
        llm_type="openai",
        logger=logging.getLogger(__name__),
    )

    assert isinstance(response, LLMResponse)
    assert response.content == SAFE_REFINE_FAILURE_REPLY
    assert registry.calls == []


@pytest.mark.asyncio
async def test_refine_cannot_switch_selected_tool():
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
        ]
    )
    registry = FakeRegistry()

    response = await run_strict_tool_loop(
        llm=llm,
        tool_registry=registry,
        tool_prompt_catalog=FakeCatalog(),
        messages=[{"role": "user", "content": "hello"}],
        system_prompt="sys",
        use_native_tools=True,
        llm_type="openai",
        logger=logging.getLogger(__name__),
    )

    assert isinstance(response, LLMResponse)
    assert response.content == SAFE_REFINE_FAILURE_REPLY
    assert registry.calls == []
