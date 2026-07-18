"""Focused tests for stage-owned runtime context and persona scope."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from twin.shared.agent.think import Think


class FakeLLM:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def generate_response(self, **kwargs):
        self.calls.append(kwargs)
        return "ok"


@pytest.mark.asyncio
async def test_decide_adds_runtime_to_copied_current_user_message():
    llm = FakeLLM()
    think = Think(llm, now=lambda: datetime(2026, 7, 18, 14, 30, 45))
    messages = [{"role": "user", "content": "thời tiết hôm nay"}]

    await think.run(
        stage="decide",
        messages=messages,
        system_prompt="static system prompt",
        use_native_tools=True,
        max_tokens=100,
    )

    call = llm.calls[0]
    assert messages == [{"role": "user", "content": "thời tiết hôm nay"}]
    assert call["messages"] == [{
        "role": "user",
        "content": "thời tiết hôm nay\n\nThời gian hiện tại: 2026-07-18 14:30:45",
    }]
    assert call["system_prompt"] == "static system prompt"
    assert call["include_persona"] is True
    assert call["include_tool_catalog"] is True


@pytest.mark.asyncio
async def test_refine_has_runtime_without_persona():
    llm = FakeLLM()
    think = Think(llm, now=lambda: datetime(2026, 7, 18, 14, 31, 10))
    messages = [
        {"role": "user", "content": "original request"},
        {"role": "user", "content": "Chỉ trả về JSON hợp lệ."},
    ]

    await think.run(
        stage="refine",
        messages=messages,
        system_prompt="tool guide and refine contract",
        use_native_tools=False,
        max_tokens=100,
    )

    call = llm.calls[0]
    assert call["messages"][-1]["content"].endswith(
        "Chỉ trả về JSON hợp lệ.\n\nThời gian hiện tại: 2026-07-18 14:31:10"
    )
    assert call["include_persona"] is False
    assert call["include_tool_catalog"] is False


@pytest.mark.asyncio
async def test_runtime_time_is_fresh_for_each_stage_call():
    times = iter(
        [
            datetime(2026, 7, 18, 14, 30, 45),
            datetime(2026, 7, 18, 14, 31, 10),
        ]
    )
    llm = FakeLLM()
    think = Think(llm, now=lambda: next(times))

    for stage in ("decide", "refine"):
        await think.run(
            stage=stage,
            messages=[{"role": "user", "content": "request"}],
            system_prompt="system",
            use_native_tools=stage == "decide",
            max_tokens=100,
        )

    assert llm.calls[0]["messages"][0]["content"].endswith("2026-07-18 14:30:45")
    assert llm.calls[1]["messages"][0]["content"].endswith("2026-07-18 14:31:10")
