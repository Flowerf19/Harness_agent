---
status: done
created: 2026-05-26
---

# Tools package consolidation — collapse OLD top-level into `registry/`

## Summary

`twin/shared/tools/` carries two parallel hierarchies. Finish the migration: move the real `BaseTool` / `ToolRegistry` / `ToolDiscovery` implementations into `registry/`, redirect every import, then delete the empty shells (top-level files + `implementations/system/` shims). MCP, approval, dm_client, exceptions, declarations, and `modules/` are already single-shape and stay put.

**Initial framing was inverted.** Verified by reading the files: `registry/{base,registry,discovery}.py` are 6-line re-exports; the real implementations (210 / 281 / 281 lines) still live at top-level `base_tool.py` / `tool_registry.py` / `tool_discovery.py`. The only thing genuinely born inside `registry/` is `bootstrap.py`. The `implementations/system/*.py` shims (7 files) re-export from `modules/*` — also pure re-exports. So the public surface diff between OLD and NEW is **zero** — every "NEW" path is a re-export of the corresponding OLD code. Safe to consolidate.

## Success criteria

- `pytest tests/unit -v` and `pytest tests/services/tools -v` green (baseline per `.agents/TESTING_GUIDE.md` is `66 passed` on `tests/unit` — should still hold + the existing `tool_bootstrap_test.py` cases).
- `python -m compileall twin gateway` clean.
- Zero imports of `twin.shared.tools.base_tool`, `…tool_registry`, `…tool_discovery`, `…implementations.system` anywhere in the repo.
- `twin/shared/tools/` directory shape:
  ```
  twin/shared/tools/
  ├── __init__.py                                  (facade, re-exports)
  ├── approval_context.py, approval_dm_client.py, approval_gate.py
  ├── dm_client.py, exceptions.py
  ├── mcp_client.py, mcp_protocol.py, mcp_transport.py
  ├── declarations/{__init__.py, system_tools.py}
  ├── registry/{__init__.py, base.py, registry.py, discovery.py, bootstrap.py}
  └── modules/{execution,memory,profile,web}/*
  ```

## Key changes

### Phase 1 — Move real code into `registry/`, leave temporary shim at top-level

Replace each pair:

| Source (real code today) | Destination | Action |
|---|---|---|
| `base_tool.py` (210 lines) | `registry/base.py` (currently a 6-line shim) | Move full content. Then rewrite `base_tool.py` as `from twin.shared.tools.registry.base import BaseTool, ToolExecutionError; __all__ = [...]`. |
| `tool_registry.py` (281 lines) | `registry/registry.py` (6-line shim) | Move full content. Update its internal import `from twin.shared.tools.base_tool import …` → `from twin.shared.tools.registry.base import …`. Rewrite `tool_registry.py` as a 1-line re-export shim. |
| `tool_discovery.py` (281 lines) | `registry/discovery.py` (6-line shim) | Move full content. Update internal imports `from twin.shared.tools.base_tool import BaseTool` → `from twin.shared.tools.registry.base import BaseTool` and `from twin.shared.tools.tool_registry import ToolRegistry` → `from twin.shared.tools.registry.registry import ToolRegistry`. Rewrite `tool_discovery.py` as a 1-line re-export shim. |

After Phase 1: all imports still resolve (top-level files now point to `registry/` instead of being the source themselves). Tests must stay green here.

### Phase 2 — Redirect every internal import to `registry.*`

| File | Line | OLD import | NEW import |
|---|---|---|---|
| `twin/shared/tools/__init__.py` | 10 | `from .base_tool import BaseTool, ToolExecutionError` | `from .registry.base import BaseTool, ToolExecutionError` |
| same | 11 | `from .tool_registry import ToolRegistry` | `from .registry.registry import ToolRegistry` |
| same | 24 | `from .tool_discovery import ToolDiscovery, discover_and_register_tools` | `from .registry.discovery import ToolDiscovery, discover_and_register_tools` |
| `twin/shared/tools/exceptions.py` | 8 | `from twin.shared.tools.base_tool import ToolExecutionError` | `from twin.shared.tools.registry.base import ToolExecutionError` |
| `twin/shared/tools/mcp_protocol.py` | 27 | `from twin.shared.tools.base_tool import BaseTool` (TYPE_CHECKING) | `from twin.shared.tools.registry.base import BaseTool` |
| `twin/shared/tools/registry/bootstrap.py` | 14 | `from twin.shared.tools.base_tool import BaseTool` | `from twin.shared.tools.registry.base import BaseTool` |
| same | 17 | `from twin.shared.tools.tool_registry import ToolRegistry` | `from twin.shared.tools.registry.registry import ToolRegistry` |
| `twin/shared/tools/modules/execution/code_interpreter_tool.py` | 24 | `from twin.shared.tools.base_tool import BaseTool, ToolExecutionError` | `from twin.shared.tools.registry.base import BaseTool, ToolExecutionError` |
| `twin/shared/tools/modules/execution/execute_host_bash_tool.py` | 16 | same | same target |
| `twin/shared/tools/modules/memory/search_memory_tool.py` | 6 | same | same target |
| `twin/shared/tools/modules/memory/consolidate_t2_memory_tool.py` | 18 | same | same target |
| `twin/shared/tools/modules/profile/update_profile_tool.py` | 11 | same | same target |
| `twin/shared/tools/modules/profile/update_personality_tool.py` | 20 | same | same target |
| `twin/shared/tools/modules/web/tavily_search_tool.py` | 17 | same | same target |

After Phase 2: no internal file imports from top-level OLD modules; only the top-level shims (and external callers) still do.

### Phase 3 — Redirect external callers

Prefer the package facade `from twin.shared.tools.registry import …` (already exported by `registry/__init__.py`) — single import line per caller.

| File | Line | OLD | NEW |
|---|---|---|---|
| `twin/march7/agent.py` | 12 | `from twin.shared.tools.tool_registry import ToolRegistry` | `from twin.shared.tools.registry import ToolRegistry` |
| `twin/evernight/agent.py` | 12 | same | same |
| `tests/unit/tool_bootstrap_test.py` | 3 | `from twin.shared.tools.base_tool import ToolExecutionError` | `from twin.shared.tools.registry import ToolExecutionError` |
| `tests/unit/t2_consolidation_tool_test.py` | 9 | `from twin.shared.tools.base_tool import ToolExecutionError` | `from twin.shared.tools.registry import ToolExecutionError` |
| same | 10 | `from twin.shared.tools.implementations.system.consolidate_t2_memory_tool import ConsolidateT2MemoryTool` | `from twin.shared.tools.modules.memory.consolidate_t2_memory_tool import ConsolidateT2MemoryTool` |
| same | 11 | `from twin.shared.tools.tool_registry import ToolRegistry` | `from twin.shared.tools.registry import ToolRegistry` |
| `tests/services/tools/code_interpreter_tool_test.py` | 17 | `from twin.shared.tools.implementations.system.code_interpreter_tool import CodeInterpreterTool` | `from twin.shared.tools.modules.execution.code_interpreter_tool import CodeInterpreterTool` |
| same | 19 | `from twin.shared.tools.base_tool import ToolExecutionError` | `from twin.shared.tools.registry import ToolExecutionError` |
| `tests/services/tools/tavily_search_tool_test.py` | 16 | `from twin.shared.tools.implementations.system.tavily_search_tool import TavilySearchTool` | `from twin.shared.tools.modules.web.tavily_search_tool import TavilySearchTool` |

### Phase 4 — Delete the orphaned shells

After Phase 3 nothing references these. Remove:

- `twin/shared/tools/base_tool.py`
- `twin/shared/tools/tool_registry.py`
- `twin/shared/tools/tool_discovery.py`
- `twin/shared/tools/implementations/system/__init__.py`
- `twin/shared/tools/implementations/system/search_memory_tool.py`
- `twin/shared/tools/implementations/system/update_profile_tool.py`
- `twin/shared/tools/implementations/system/update_personality_tool.py`
- `twin/shared/tools/implementations/system/tavily_search_tool.py`
- `twin/shared/tools/implementations/system/code_interpreter_tool.py`
- `twin/shared/tools/implementations/system/execute_host_bash_tool.py`
- `twin/shared/tools/implementations/system/consolidate_t2_memory_tool.py`
- `twin/shared/tools/implementations/system/` (now empty)

**Decision needed before this phase** — `twin/shared/tools/implementations/mcp/__init__.py` is an empty stub whose docstring describes a planned future package ("MCP proxy tool implementations that allow agents to call external MCP servers"). No real code, no importers. Two options:
- **(a)** Delete it along with `implementations/__init__.py` and the `implementations/` dir entirely — tidiest, recoverable via git history if MCP proxy work resumes.
- **(b)** Keep `implementations/mcp/` as documented placeholder — signals intent.

Recommend **(a)**, since the package facade `registry/` and `modules/` are now the structural answer; resurrecting from git is cheap if MCP proxy work starts.

## Test plan

Checkpoint after each phase. Stop if anything goes red — root-cause before continuing.

| Phase | Verify |
|---|---|
| After Phase 1 | `python -m compileall twin gateway` clean. `pytest tests/unit -q` ≥ 66 passed + `tool_bootstrap_test` cases. `pytest tests/services/tools -q`. |
| After Phase 2 | Same commands. Internal-only changes; should be no-op behaviorally. |
| After Phase 3 | Same commands. This is where the agent/test files actually re-route. |
| After Phase 4 | Same commands. Plus: `grep -rn -E "from twin\.shared\.tools\.(base_tool\|tool_registry\|tool_discovery\|implementations\.system)" twin gateway tests` returns nothing. |
| Final | `docker compose -f docker/docker-compose.yml up -d --build` smoke (optional — only if user wants runtime confidence beyond unit tests). |

Existing test files that exercise the relevant surface (no new tests needed):

- `tests/unit/tool_bootstrap_test.py` — covers `build_tool_registry`, agent-scoped visibility, ToolExecutionError on denied execution.
- `tests/unit/t2_consolidation_tool_test.py` — covers `ConsolidateT2MemoryTool` + `ToolRegistry` integration.
- `tests/services/tools/code_interpreter_tool_test.py`, `tests/services/tools/tavily_search_tool_test.py` — cover the two module-level tools whose import paths are most exposed.

## Risk callouts

1. **No public-surface diff between OLD and NEW** — verified by reading every wrapper. `BaseTool`, `ToolExecutionError`, `ToolRegistry`, `ToolDiscovery`, `discover_and_register_tools` keep identical signatures; only the import path changes.
2. **Phase 1 transient state is safe**: top-level files become 1-line shims temporarily, so any cross-import still resolves while phases 2–3 run.
3. **`implementations/mcp/` decision**: see Phase 4. Pick (a) or (b) before executing.
4. **No production-code path lives in the deletion set** — `SYSTEM_TOOL_SPECS` in `declarations/system_tools.py` already points at `twin.shared.tools.modules.*` strings used by `importlib.import_module` in `bootstrap.py`. Bootstrap doesn't depend on `implementations/system/*.py` files at all; they exist only for legacy test imports.
5. **No runtime behavior change**: this is a structural move. ToolRegistry / bootstrap / executor wiring is byte-for-byte identical.

## Assumptions

- Keep the package facade `from twin.shared.tools.registry import …` as the canonical external API for callers that want core types (bootstrap, ToolRegistry, BaseTool, etc.). Module-level tool classes (`SearchMemoryTool`, `CodeInterpreterTool`, …) keep their `twin.shared.tools.modules.<domain>.<tool>` import path — that is already what `declarations/system_tools.py` uses and what tests will be redirected to.
- `tests/services/tools/*_test.py` are still active tests (file path lives outside `tests/unit/`; TESTING_GUIDE doesn't list them but they're discoverable by pytest). If they're considered dead, the deletion of `implementations/system/*` becomes simpler — flag if so.
- `pytest tests/unit` baseline `66 passed` from TESTING_GUIDE will need a fresh number after this lands (count may shift if any test file got added/removed since 2026-05-25); update the doc accordingly.
- No drive-by edits to comments, docstrings, type hints, or formatting in moved files. Move bytes, fix imports, stop.
