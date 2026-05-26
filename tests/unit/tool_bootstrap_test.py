import pytest

from twin.shared.tools.base_tool import ToolExecutionError
from twin.shared.tools.registry.bootstrap import build_tool_registry


class DummyLLM:
    pass


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

    assert "consolidate_t2_memory" not in _schema_names(march7)
    assert "consolidate_t2_memory" in _schema_names(evernight)


@pytest.mark.asyncio
async def test_bootstrap_blocks_disallowed_tool_execution():
    march7 = _registry_for("march7")

    with pytest.raises(ToolExecutionError) as exc:
        await march7.execute_tool("consolidate_t2_memory", {})

    assert "không có quyền" in str(exc.value)
