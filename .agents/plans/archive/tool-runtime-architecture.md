---
status: done
created: 2026-06-19
last_updated: 2026-06-20
---

# Tool Runtime Architecture: Local + Remote MCP

## Summary

Standardize tool execution around two backend kinds without changing the
model-facing prompt contract:

- `local`: in-process tools and app-owned services, called directly through the
  existing `ToolRegistry` / `BaseTool` path.
- `remote_mcp`: external MCP servers outside this app's trust boundary, called
  through `MCPClient`.

The local `ToolPromptCatalog`, guide files, native schemas, visibility, and
approval behavior remain the source of truth for the LLM. Remote MCP metadata
must not be injected into the prompt. This preserves prompt caching as long as
catalog lines, tool order, schema descriptions, and guide text remain stable.

Current audit result:

- `web_search` / Tavily is now `remote_mcp` because it uses Tavily's real
  external MCP endpoint. The public tool contract stays local and maps to
  Tavily's `tavily_search` MCP tool at execution time.
- Keep all other current tools `local`: memory/profile/consolidation tools are
  internal stateful tools; `run_python_code` and `execute_host_bash` call
  app-owned infrastructure with existing safety behavior.

Success criteria:

- Current prompt catalog output and OpenAI/Gemini tool schemas are unchanged
  for existing tools.
- Existing local tools continue to execute through direct `BaseTool.execute()`.
- The codebase has an explicit, tested backend concept with default `local`.
- A `remote_mcp` adapter can be added without exposing raw remote MCP
  descriptions to the LLM.
- Tests prove no accidental prompt/cache-affecting prompt surface changes.

## Architecture

This plan keeps the architecture deliberately small:

```text
LLM
  |
  v
Local Tool Catalog + Lazy Guide
  - stable public tool names
  - stable micro descriptions
  - stable local schemas
  - stable guide text
  |
  v
ToolRegistry / Tool Gateway
  - visibility
  - allowed_to
  - parameter validation
  - approval
  - backend dispatch
  |
  +-- backend: local
  |     - direct BaseTool.execute()
  |     - in-process app tools
  |     - app-owned services such as CodeBox / Bash Executor
  |
  +-- backend: remote_mcp
        - external MCP server
        - MCPClient tools/call
        - remote metadata is untrusted
        - sampling disabled by default
```

The model sees logical tools, not backend plumbing:

```text
Model-facing logical tools:
  web_search
  search_memory
  get_profile
  update_user_profile
  manage_user_profile
  update_personality
  run_python_code
  execute_host_bash
  consolidate_memory

Runtime backend kinds:
  local
  remote_mcp
```

Current classification:

```text
web_search
  current backend: remote_mcp
  remote server: Tavily remote MCP
  remote tool: tavily_search
  legacy HTTP fallback: removed
  prompt contract: local web_search guide/schema; no raw tools/list metadata

search_memory
consolidate_memory
get_profile
update_user_profile
manage_user_profile
update_personality
  backend: local
  reason: internal memory/profile/persona state

run_python_code
execute_host_bash
  backend: local
  reason: app-owned infrastructure with existing safety controls
```

Prompt/cache boundary:

```text
Backend metadata must not affect:
  - ToolPromptCatalog.render_catalog()
  - lazy guide text
  - OpenAI/Gemini tool schema descriptions
  - tool ordering

Remote MCP discovery may inform runtime wiring,
but it must not be rendered into the model prompt.
```

Remote MCP wrapper rule:

```text
Local public contract:
  name = web_search
  schema = local schema
  description = local guide <tool_description>
  guide = local lazy guide

Remote execution contract:
  server = external MCP server
  method = tools/call
  name = remote_tool_name
  arguments = normalized local arguments
```

Non-goal architecture for this phase:

```text
No local MCP server process.
No MCP transport for local tools.
No workflow engine.
No generated tool runtime.
No automatic remote tools/list import into prompt.
No sampling support by default.
```

## Tasks

### GOAL-001: Record the backend boundary without runtime churn

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-001 | Rename docs/comments that describe `SYSTEM_TOOL_SPECS` as only "system tools" so they say "locally declared tools" or "declared tools"; do not rename runtime symbols in this task. | ✅ | 2026-06-19 |
| TASK-002 | Add `backend: Literal["local", "remote_mcp"] = "local"` metadata to `ToolSpec` in `twin/shared/tools/declarations/system_tools.py`. | ✅ | 2026-06-19 |
| TASK-003 | Historical baseline: leave every existing `SYSTEM_TOOL_SPECS` entry on default `local`; superseded for Tavily by TASK-019. | ✅ | 2026-06-19 |
| TASK-004 | Add a short architecture note in `.agents/PROJECT_CONTEXT.md` or a focused decision note explaining: local direct call, remote MCP for external servers, remote metadata untrusted, prompt catalog remains local source of truth. | ✅ | 2026-06-19 |

### GOAL-002: Preserve prompt caching and strict-loop behavior

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-005 | Add or update tests around `ToolPromptCatalog.render_catalog()` to assert existing catalog text/order is unchanged by backend metadata. | ✅ | 2026-06-19 |
| TASK-006 | Add or update tests around `DeclaredToolProxy.description` / `get_openai_schema()` to assert descriptions still come from local guide `<tool_description>`, not backend metadata. | ✅ | 2026-06-19 |
| TASK-007 | Verify `ToolRegistry.execute_tool()` behavior is unchanged for local tools: visibility, allowed agents, parameter validation, and exception wrapping still happen before execution. | ✅ | 2026-06-19 |

### GOAL-003: Prepare a remote MCP adapter for real external servers

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-008 | Extend `ToolSpec` with optional remote fields only as needed for an adapter: `remote_server`, `remote_tool_name`, and optional argument/result mapping hooks. Keep all optional and unused for current tools. | | |
| TASK-009 | Superseded: do not implement a generic `RemoteMCPToolProxy` yet; Tavily uses a specific adapter until a second remote MCP integration justifies the abstraction. | ✅ | 2026-06-20 |
| TASK-010 | If implementing the adapter, ensure it exposes the local tool name/schema/description and only uses remote MCP for `tools/call`; never render raw `tools/list` descriptions into catalog or native schemas. | ✅ | 2026-06-20 |
| TASK-011 | If implementing the adapter, disable sampling by default and do not advertise `sampling`/`sampling.tools` to untrusted external MCP servers. | ✅ | 2026-06-20 |
| TASK-012 | If implementing the adapter, normalize MCP content blocks into bounded text and mark remote results as untrusted data before returning them to the LLM loop. | ✅ | 2026-06-20 |

TASK-009 is superseded by a Tavily-specific adapter in `TavilySearchTool`.
Do not add a generic remote MCP proxy until a second remote MCP integration
needs the same abstraction.

### GOAL-004: Audit current tools against the boundary

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-013 | Historical baseline: document `web_search` as a future remote MCP candidate before the Tavily remote integration landed; superseded by TASK-019. | ✅ | 2026-06-19 |
| TASK-014 | Historical baseline: assert all declarations default to `backend == "local"` until an explicit remote MCP integration lands; superseded by TASK-019. | ✅ | 2026-06-19 |
| TASK-015 | Add a guard test that no declared tool with `backend == "remote_mcp"` can omit a local guide path. | ✅ | 2026-06-19 |
| TASK-019 | Convert the explicit Tavily declaration to `backend="remote_mcp"` and keep all other declarations `local`. | ✅ | 2026-06-20 |
| TASK-020 | Add bootstrap/config tests showing Tavily remote MCP wiring. | ✅ | 2026-06-20 |
| TASK-021 | Add Tavily adapter tests for `tavily_search` argument mapping, `topic=news` normalization, and result trimming back to the public local schema. | ✅ | 2026-06-20 |
| TASK-022 | Remove the legacy Tavily HTTP runtime path, `TAVILY_BACKEND` switch, and old Tavily HTTP client tests so `web_search` only executes through remote MCP. | ✅ | 2026-06-20 |

### GOAL-005: Keep future bot-created tools constrained

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-016 | Document the future rule: bot-created tools start as drafts and cannot become visible/allowed without validation and approval. No implementation required in this plan. | ✅ | 2026-06-19 |
| TASK-017 | Document that generated workflow tools, when implemented, should be `local` backend unless they proxy a real external MCP server. | ✅ | 2026-06-19 |
| TASK-018 | Document explicit non-goals for this phase: no local MCP server process, no generated tool runtime, no workflow engine, no automatic remote tool import, no sampling support by default. | ✅ | 2026-06-19 |

## Test Plan

- Run focused unit tests for tool prompt catalog and declarations:
  `pytest tests/unit/tool_prompt_catalog_test.py -v`
- Run focused tool tests after any registry/bootstrap changes:
  `pytest tests/unit/memory/tools_test.py tests/unit/manage_profile_tool_test.py -v`
- Run service-level tests for unchanged external wrappers if touched:
  `pytest tests/services/tools/tavily_search_tool_test.py tests/services/tools/code_interpreter_tool_test.py -v`
- If a remote MCP adapter is implemented, add dedicated tests using a fake
  `MCPClient`:
  - local description/schema are used
  - remote `tools/list` description is ignored
  - `tools/call` receives mapped arguments
  - MCP content blocks normalize to bounded text
  - sampling is not advertised

Acceptance checks:

- `ToolPromptCatalog.render_catalog()` output for current tools is unchanged.
- Existing tools still register and execute as before.
- Only `web_search` / Tavily is converted to `remote_mcp`; every other current
  declaration remains `local`.
- No raw external MCP metadata enters the system prompt, tool schema
  description, or lazy guide.

## Assumptions

- `remote_mcp` means an external MCP server outside this app's trust boundary.
- App-owned HTTP services such as CodeBox and Bash Executor remain `local`
  because they are internal infrastructure with existing safety controls.
- Tavily uses Tavily's external MCP server only. The legacy Tavily HTTP client
  and `TAVILY_BACKEND` switch are removed from the app runtime.
- Prompt caching depends on deterministic catalog text, tool schema
  descriptions, guide text, and tool ordering. Backend metadata must not affect
  those surfaces.
- This plan intentionally avoids a local MCP server process. Local tools only
  need an MCP-compatible shape (`name`, `inputSchema`, `arguments`, result),
  not MCP transport.
