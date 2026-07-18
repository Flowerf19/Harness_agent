---
status: done
created: 2026-07-18
last_updated: 2026-07-18
---

# T1 Current Server Time Context

## Summary

Keep server-local current time out of static persona/system prompt assembly.
Each `Think` inference attaches fresh runtime time to a copied stage message;
Decide keeps persona while Refine receives its task context without persona.
Persisted T1 entries and gateway timestamps remain unchanged.

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

### GOAL-004: Move runtime context to Think stages

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-012 | Remove runtime placeholder/file ownership from `PromptManager`; keep it focused on static persona loading and assembly. | ✓ | 2026-07-18 |
| TASK-013 | Attach fresh server time to each `Think` stage message without mutating persisted T1 messages. | ✓ | 2026-07-18 |
| TASK-014 | Omit persona prompts from `Think(Refine)` while retaining its tool guide, dynamic context, conversation, and runtime time. | ✓ | 2026-07-18 |
| TASK-015 | Add focused stage/prompt regression tests and run the relevant unit suites. | ✓ | 2026-07-18 |
| TASK-016 | Synchronize architecture guidance with stage-owned runtime context and persona-free Refine. | ✓ | 2026-07-18 |

## Test Plan

- Rewrite a persona file through `UpdatePersonalityTool` and assert the same `PromptManager` instance exposes the new content immediately.
- Assert static system-prompt assembly contains no runtime timestamp.
- Assert every `Think` call receives a fresh server time in a copied stage message.
- Assert `Think(Decide)` includes persona while `Think(Refine)` omits it.
- Assert runtime injection does not mutate the T1 message list owned by the agent loop.
- Run focused LLM prompt and memory test suites.

## Assumptions

- The server clock and server-local timezone are configured correctly by deployment.
- Relative persona paths resolve from the repository root; absolute paths remain supported for tests/runtime overrides.
- Runtime time is server-local and formatted as `YYYY-MM-DD HH:MM:SS`.
- Runtime context is stage input, not persisted T1 content or global persona content.
