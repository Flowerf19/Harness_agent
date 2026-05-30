"""Verify March7 handle_chat routes T1 reads and writes by scope.

Covers the regression where user-scope T1 was loaded for channel turns and
bot replies were filed under the user scope regardless of channel.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from twin.march7.agent import March7Agent


class FakeMemoryManager:
    """Minimal MemoryManager double capturing the calls handle_chat makes."""

    def __init__(self):
        self.user_scope_msgs: Dict[str, List[Dict]] = {}
        self.channel_scope_msgs: Dict[str, List[Dict]] = {}
        self.get_context_calls: List[Dict] = []
        self.add_assistant_calls: List[Dict] = []
        self.add_user_calls: List[Dict] = []

    async def add_message(self, user_id: str, role: str, content: str) -> None:
        self.add_user_calls.append({"user_id": user_id, "role": role, "content": content})
        self.user_scope_msgs.setdefault(user_id, []).append({"role": role, "content": content})

    async def get_context(
        self,
        user_id: str,
        current_query: str,
        channel_id: str | None = None,
    ):
        self.get_context_calls.append({"user_id": user_id, "channel_id": channel_id})
        if channel_id:
            return "sys-prompt", list(self.channel_scope_msgs.get(channel_id, []))
        return "sys-prompt", list(self.user_scope_msgs.get(user_id, []))

    async def add_assistant_message(
        self,
        user_id: str,
        content: str,
        *,
        channel_id: str | None = None,
        guild_id: str | None = None,
        bot_id: str | None = None,
        bot_name: str | None = None,
    ) -> None:
        self.add_assistant_calls.append({
            "user_id": user_id,
            "content": content,
            "channel_id": channel_id,
            "guild_id": guild_id,
            "bot_id": bot_id,
            "bot_name": bot_name,
        })
        if channel_id:
            self.channel_scope_msgs.setdefault(channel_id, []).append(
                {"role": "assistant", "content": content, "author_name": bot_name or "March7"}
            )
        else:
            self.user_scope_msgs.setdefault(user_id, []).append(
                {"role": "assistant", "content": content}
            )


class FakeLLM:
    """Returns a fixed string and records the messages it received."""

    def __init__(self, response: str = "echo"):
        self.response = response
        self.last_messages: List[Dict] | None = None
        self.last_system_prompt: str | None = None

    def __class__name__(self):  # pragma: no cover — only for repr
        return "FakeLLM"

    async def generate_response(self, messages, system_prompt, use_native_tools):
        self.last_messages = list(messages)
        self.last_system_prompt = system_prompt
        return self.response


def _make_agent(memory: FakeMemoryManager, llm_response: str = "echo") -> March7Agent:
    llm = FakeLLM(response=llm_response)
    agent = March7Agent(
        memory_manager=memory,  # type: ignore[arg-type]
        llm_service=llm,        # type: ignore[arg-type]
        tool_registry=None,
        use_native_tools=False,
        redis_client=None,
    )
    # Stash the LLM so tests can inspect what messages it saw.
    agent._fake_llm = llm  # type: ignore[attr-defined]
    return agent


@pytest.mark.asyncio
async def test_handle_chat_in_channel_loads_channel_scope_only():
    memory = FakeMemoryManager()
    # Seed cross-scope contamination: DM history for the same user_id.
    memory.user_scope_msgs["u1"] = [
        {"role": "user", "content": "kiểm tra tool giúp: test run_python_code"},
        {"role": "assistant", "content": "Tổng kết test: ..."},
    ]
    memory.channel_scope_msgs["c1"] = [
        {"role": "user", "content": "Hoà: Năm 2070+10 bằng?"},
    ]

    agent = _make_agent(memory)
    response = await agent.handle_chat(
        user_id="u1",
        content="2080+10?",
        channel_id="c1",
        observe_input=False,
        bot_id="march7",
        bot_name="March7",
    )

    assert response == "echo"
    assert memory.get_context_calls == [{"user_id": "u1", "channel_id": "c1"}]
    seen = agent._fake_llm.last_messages  # type: ignore[attr-defined]
    assert seen == [{"role": "user", "content": "Hoà: Năm 2070+10 bằng?"}]
    # DM-only contamination must not appear in the LLM context for a channel turn.
    contents = [m.get("content", "") for m in seen]
    assert not any("kiểm tra tool" in c for c in contents)
    assert not any("Tổng kết test" in c for c in contents)


@pytest.mark.asyncio
async def test_handle_chat_in_channel_saves_assistant_reply_to_channel_scope():
    memory = FakeMemoryManager()
    agent = _make_agent(memory, llm_response="2090 nha")

    await agent.handle_chat(
        user_id="u1",
        content="2080+10?",
        channel_id="c1",
        observe_input=False,
        guild_id="g1",
        bot_id="b42",
        bot_name="Bé Bảy",
    )

    assert len(memory.add_assistant_calls) == 1
    call = memory.add_assistant_calls[0]
    assert call == {
        "user_id": "u1",
        "content": "2090 nha",
        "channel_id": "c1",
        "guild_id": "g1",
        "bot_id": "b42",
        "bot_name": "Bé Bảy",
    }
    # Reply landed in channel scope, NOT user scope.
    assert "u1" not in memory.user_scope_msgs
    assert memory.channel_scope_msgs["c1"][-1]["role"] == "assistant"
    assert memory.channel_scope_msgs["c1"][-1]["content"] == "2090 nha"


@pytest.mark.asyncio
async def test_handle_chat_in_dm_uses_user_scope():
    memory = FakeMemoryManager()
    memory.user_scope_msgs["u1"] = [{"role": "user", "content": "alo"}]

    agent = _make_agent(memory, llm_response="chào Hoà")

    response = await agent.handle_chat(
        user_id="u1",
        content="alo",
        channel_id=None,
        observe_input=True,
    )

    assert response == "chào Hoà"
    assert memory.get_context_calls == [{"user_id": "u1", "channel_id": None}]
    # observe_input=True → user message recorded into user scope.
    assert memory.add_user_calls[-1] == {"user_id": "u1", "role": "user", "content": "alo"}
    # Bot reply saved to user scope (channel_id=None).
    assert memory.add_assistant_calls[-1]["channel_id"] is None
    assert memory.user_scope_msgs["u1"][-1] == {"role": "assistant", "content": "chào Hoà"}


@pytest.mark.asyncio
async def test_handle_chat_silence_sentinel_stays_silent():
    """allow_silence + model emits [skip] → empty reply, nothing saved, note injected."""
    memory = FakeMemoryManager()
    agent = _make_agent(memory, llm_response="[skip]")

    response = await agent.handle_chat(
        user_id="u1",
        content="hôm nay trời đẹp",
        channel_id="c1",
        observe_input=False,
        bot_id="march7",
        bot_name="March7",
        allow_silence=True,
    )

    assert response == ""
    # Silent → no assistant reply persisted to any scope.
    assert memory.add_assistant_calls == []
    assert "c1" not in memory.channel_scope_msgs
    # The silence permission note must reach the LLM's system prompt.
    assert "[skip]" in agent._fake_llm.last_system_prompt  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_handle_chat_allow_silence_normal_reply_is_sent():
    """allow_silence but a real reply → sent and saved (sentinel only on exact [skip])."""
    memory = FakeMemoryManager()
    agent = _make_agent(memory, llm_response="ờ đẹp thật đó =))")

    response = await agent.handle_chat(
        user_id="u1",
        content="hôm nay trời đẹp",
        channel_id="c1",
        observe_input=False,
        bot_id="march7",
        bot_name="March7",
        allow_silence=True,
    )

    assert response == "ờ đẹp thật đó =))"
    assert len(memory.add_assistant_calls) == 1
    assert memory.channel_scope_msgs["c1"][-1]["content"] == "ờ đẹp thật đó =))"


@pytest.mark.asyncio
async def test_handle_chat_sentinel_ignored_when_silence_not_allowed():
    """Default allow_silence=False (e.g. direct mention) → [skip] is a literal reply."""
    memory = FakeMemoryManager()
    agent = _make_agent(memory, llm_response="[skip]")

    response = await agent.handle_chat(
        user_id="u1",
        content="@Bảy nói gì đi",
        channel_id="c1",
        observe_input=False,
        bot_id="march7",
        bot_name="March7",
    )

    assert response == "[skip]"
    assert len(memory.add_assistant_calls) == 1
    # No silence note when not permitted.
    assert "NGỮ CẢNH KÊNH" not in (agent._fake_llm.last_system_prompt or "")  # type: ignore[attr-defined]
