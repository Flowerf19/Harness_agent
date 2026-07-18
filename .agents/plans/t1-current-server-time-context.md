---
status: done
created: 2026-07-18
last_updated: 2026-07-18
---

# T1 Current Server Time Context

## Summary

Render a `{{current_time}}` placeholder from a final runtime prompt template at
system prompt assembly time. Keep static persona content cacheable and do not
change T1 storage, gateway timestamps, or message contents.

### GOAL-001: Add a server-time prompt anchor

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-001 | ~~Add the formatted current server time to `SharedMemoryManager.get_context()`.~~ Superseded by prompt template rendering. | ✓ | 2026-07-18 |
| TASK-002 | ~~Add a deterministic unit test for the generated prompt.~~ Superseded by prompt template rendering. | ✓ | 2026-07-18 |
| TASK-003 | Run focused and relevant memory tests. | ✓ | 2026-07-18 |

### GOAL-002: Render the current-time prompt placeholder

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-004 | ~~Replace the manager-built time header with `{{current_time}}` in both persona `SOUL.md` files.~~ Superseded by the final runtime template. | ✓ | 2026-07-18 |
| TASK-005 | Add a `PromptManager` class and pass the assembled system prompt through it to render `{{current_time}}`. | ✓ | 2026-07-18 |
| TASK-006 | Add deterministic rendering coverage and run focused LLM/memory tests. | ✓ | 2026-07-18 |

### GOAL-003: Move persona prompt ownership into PromptManager

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-007 | Move `IDENTITY.md`, `SOUL.md`, and extra persona file loading/cache into `PromptManager`. | ✓ | 2026-07-18 |
| TASK-008 | Delegate final system-prompt assembly and persona reloads from `BaseLLMService` to `PromptManager`. | ✓ | 2026-07-18 |
| TASK-009 | Verify `UpdatePersonalityTool` refreshes the manager cache immediately after an agent edits a prompt. | ✓ | 2026-07-18 |
| TASK-010 | Run focused and broad unit verification. | ✓ | 2026-07-18 |
| TASK-011 | Move `{{current_time}}` from the start of `SOUL.md` to a final runtime template so the static prompt prefix remains cacheable. | ✓ | 2026-07-18 |

## Test Plan

- Construct `PromptManager` with a fixed clock and assert the exact timestamp replaces the placeholder.
- Assert final system prompts for both personas pass through `PromptManager` and contain the rendered time.
- Assert no unresolved `{{current_time}}` appears in the final system prompt.
- Rewrite a persona file through `UpdatePersonalityTool` and assert the same `PromptManager` instance exposes the new content immediately.
- Assert runtime time is appended after dynamic context and omitted for `include_persona=False` utility prompts.
- Run focused LLM prompt and memory test suites.

## Assumptions

- The server clock and server-local timezone are configured correctly by deployment.
- `PromptManager` only recognizes `{{current_time}}`; unknown template text remains literal.
- Relative persona paths resolve from the repository root; absolute paths remain supported for tests/runtime overrides.
