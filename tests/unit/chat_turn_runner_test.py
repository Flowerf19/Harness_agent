"""Tests for ChatTurnRunner normalization, token accounting, and LLM failure sentinel mapping.

Covers ChatTurnResult fields, token extraction from LLMResponse, and the
mapping of hard-failure sentinels to the friendly fallback.
"""
from __future__ import annotations

import logging
from typing import Any

import pytest

from twin.shared.llm.llm_response import LLMResponse
from twin.shared.llm.base_llm_service import LLM_ERROR_RESPONSE, LLM_ERROR_RESPONSES
from twin.shared.agent.chat_turn import ChatTurnRunner, ChatTurnResult


class FakeLLM:
    """Records calls and returns a fixed response."""

    def __init__(self, response: Any = "echo"):
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def generate_response(
        self,
        messages,
        system_prompt=None,
        use_native_tools=False,
        include_tool_catalog=True,
        max_tokens=None,
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
        return self.response


class FakeCatalog:
    def render_catalog(self) -> str:
        return "catalog"

    def allowed_tool_names(self) -> set[str]:
        return {"t1"}

    def render_tool_guide(self, tool_name: str) -> str:
        return f"guide for {tool_name}"


class FakeRegistry:
    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]):
        return f"result for {tool_name}"


def _make_runner(llm: FakeLLM, registry: Any = None) -> ChatTurnRunner:
    runner = ChatTurnRunner(
        llm=llm,
        tool_registry=registry,
        use_native_tools=True,
        logger=logging.getLogger(__name__),
    )
    # Inject a fake catalog so AgentLoop can load tool guides
    llm.tool_prompt_catalog = FakeCatalog()
    return runner


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_chat_turn_result_normalizes_string_response():
    llm = FakeLLM(response="plain text")
    runner = _make_runner(llm)
    result = await runner.run(messages=[{"role": "user", "content": "hi"}], system_prompt="sys")

    assert isinstance(result, ChatTurnResult)
    assert result.content == "plain text"
    assert result.raw_response == "plain text"
    assert result.is_failure is False
    assert result.is_structured is False
    assert result.input_tokens == 0
    assert result.output_tokens == 0
    assert result.total_tokens == 0


@pytest.mark.asyncio
async def test_chat_turn_result_normalizes_llm_response_with_tokens():
    llm = FakeLLM(
        response=LLMResponse(
            content="structured answer",
            input_tokens=42,
            output_tokens=7,
            total_tokens=49,
            model="gpt-4",
            finish_reason="stop",
        )
    )
    runner = _make_runner(llm)
    result = await runner.run(messages=[{"role": "user", "content": "hi"}], system_prompt="sys")

    assert result.content == "structured answer"
    # ChatTurnRunner normalizes string responses from AgentLoop; token fields come
    # from the raw_response when it is an LLMResponse. The result is_structured flag
    # is derived from whether raw_response is an LLMResponse.
    assert result.is_structured is True
    assert result.input_tokens == 42
    assert result.output_tokens == 7
    assert result.total_tokens == 49
    assert result.is_failure is False


@pytest.mark.asyncio
async def test_chat_turn_result_reasoning_only_flag_preserved():
    llm = FakeLLM(
        response=LLMResponse(
            content="thinking...",
            reasoning_only=True,
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
        )
    )
    runner = _make_runner(llm)
    result = await runner.run(messages=[{"role": "user", "content": "hi"}], system_prompt="sys")

    assert result.content == "thinking..."
    assert result.reasoning_only is True
    assert result.is_structured is True


# ---------------------------------------------------------------------------
# LLM failure sentinel mapping
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_chat_turn_maps_llm_error_sentinel_to_failure():
    llm = FakeLLM(response=LLM_ERROR_RESPONSE)
    runner = _make_runner(llm)
    result = await runner.run(messages=[{"role": "user", "content": "hi"}], system_prompt="sys")

    assert result.content == LLM_ERROR_RESPONSE
    assert result.is_failure is True
    assert result.is_structured is False


@pytest.mark.asyncio
async def test_chat_turn_maps_llm_bad_format_to_failure():
    from twin.shared.llm.base_llm_service import LLM_ERROR_BAD_FORMAT

    llm = FakeLLM(response=LLM_ERROR_BAD_FORMAT)
    runner = _make_runner(llm)
    result = await runner.run(messages=[{"role": "user", "content": "hi"}], system_prompt="sys")

    assert result.content == LLM_ERROR_BAD_FORMAT
    assert result.is_failure is True


@pytest.mark.asyncio
async def test_chat_turn_failure_with_structured_response():
    """If the LLM returns an LLMResponse whose content is a sentinel, it is still a failure."""
    llm = FakeLLM(
        response=LLMResponse(
            content=LLM_ERROR_RESPONSE,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
        )
    )
    runner = _make_runner(llm)
    result = await runner.run(messages=[{"role": "user", "content": "hi"}], system_prompt="sys")

    assert result.is_failure is True
    assert result.is_structured is True
    assert result.content == LLM_ERROR_RESPONSE
