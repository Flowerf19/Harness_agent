import pytest

from twin.shared.llm.base_llm_service import BaseLLMService
from twin.shared.tools.registry import ToolExecutionError, build_tool_registry


class DummyLLM:
    pass


class DummyPersonaLLM(BaseLLMService):
    async def generate_response(
        self,
        messages,
        system_prompt=None,
        use_native_tools=False,
        max_tokens=None,
    ):
        return "ok"


def _registry_for(agent_name: str):
    return build_tool_registry(
        agent_name=agent_name,
        core_manager=None,
        memory_manager=None,
        llm_service=DummyLLM(),
        base_memory_path="memories",
    ).registry


def _schema_names(registry):
    return {
        schema["function"]["name"]
        for schema in registry.get_all_openai_schemas()
    }


def test_bootstrap_filters_tool_visibility_by_agent():
    march7 = _registry_for("march7")
    evernight = _registry_for("evernight")
    removed_consolidation_tool = "consolidate_" + "t2_memory"

    assert removed_consolidation_tool not in _schema_names(march7)
    assert removed_consolidation_tool not in _schema_names(evernight)
    assert "get_profile" in _schema_names(march7)
    assert "get_profile" in _schema_names(evernight)


@pytest.mark.asyncio
async def test_bootstrap_removes_consolidation_tool_execution():
    march7 = _registry_for("march7")

    with pytest.raises(ToolExecutionError) as exc:
        await march7.execute_tool("consolidate_" + "t2_memory", {})

    assert "not found" in str(exc.value)


@pytest.mark.asyncio
async def test_update_personality_reloads_llm_persona_cache(tmp_path):
    persona_dir = tmp_path / "persona"
    persona_dir.mkdir()
    (persona_dir / "IDENTITY.md").write_text("old identity", encoding="utf-8")
    (persona_dir / "SOUL.md").write_text("old soul", encoding="utf-8")

    llm = DummyPersonaLLM(persona_path=str(persona_dir))
    result = build_tool_registry(
        agent_name="march7",
        core_manager=None,
        memory_manager=None,
        llm_service=llm,
        base_memory_path=str(persona_dir),
    )

    await result.registry.execute_tool(
        "update_personality",
        {"instruction": "Nói ngắn gọn hơn trong mọi câu trả lời."},
    )

    assert llm.static_soul == "Nói ngắn gọn hơn trong mọi câu trả lời."
    assert "Nói ngắn gọn hơn" in llm._build_final_system_prompt("")
