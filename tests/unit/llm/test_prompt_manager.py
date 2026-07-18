from datetime import datetime

import pytest

import twin.shared.llm.prompt_manager as prompt_manager_module
from twin.shared.llm.base_llm_service import BaseLLMService
from twin.shared.llm.prompt_manager import PromptManager


class DummyLLMService(BaseLLMService):
    async def generate_response(
        self,
        messages,
        system_prompt=None,
        use_native_tools=False,
        include_tool_catalog=True,
        max_tokens=None,
        tool_choice=None,
    ):
        return "ok"


def test_prompt_manager_renders_current_time():
    manager = PromptManager(current_time=datetime(2026, 7, 18, 14, 30, 45))

    prompt = manager.render("Thời gian hiện tại: {{current_time}}")

    assert prompt == "Thời gian hiện tại: 2026-07-18 14:30:45"


def test_prompt_manager_loads_and_reloads_persona_files(tmp_path):
    (tmp_path / "IDENTITY.md").write_text("identity v1", encoding="utf-8")
    (tmp_path / "SOUL.md").write_text("soul v1 {{current_time}}", encoding="utf-8")
    (tmp_path / "VOICE.md").write_text("voice v1", encoding="utf-8")
    manager = PromptManager(
        str(tmp_path),
        current_time=datetime(2026, 7, 18, 14, 30, 45),
    )

    assert manager.identity == "identity v1"
    assert manager.soul == "soul v1 {{current_time}}"
    assert manager.extras == ["## VOICE.md\nvoice v1"]

    (tmp_path / "SOUL.md").write_text("soul v2 {{current_time}}", encoding="utf-8")
    manager.reload()
    prompt = manager.build_system_prompt("dynamic memory")

    assert manager.soul == "soul v2 {{current_time}}"
    assert "soul v2 2026-07-18 14:30:45" in prompt
    assert "dynamic memory" in prompt
    assert prompt.endswith("Thời gian hiện tại: 2026-07-18 14:30:45")


def test_prompt_manager_omits_persona_runtime_for_utility_prompt(tmp_path):
    (tmp_path / "IDENTITY.md").write_text("identity", encoding="utf-8")
    (tmp_path / "SOUL.md").write_text("soul", encoding="utf-8")
    manager = PromptManager(
        str(tmp_path),
        current_time=datetime(2026, 7, 18, 14, 30, 45),
    )

    prompt = manager.build_system_prompt(
        "dynamic memory",
        tool_catalog="tool list",
        include_persona=False,
    )

    assert prompt == "=== CÔNG CỤ ===\ntool list\n\ndynamic memory"
    assert "Thời gian hiện tại" not in prompt


@pytest.mark.parametrize(
    "persona_path",
    ["twin/march7/personas", "twin/evernight/personas"],
)
def test_final_system_prompt_renders_persona_current_time(monkeypatch, persona_path):
    fixed_now = datetime(2026, 7, 18, 14, 30, 45)

    class FixedDateTime:
        @classmethod
        def now(cls):
            return fixed_now

    monkeypatch.setattr(prompt_manager_module, "datetime", FixedDateTime)
    llm = DummyLLMService(persona_path=persona_path)

    prompt = llm._build_final_system_prompt("")

    assert prompt.endswith("Thời gian hiện tại: 2026-07-18 14:30:45")
    assert "{{current_time}}" not in prompt


def test_prompt_manager_uses_fresh_time_for_each_render(tmp_path):
    times = iter(
        [
            datetime(2026, 7, 18, 14, 30, 45),
            datetime(2026, 7, 18, 14, 31, 10),
        ]
    )
    manager = PromptManager(str(tmp_path), now=lambda: next(times))

    first = manager.render("{{current_time}}")
    second = manager.render("{{current_time}}")

    assert first == "2026-07-18 14:30:45"
    assert second == "2026-07-18 14:31:10"
