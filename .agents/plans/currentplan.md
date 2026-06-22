---
status: completed
created: 2026-06-22
last_updated: 2026-06-22
---

# Think Agent Loop

## Summary

Refactor the current shared chat/tool orchestration from a monolithic
`run_strict_tool_loop` into an explicit agent loop:

```text
Think(Decide) -> Think(Refine) -> Act -> Think(Decide) -> ... -> Think(Resolve)
```

Key architectural decisions:

- `Think` is the only LLM-facing abstraction.
- `Act` never calls the LLM and never receives persona prompts.
- `Decide`, `Refine`, and `Resolve` all keep the existing bot identity/soul
  behavior by continuing through `BaseLLMService.generate_response`.
- Do not add `behavior.md`, `reply.md`, or per-stage persona files in this task.
- User-visible output must come from `Think(Resolve)`, not directly from tool
  selection/refine.
- Tool prompt loading stays lazy: short catalog/schema for `Decide`, full guide
  only for `Refine`, implementation object only for `Act`.
- Existing logic is reusable; do not rewrite from scratch. Expected reuse is
  roughly 65-75%: provider calls, tool registry execution, lazy tool guide
  rendering, refine parsing, prerequisite routing, message formatting,
  timeout/error handling, and tests.

## Implementation Status

All planned tasks are complete. The branch `feat/agent-action-loop` contains the
new `twin/shared/agent/` modules and the wiring changes.

## Tasks

### GOAL-001: Lock The Agent-Loop Contract

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-001 | Add a small contract module under `twin/shared/agent/` for stage names and result types. Use `ThinkStage` values `decide`, `refine`, `resolve`; do not include `act` in `ThinkStage` because `Act` is not an LLM phase. | ✅ | 2026-06-22 |
| TASK-002 | Define `AgentLoopResult` with at least `response`, `messages`, `tools_executed`, `iterations`, and `stopped_by`. Keep this compatible with the useful parts of current `ToolLoopResult`. | ✅ | 2026-06-22 |
| TASK-003 | Define/refactor `RefineDecision` and tool-call message/result helpers in the agent layer, not as orchestration hidden inside `twin/shared/llm/tool_loop.py`. | ✅ | 2026-06-22 |
| TASK-004 | Document the invariant in code comments or docstrings: every user-visible answer goes through `Think(Resolve)`; `Decide` and `Refine` may produce candidates or cancellation reasons but do not directly become chat output. | ✅ | 2026-06-22 |

### GOAL-002: Make `Think` The Single LLM Stage Wrapper

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-005 | Add `class Think` under `twin/shared/agent/` with one `run(...)` method that accepts `stage`, `messages`, `system_prompt`, `use_native_tools`, `max_tokens`, and trace metadata. | ✅ | 2026-06-22 |
| TASK-006 | `Think.run` must call `llm.generate_response` through `call_with_langsmith_extra` and dynamic `langsmith_extra(name=f"think.{stage}")`. Do not decorate `Think.run` as an LLM span; provider `generate_response` is already the LLM span. | ✅ | 2026-06-22 |
| TASK-007 | Preserve current persona behavior: do not manually load or append `IDENTITY.md` / `SOUL.md` in `Think`. All Think stages go through the existing LLM service prompt builder so the bot keeps its identity/soul. | ✅ | 2026-06-22 |
| TASK-008 | Add thin inline stage contracts only where needed. These are not new persona files. `Decide` decides next action/tool, `Refine` returns strict JSON for one selected tool, `Resolve` synthesizes the final user-facing answer with tools disabled. | ✅ | 2026-06-22 |

### GOAL-003: Scope Tool Catalog And Tool Guide By Stage

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-009 | Add a backward-compatible prompt-scope option to `BaseLLMService.generate_response`, likely `include_tool_catalog: bool = True`, and thread it through OpenAI/Gemini services and test fakes. | ✅ | 2026-06-22 |
| TASK-010 | Update `BaseLLMService._build_final_system_prompt(...)` to include the tool catalog only when `include_tool_catalog=True`. Keep `IDENTITY.md`, `SOUL.md`, and memory/system prompt behavior unchanged. | ✅ | 2026-06-22 |
| TASK-011 | Call `Think(Decide)` with `include_tool_catalog=True` and `use_native_tools=True`. This is the only stage that receives native tool schemas. | ✅ | 2026-06-22 |
| TASK-012 | Call `Think(Refine)` with `include_tool_catalog=False`, `use_native_tools=False`, and exactly the selected tool's full guide in the stage system prompt. | ✅ | 2026-06-22 |
| TASK-013 | Call `Think(Resolve)` with `include_tool_catalog=False` and `use_native_tools=False`. Resolve should see conversation context and observations, not the full tool catalog. | ✅ | 2026-06-22 |

### GOAL-004: Extract `Act` As Pure Tool Execution

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-014 | Add `class ToolAct` or `class Act` under `twin/shared/agent/` that receives `tool_registry`, `tool_timeout`, `llm_type`, and logger. | ✅ | 2026-06-22 |
| TASK-015 | `Act.run(tool_name, arguments, tool_call_id, ...)` must validate/execute via `tool_registry.execute_tool(...)` only. It must not call `llm.generate_response`, load prompts, or inspect persona files. | ✅ | 2026-06-22 |
| TASK-016 | Preserve current execution behavior: timeout handling, `BashExecutorUnavailableError` propagation when requested, generic tool error conversion, and trace metadata for tool execution. | ✅ | 2026-06-22 |
| TASK-017 | Preserve provider-specific observation formatting: OpenAI uses assistant `tool_calls` + `tool` result messages; Gemini uses `functionCall` / `functionResponse` parts. | ✅ | 2026-06-22 |

### GOAL-005: Replace The Monolithic Tool Loop With `AgentLoop`

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-018 | Add `class AgentLoop` or `class ThinkLoop` under `twin/shared/agent/`. It owns orchestration only; it should not own memory persistence, gateway routing, silence policy, or persona loading. | ✅ | 2026-06-22 |
| TASK-019 | Implement the loop: call `Think(Decide)`; if it returns a tool call, select only the first tool and defer the rest as today; if no tool call, break to `Think(Resolve)` instead of returning the decide text directly. | ✅ | 2026-06-22 |
| TASK-020 | When a tool is selected, load only that tool guide from `ToolPromptCatalog`, calculate missing required args with existing logic, then call `Think(Refine)`. | ✅ | 2026-06-22 |
| TASK-021 | Preserve prerequisite routing: if selected tool lacks required args, `Refine` may route to an allowed prerequisite tool; otherwise switching tools remains rejected. | ✅ | 2026-06-22 |
| TASK-022 | If `Refine` returns `call_tool`, call `Act`, append the formatted tool call/result messages, increment `tools_executed`, and continue the loop with another `Think(Decide)` so the agent can decide whether more tools are needed. | ✅ | 2026-06-22 |
| TASK-023 | If `Refine` returns `respond` or cancellation, do not return that text directly. Pass the cancellation/reason into `Resolve` as stage context and let `Think(Resolve)` produce the user-facing answer. | ✅ | 2026-06-22 |
| TASK-024 | On `max_iterations`, stop tool use and call `Think(Resolve)` with a clear internal note that the loop limit was reached. Do not expose raw JSON/tool internals unless the user explicitly asked. | ✅ | 2026-06-22 |
| TASK-025 | Keep hard LLM provider failure sentinels (`LLM_ERROR_RESPONSES`) as failures. `ChatTurnRunner` should still convert them into the existing friendly agent-level fallback. | ✅ | 2026-06-22 |

### GOAL-006: Wire `ChatTurnRunner` To The New Loop

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-026 | Replace `ChatTurnRunner.run(...)`'s call to `run_strict_tool_loop(...)` with the new `AgentLoop.run(...)`. Keep `ChatTurnResult` normalization and token accounting behavior. | ✅ | 2026-06-22 |
| TASK-027 | Add the thin `Resolve` stage contract owned by `Think`/`AgentLoop` that synthesizes the final user-facing answer. There is no `_build_final_answer_system_prompt` to remove (it does not exist). Do not create a new markdown prompt file. | ✅ | 2026-06-22 |
| TASK-028 | Collapse the two nested chain spans (`chat_turn.run` → `tool_loop.run`) into one outer chain span for the agent loop, with provider LLM spans named `think.decide`, `think.refine`, and `think.resolve`. There is no `final_answer.generate` LLM wrapper span to remove. | ✅ | 2026-06-22 |
| TASK-029 | Decide whether `twin/shared/llm/tool_loop.py` becomes deleted code, helper-only code, or a temporary compatibility shim. The final active orchestration must live in `twin/shared/agent/`, not `twin/shared/llm/`. | ✅ | 2026-06-22 |

### GOAL-007: Update Tests Around The New Contract

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-030 | Port useful assertions from `tests/unit/strict_tool_loop_test.py` to new agent-loop tests: no-tool path, first-tool-only behavior, refine JSON validation, prerequisite routing, rejected tool switching, timeout/error behavior. | ✅ | 2026-06-22 |
| TASK-031 | Add a test proving `Act` does not call the LLM: fake LLM call count must not change during tool execution, while fake registry records exactly one execution. | ✅ | 2026-06-22 |
| TASK-032 | Add a test proving user-visible output comes from `Resolve`: no-tool path should call `Decide` with `use_native_tools=True`, then `Resolve` with `use_native_tools=False`; returned content must be the resolve response, not the decide draft. | ✅ | 2026-06-22 |
| TASK-033 | Add a test proving one-tool path order: `Decide(native tools on)` -> `Refine(native tools off)` -> `Act` -> `Decide(native tools on)` -> `Resolve(native tools off)` when the second decide says no more tools. | ✅ | 2026-06-22 |
| TASK-034 | Add prompt-scope tests: tool catalog included for `Decide`, excluded for `Refine`/`Resolve`; selected tool guide included only for `Refine`. | ✅ | 2026-06-22 |
| TASK-035 | Keep/update March7/Evernight chat-scope tests to ensure agent-level behavior still persists replies, honors `[skip]`, and maps LLM failure sentinels to friendly fallback text. | ✅ | 2026-06-22 |

### GOAL-008: Documentation And Cleanup

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-036 | Update `.agents/PROJECT_CONTEXT.md` or `.agents/AGENT_RULES.md` with the new Think/Act loop only after implementation lands. Mention `Act` has no LLM/persona and all user-visible output goes through `Resolve`. | ✅ | 2026-06-22 |
| TASK-037 | Remove obsolete tests/imports that still assert `run_strict_tool_loop` is the primary orchestration path, unless a deliberate compatibility shim remains. | ✅ | 2026-06-22 |
| TASK-038 | Keep `twin/shared/observability/langsmith.py` in this task. Do not remove the wrapper while changing the agent loop; tracing cleanup can be a separate task after span shape is verified. | ✅ | 2026-06-22 |

## Additional Fixes Discovered During Verification

- `twin/march7/container.py` was missing `embedding_service` and
  `timeline_summary_store` when calling `build_tool_registry`. This caused
  `search_memory` to report `"timeline_summary_store chưa được cấu hình"` in
  Discord. Fixed by passing both dependencies, matching `EvernightContainer`.
  Containers were restarted; full unit suite still passes.

## Verification

Unit tests:

```bash
conda run -n discord_bot python -m pytest tests/unit -q
```

Result: **201 passed**.

Docker:

- `march7` and `evernight` containers restarted successfully after the changes.
- No runtime errors beyond the existing unclosed `aiohttp` client-session warnings
  on shutdown.

## Test Plan (Completed)

Run focused tests first:

```bash
conda run -n discord_bot python -m pytest tests/unit/agent_loop_test.py tests/unit/chat_turn_runner_test.py -q
```

Then run agent behavior tests:

```bash
conda run -n discord_bot python -m pytest tests/unit/march7_handle_chat_scope_test.py tests/unit/evernight_agent_test.py -q
```

Then run relevant tool/runtime tests:

```bash
conda run -n discord_bot python -m pytest tests/unit/tool_bootstrap_test.py tests/unit/tool_prompt_catalog_test.py -q
```

Finish with:

```bash
conda run -n discord_bot python -m pytest tests/unit -q
```

Manual trace acceptance when LangSmith is enabled:

- One chain span for `chat_turn.run` / agent loop.
- LLM spans named `think.decide`, `think.refine`, `think.resolve`.
- Tool execution span under the loop.
- No duplicate nested `final_answer.generate` LLM wrapper span.

## Assumptions

- The current unified `IDENTITY.md` + `SOUL.md` loading is intentionally kept
  for all Think phases to preserve the bot's soul/persona.
- `behavior.md` / `reply.md` are out of scope. They risk duplicating `SOUL.md`.
- No-tool conversations will usually cost two LLM calls after this refactor:
  `Decide` then `Resolve`. One-tool conversations normally cost four LLM calls:
  `Decide`, `Refine`, post-observation `Decide`, then `Resolve`. This matches
  the architectural requirement that the tool-selection call does not directly
  become user-facing output.
- Future optimization may skip `Resolve` on simple no-tool turns, but that is
  intentionally not part of this plan because it weakens the clean stage
  boundary.
- Gateway, memory persistence, A2A boundaries, and Discord adapter behavior are
  not refactored here.
