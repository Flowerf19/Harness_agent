import pytest

from twin.shared.llm.base_llm_service import BaseLLMService
from twin.shared.system_gateway import HostGatewayClient
from twin.shared.tools.mcp_client import MCPClient
from twin.shared.tools.modules.profile.update_personality_tool import UpdatePersonalityTool
from twin.shared.tools.registry import ToolExecutionError, build_tool_registry
from twin.shared.tools.registry import bootstrap


class DummyLLM:
    pass


class DummyProfileStore:
    def __init__(self):
        self.calls = []

    async def replace_section(
        self,
        user_id,
        section,
        bullets,
        expected_profile_hash=None,
    ):
        self.calls.append((user_id, section, bullets, expected_profile_hash))
        if expected_profile_hash == "stale":
            return {
                "ok": False,
                "conflict": True,
                "profile_hash": "fresh",
                "written": False,
            }
        return {
            "ok": True,
            "conflict": False,
            "profile_hash": "hash2",
            "written": True,
            "old_count": 2,
            "new_count": len(bullets),
        }


class DummyPersonaLLM(BaseLLMService):
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


def _bootstrap_for(agent_name: str, profile_store=None):
    return build_tool_registry(
        agent_name=agent_name,
        core_manager=None,
        memory_manager=None,
        llm_service=DummyLLM(),
        base_memory_path="memories",
        profile_store=profile_store,
    )


def _registry_for(agent_name: str, profile_store=None):
    return _bootstrap_for(agent_name, profile_store=profile_store).registry


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
    assert "host_system" in _schema_names(march7)
    assert "host_system" in _schema_names(evernight)
    assert "execute_host_bash" not in _schema_names(march7)
    assert "execute_host_bash" not in _schema_names(evernight)
    assert "manage_user_profile" not in _schema_names(march7)
    assert "manage_user_profile" in _schema_names(evernight)


def test_bootstrap_uses_tavily_remote_mcp_backend_by_default(monkeypatch):
    monkeypatch.setattr(bootstrap.Config, "TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(bootstrap.Config, "TAVILY_MCP_URL", "https://mcp.tavily.com/mcp")

    result = _bootstrap_for("march7")

    assert isinstance(result.tavily_mcp_client, MCPClient)
    assert result.tavily_mcp_client.transport.server_url == "https://mcp.tavily.com/mcp"
    assert result.tavily_mcp_client.transport.extra_headers == {
        "Authorization": "Bearer test-key"
    }


def test_bootstrap_initializes_system_gateway_client(monkeypatch):
    monkeypatch.setattr(bootstrap.Config, "SYSTEM_GATEWAY_URL", "http://system-gateway.local")
    monkeypatch.setattr(bootstrap.Config, "SYSTEM_GATEWAY_TIMEOUT", 12)

    result = _bootstrap_for("march7")

    assert isinstance(result.host_gateway_client, HostGatewayClient)
    assert result.host_gateway_client.base_url == "http://system-gateway.local"
    assert result.host_gateway_client.timeout == 12


@pytest.mark.asyncio
async def test_bootstrap_removes_consolidation_tool_execution():
    march7 = _registry_for("march7")

    with pytest.raises(ToolExecutionError) as exc:
        await march7.execute_tool("consolidate_" + "t2_memory", {})

    assert "not found" in str(exc.value)


@pytest.mark.asyncio
async def test_execute_host_bash_is_legacy_denied_for_agents():
    march7 = _registry_for("march7")

    with pytest.raises(ToolExecutionError) as exc:
        await march7.execute_tool("execute_host_bash", {"command": "pwd"})

    assert "không có quyền" in str(exc.value)


@pytest.mark.asyncio
async def test_manage_user_profile_denied_for_march7_even_if_called_directly():
    march7 = _registry_for("march7", profile_store=DummyProfileStore())

    with pytest.raises(ToolExecutionError) as exc:
        await march7.execute_tool(
            "manage_user_profile",
            {
                "user_id": "123",
                "section": "basic",
                "bullets": ["Tên: Quang"],
                "expected_profile_hash": "hash1",
                "reason": "cleanup duplicate",
            },
        )

    assert "không có quyền" in str(exc.value)


@pytest.mark.asyncio
async def test_manage_user_profile_executes_for_evernight():
    store = DummyProfileStore()
    evernight = _registry_for("evernight", profile_store=store)

    result = await evernight.execute_tool(
        "manage_user_profile",
        {
            "user_id": "123",
            "section": "basic",
            "bullets": ["Tên: Quang"],
            "expected_profile_hash": "hash1",
            "reason": "merge duplicate",
        },
    )

    assert "Đã thay section basic" in result
    assert "Hash mới: hash2" in result
    assert store.calls == [("123", "basic", ["Tên: Quang"], "hash1")]


@pytest.mark.asyncio
async def test_manage_user_profile_reports_hash_conflict_for_evernight():
    evernight = _registry_for("evernight", profile_store=DummyProfileStore())

    result = await evernight.execute_tool(
        "manage_user_profile",
        {
            "user_id": "123",
            "section": "basic",
            "bullets": ["Tên: Quang"],
            "expected_profile_hash": "stale",
            "reason": "resolve conflict",
        },
    )

    assert "Conflict" in result
    assert "fresh" in result


@pytest.mark.asyncio
async def test_update_personality_reloads_llm_persona_cache(tmp_path):
    persona_dir = tmp_path / "persona"
    persona_dir.mkdir()
    (persona_dir / "IDENTITY.md").write_text("old identity", encoding="utf-8")
    (persona_dir / "SOUL.md").write_text("old soul", encoding="utf-8")
    (persona_dir / "VOICE.md").write_text("old voice", encoding="utf-8")

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
        {
            "target_file": "SOUL.md",
            "instruction": "Nói ngắn gọn hơn trong mọi câu trả lời.",
        },
    )

    assert llm.static_soul == "Nói ngắn gọn hơn trong mọi câu trả lời."
    assert "Nói ngắn gọn hơn" in llm._build_final_system_prompt("")
    assert "old voice" in llm._build_final_system_prompt("")

    await result.registry.execute_tool(
        "update_personality",
        {
            "target_file": "VOICE.md",
            "instruction": "# VOICE.md\n\nNét giọng riêng mới.",
        },
    )

    assert (persona_dir / "VOICE.md").read_text(encoding="utf-8") == "# VOICE.md\n\nNét giọng riêng mới.\n"
    assert "Nét giọng riêng mới." in llm._build_final_system_prompt("")


@pytest.mark.asyncio
async def test_update_personality_requires_target_file(tmp_path):
    persona_dir = tmp_path / "persona"
    persona_dir.mkdir()
    tool = UpdatePersonalityTool(base_memory_path=str(persona_dir))

    result = await tool.execute("Nói ngắn hơn.")

    assert result == "Lỗi: Thiếu target_file."


@pytest.mark.asyncio
async def test_update_personality_rejects_target_paths(tmp_path):
    persona_dir = tmp_path / "persona"
    persona_dir.mkdir()
    tool = UpdatePersonalityTool(base_memory_path=str(persona_dir))

    result = await tool.execute("bad", target_file="../SOUL.md")

    assert result.startswith("Lỗi:")
    assert not (tmp_path / "SOUL.md").exists()
