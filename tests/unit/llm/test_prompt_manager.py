import pytest

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
        reasoning_effort=None,
        include_persona=True,
    ):
        return "ok"


def test_prompt_manager_loads_and_reloads_persona_files(tmp_path):
    (tmp_path / "IDENTITY.md").write_text("identity v1", encoding="utf-8")
    (tmp_path / "SOUL.md").write_text("soul v1", encoding="utf-8")
    (tmp_path / "VOICE.md").write_text("voice v1", encoding="utf-8")
    manager = PromptManager(str(tmp_path))

    assert manager.identity == "identity v1"
    assert manager.soul == "soul v1"
    assert manager.extras == ["## VOICE.md\nvoice v1"]

    (tmp_path / "SOUL.md").write_text("soul v2", encoding="utf-8")
    manager.reload()
    prompt = manager.build_system_prompt("dynamic memory")

    assert manager.soul == "soul v2"
    assert "soul v2" in prompt
    assert "dynamic memory" in prompt
    assert "Thời gian hiện tại" not in prompt


def test_prompt_manager_omits_persona_for_utility_prompt(tmp_path):
    (tmp_path / "IDENTITY.md").write_text("identity", encoding="utf-8")
    (tmp_path / "SOUL.md").write_text("soul", encoding="utf-8")
    manager = PromptManager(str(tmp_path))

    prompt = manager.build_system_prompt(
        "dynamic memory",
        tool_catalog="tool list",
        include_persona=False,
    )

    assert prompt == "=== CÔNG CỤ ===\ntool list\n\ndynamic memory"


@pytest.mark.parametrize(
    "persona_path",
    ["twin/march7/personas", "twin/evernight/personas"],
)
def test_final_system_prompt_contains_only_static_persona_context(persona_path):
    llm = DummyLLMService(persona_path=persona_path)

    prompt = llm._build_final_system_prompt("dynamic memory")

    assert "dynamic memory" in prompt
    assert "Thời gian hiện tại" not in prompt
