---
status: done
created: 2026-06-30
last_updated: 2026-06-30
---

# Summary

Replace the current `decide -> refine -> act -> decide -> resolve` hot path with a cleaner `decide -> refine -> act -> decide` loop where `decide` can answer directly and `resolve` is removed.

New meaning:

- `decide` is the primary assistant turn. It decides the next action: answer the user directly, or call one tool.
- `refine` is the selected-tool argument repair/safety pass and remains mandatory for tool turns in this phase.
- `resolve` is removed from the normal architecture and deleted from the stage contract.

Success criteria:

- No-tool turns use 1 LLM call: `Think(decide)` returns final text.
- One valid tool turn uses 3 LLM calls: `Think(decide) -> Think(refine) -> Act -> Think(decide)`.
- One tool needing missing-arg repair uses the same call shape; `refine` stays mandatory and still receives the selected tool's full guide for every tool turn.
- User-visible answers may come from `Think(decide)`; old invariant "all answers go through resolve" is removed.
- Refine cancellation/error and max-iteration exits ask one final `Think(decide)` pass with native tools disabled; they do not return `Think(refine)` JSON/text directly.
- `Think(resolve)`, `_build_resolve_context`, and resolve prompt catalog scope are gone.

# Tasks

### GOAL-001: Update the agent loop contract

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-001 | In `twin/shared/agent/contract.py`, change `ThinkStage` from `Literal["decide", "refine", "resolve"]` to `Literal["decide", "refine"]`. | ✅ | 2026-06-30 |
| TASK-002 | Update `AgentLoopResult` docstrings/comments so `response` is from the stopping stage, not `Think(resolve)`. | ✅ | 2026-06-30 |
| TASK-003 | Update module docstrings in `contract.py`, `think.py`, and `agent_loop.py` to describe `Think(decide) -> Think(refine) -> Act -> Think(decide)`. | ✅ | 2026-06-30 |
| TASK-004 | Remove or rewrite comments that state "every user-visible answer goes through resolve". | ✅ | 2026-06-30 |

### GOAL-002: Make `Decide` the final-answer path

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-005 | In `AgentLoop.run`, when `decide_response` is a plain string and not an LLM failure sentinel, return it as the final `AgentLoopResult` with `stopped_by="answer"`. | ✅ | 2026-06-30 |
| TASK-006 | In `AgentLoop.run`, when `decide_response` is an `LLMResponse` without tool calls, return `decide_response.content` as the final answer with `stopped_by="answer"`. | ✅ | 2026-06-30 |
| TASK-007 | Preserve current LLM failure sentinel handling for both string and `LLMResponse.content`. | ✅ | 2026-06-30 |
| TASK-008 | Preserve existing "only execute first tool call, defer the rest" behavior unless a later task intentionally expands multi-tool-per-turn execution. | ✅ | 2026-06-30 |

### GOAL-003: Keep `Refine` mandatory for tool turns

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-009 | Keep the missing-required-args gate deterministic in `agent_loop.py`, but do not skip `refine` for valid selected tool calls in this phase. Missing required args only controls whether prerequisite tool switching is allowed. | ✅ | 2026-06-30 |
| TASK-010 | For selected tool calls, always run the existing `render_tool_guide -> build_refine_system_prompt -> parse_refine_decision` path, append the refined selected tool call when `refine` says `call_tool`, run `Act`, append result, and continue to the next `Think(decide)`. | ✅ | 2026-06-30 |
| TASK-011 | For missing required args, keep the existing `render_tool_guide -> build_refine_system_prompt -> parse_refine_decision` path, including prerequisite tool switching. | ✅ | 2026-06-30 |
| TASK-012 | If `refine.action == "respond"`, route the cancellation reason into one final `Think(decide)` pass with native tools disabled, instead of appending an internal note and calling resolve. | ✅ | 2026-06-30 |
| TASK-013 | If refine JSON is invalid or a switch is rejected, route a safe context note into one final `Think(decide)` pass with native tools disabled instead of falling through to resolve. | ✅ | 2026-06-30 |
| TASK-014 | Keep `format_tool_call_message(...)` and `Act.run(...)` behavior unchanged so provider-specific tool-result pairing remains intact. | ✅ | 2026-06-30 |

### GOAL-004: Remove resolve from execution and prompt scope

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-015 | Delete the final `Think(resolve)` block from `AgentLoop.run`. Max-iteration handling should return a concise safe final response from `Decide` loop state, not call another LLM. | ✅ | 2026-06-30 |
| TASK-016 | Delete `_build_resolve_context` and any tests that only exist for resolve-context injection. | ✅ | 2026-06-30 |
| TASK-017 | In `Think.run`, change prompt catalog scoping to `include_tool_catalog = stage == "decide"`. | ✅ | 2026-06-30 |
| TASK-018 | Update `Think.run` arg docs from "decide/refine/resolve" to "decide/refine". | ✅ | 2026-06-30 |

### GOAL-005: Keep prompt composition clean

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-019 | Keep `IDENTITY.md` + `SOUL.md` loaded through `BaseLLMService` for `decide`, because `decide` now owns both answering and tool choice. | ✅ | 2026-06-30 |
| TASK-020 | Do not move tool rules out of `SOUL.md` in this change unless tests show prompt conflict remains; this plan is loop architecture first. | ✅ | 2026-06-30 |
| TASK-021 | Ensure `refine` still receives selected-tool full guide through `build_refine_system_prompt`, and does not receive the full catalog. | ✅ | 2026-06-30 |

### GOAL-006: Update tests for new call counts and behavior

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-022 | Update `tests/unit/agent_loop_test.py::test_no_tool_path_calls_decide_then_resolve` to expect one LLM call and final text from decide. Rename the test. | ✅ | 2026-06-30 |
| TASK-023 | Update one-tool happy path tests to expect `decide -> refine -> act -> decide` rather than `decide -> refine -> act -> decide -> resolve`. | ✅ | 2026-06-30 |
| TASK-024 | Add/adjust a missing-required-arg test to expect `decide -> refine -> act -> decide`. | ✅ | 2026-06-30 |
| TASK-025 | Update prompt-scope tests: decide includes catalog, refine excludes catalog, no resolve call exists. | ✅ | 2026-06-30 |
| TASK-026 | Add a regression test where `Decide` returns normal text without tool calls and that text is not discarded. | ✅ | 2026-06-30 |
| TASK-027 | Add a regression test where `Refine` returns `respond`, and final answer comes from `Think(decide)` without a resolve LLM call. | ✅ | 2026-06-30 |
| TASK-028 | Update any `stopped_by` assertions to the chosen labels (`answer`, `max_iterations`, etc.). | ✅ | 2026-06-30 |

### GOAL-007: Clean docs and architecture notes

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-029 | Update `ARCHITECTURE.md` references from `Think(Decide) -> Think(Refine) -> Act -> ... -> Think(Resolve)` to the new loop. | ✅ | 2026-06-30 |
| TASK-030 | Update `twin/shared/tools/prompts/CONTRIBUTING.md` if it describes mandatory resolve or mandatory refine. | ✅ | 2026-06-30 |
| TASK-031 | Search for literal `resolve` stage references under `twin/shared/agent`, tests, and `.agents/plans/currentplan.md`; update only live architecture/docs/tests, not historical decision records unless they claim current behavior. | ✅ | 2026-06-30 |

# Test Plan

Primary command:

```bash
uv run pytest tests/unit/agent_loop_test.py -q
```

If pytest plugin autoload fails because of an unrelated global pytest plugin, retry with plugin autoload disabled if the project supports it:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest tests/unit/agent_loop_test.py -q
```

Broader focused checks after unit tests pass:

```bash
uv run pytest tests/unit/chat_turn_runner_test.py tests/unit/march7_handle_chat_scope_test.py tests/unit/evernight_agent_test.py -q
```

Static/lint check if touched files are accepted by ruff:

```bash
uv run ruff check twin/shared/agent tests/unit/agent_loop_test.py
```

# Edge Cases

- `Decide` string failure sentinels must still return `stopped_by="failure"` for existing ChatTurnRunner fallback behavior.
- `Decide` text without tool calls must be treated as final answer, not as an error and not discarded.
- Tool result pairing must stay valid for OpenAI and Gemini message formats.
- Missing required args remain the initial trigger for full-guide `Refine`; additional triggers like risky tools can be added later.
- If `max_iterations` is reached after tool execution, do not call `resolve`; ask one final `Think(decide)` pass with native tools disabled and keep a bounded fallback if that answer is empty.
- If a tool fails, its result is still appended and `Decide` gets the chance to answer from the error observation on the next loop.

# Assumptions

- The first implementation should preserve single-tool-per-iteration execution and continue deferring extra tool calls.
- `Refine` remains mandatory for every selected tool call in this phase, with missing required args still the main trigger for the full-guide branch.
- `Resolve` should be deleted from the live stage contract, not renamed.
- `Decide` remains the stage name, with the new official meaning: "decide whether to answer or call a tool."
