from pathlib import Path

import pytest

from twin.shared.llm.base_llm_service import BaseLLMService
from twin.shared.tools.registry.base import BaseTool
from twin.shared.tools.declarations.system_tools import ToolSpec
from twin.shared.tools.prompts.catalog import (
    ToolPromptCatalog,
    ToolPromptSpec,
    read_tool_description,
)
from twin.shared.tools.registry import build_tool_registry


class DummyTool(BaseTool):
    @property
    def name(self):
        return "dummy_tool"

    @property
    def description(self):
        return "Dummy."

    @property
    def parameters_schema(self):
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, **kwargs):
        return "ok"


class DummyLLMService(BaseLLMService):
    async def generate_response(
        self,
        messages,
        system_prompt=None,
        use_native_tools=False,
        max_tokens=None,
    ):
        return "ok"


def test_catalog_renders_only_micro_lines_from_guides():
    result = build_tool_registry(
        agent_name="march7",
        core_manager=None,
        memory_manager=None,
        llm_service=object(),
        base_memory_path="memories",
    )

    catalog = result.tool_prompt_catalog.render_catalog()
    search_description = result.tool_prompt_catalog.render_tool_description("search_memory")
    web_description = result.tool_prompt_catalog.render_tool_description("web_search")

    assert f"- search_memory: {search_description}" in catalog
    assert f"- web_search: {web_description}" in catalog
    assert "## search_memory" not in catalog
    assert "### Khi nên dùng" not in catalog


def test_render_tool_guide_wraps_full_selected_guide():
    result = build_tool_registry(
        agent_name="march7",
        core_manager=None,
        memory_manager=None,
        llm_service=object(),
        base_memory_path="memories",
    )

    guide = result.tool_prompt_catalog.render_tool_guide("web_search")
    web_description = result.tool_prompt_catalog.render_tool_description("web_search")

    assert guide.startswith('<tool_guide name="web_search">')
    assert web_description in guide
    assert "## web_search" in guide
    assert "<tool_description>" not in guide


def test_missing_description_block_fails_clearly(tmp_path: Path):
    guide = tmp_path / "bad.md"
    guide.write_text("## bad\nNo description block", encoding="utf-8")
    catalog = ToolPromptCatalog(
        [ToolPromptSpec(name="bad_tool", guide_path=guide)]
    )

    with pytest.raises(ValueError, match="missing <tool_description>"):
        catalog.render_catalog()


def test_native_schema_description_comes_from_tool_description_tag():
    result = build_tool_registry(
        agent_name="march7",
        core_manager=None,
        memory_manager=None,
        llm_service=object(),
        base_memory_path="memories",
    )

    schemas = result.registry.get_all_openai_schemas()
    descriptions = {
        schema["function"]["name"]: schema["function"]["description"]
        for schema in schemas
    }

    assert descriptions["web_search"] == read_tool_description(
        "web_search",
        "guides/web_search.md",
    )
    assert descriptions["search_memory"] == read_tool_description(
        "search_memory",
        "guides/search_memory.md",
    )


def test_visible_tool_without_guide_fails_clearly():
    with pytest.raises(ValueError, match="Missing guide_path for visible tool: dummy_tool"):
        ToolPromptCatalog.from_tools_and_specs(
            [DummyTool()],
            [
                ToolSpec(
                    module="tests.unit.tool_prompt_catalog_test",
                    class_name="DummyTool",
                )
            ],
            agent_name="march7",
        )


def test_final_system_prompt_uses_micro_catalog_not_persona_tool_md():
    llm = DummyLLMService(persona_path="twin/march7/personas")
    result = build_tool_registry(
        agent_name="march7",
        core_manager=None,
        memory_manager=None,
        llm_service=object(),
        base_memory_path="memories",
    )
    llm.set_tool_prompt_catalog(result.tool_prompt_catalog)

    prompt = llm._build_final_system_prompt("dynamic memory")
    search_description = result.tool_prompt_catalog.render_tool_description("search_memory")

    assert "=== CÔNG CỤ ===" in prompt
    assert f"- search_memory: {search_description}" in prompt
    assert "## search_memory" not in prompt
    assert "Quick routing" not in prompt
    assert "dynamic memory" in prompt
