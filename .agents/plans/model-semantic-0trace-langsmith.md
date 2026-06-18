---
status: in-progress
created: 2026-06-18
last_updated: 2026-06-18
---

# Model Semantic 0Trace + LangSmith Workflow

## Summary

Build an internal semantic-memory trace module named `model_semantic_0trace` and use
LangSmith as the observability/evaluation layer around it.

LangSmith should not be treated as the durable semantic state system. Current
LangSmith docs show strong support for tracing async/sync runs, tags, metadata,
nested LLM/tool spans, feedback, datasets, evaluations, cost/usage metadata, and
project-based filtering. It can show and evaluate the workflow, but the bot still
needs its own domain module for model-scoped semantic-memory change history,
dedupe decisions, profile/T2 write provenance, and replayable state transitions.

Success criteria:

- Existing `memories/semantic_trace.log` behavior is replaced or wrapped by a
  structured module named `model_semantic_0trace`.
- Semantic updates are tracked per model/provider/workflow when T2 timeline or
  T3 profile memory changes.
- Model changes produce comparable trace records, so regressions in semantic
  extraction/dedupe can be inspected later.
- LangSmith receives nested workflow traces with model, agent, scope, memory
  action, and trace event metadata.
- Local operation still works when LangSmith env vars are missing.

## Tasks

### GOAL-001: Define Internal Semantic Trace Contract

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-001 | Add `twin/shared/memory/model_semantic_0trace.py` as the single internal module for semantic-memory trace events. | | |
| TASK-002 | Define a compact event schema: `trace_id`, `timestamp`, `agent_name`, `provider`, `model`, `workflow`, `scope`, `scope_id`, `user_id`, `source`, `action`, `section`, `summary_id`, `similarity`, `token_overlap`, `old_text_hash`, `new_text_hash`, `content_preview`, `metadata`. | | |
| TASK-003 | Implement append-only JSONL writing under `memories/model_semantic_0trace.jsonl` with atomic directory creation and tolerant failure logging. | | |
| TASK-004 | Keep backward compatibility by optionally appending a human-readable bridge line to `memories/semantic_trace.log`, controlled by `MODEL_SEMANTIC_0TRACE_LEGACY_LOG=true` defaulting to true for the first rollout. | | |
| TASK-005 | Add a small read/query helper for future tools: filter by `model`, `agent_name`, `scope_id`, `workflow`, and `action`; no analytics database yet. | | |

### GOAL-002: Hook Trace Into Memory Writes

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-006 | Inject a `ModelSemantic0Trace` instance into `SharedMemoryManager` as an optional dependency with no-op behavior when omitted. | | |
| TASK-007 | In `ConsolidateMemoryTool.execute`, emit events after each successful T2 `store_summary` with topic, importance, summary id, source scope, provider/model, and messages summarized. | | |
| TASK-008 | In `ConsolidateMemoryTool.execute`, emit events for every T3 profile bullet attempt: appended, skipped duplicate, invalid section, or failed write. | | |
| TASK-009 | Extend `MarkdownProfileStore.append_raw` or wrap calls from `ConsolidateMemoryTool` so duplicate/append decisions can be recorded without changing profile file format. | | |
| TASK-010 | Add trace events for profile whole-file/section updates through `manage_user_profile` if that tool writes T3 outside consolidation. | | |

### GOAL-003: Support Per-Model Comparison

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-011 | Add model identity helper that normalizes provider and model from `llm_service` and returned `LLMResponse.model`. | | |
| TASK-012 | Include the summarizer model in every consolidation semantic trace event, not only the chat model used by March7/Evernight. | | |
| TASK-013 | Add deterministic content hashes so the same semantic bullet/summary can be compared across model changes without logging full sensitive content. | | |
| TASK-014 | Provide a minimal CLI or test helper later (`python -m twin.shared.memory.model_semantic_0trace ...`) for comparing events by model; keep this out of the first hot-path patch unless needed. | | |

### GOAL-004: Integrate LangSmith Around The Bot Workflow

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-015 | Keep existing `@traceable` spans on `March7Agent.handle_chat`, `EvernightAgent.handle_chat`, `OpenAIService.generate_response`, and `GeminiService.generate_response`. | ✅ | 2026-06-18 |
| TASK-016 | Add dynamic LangSmith metadata/tags at workflow entry points: `agent_name`, `provider`, `model`, `scope`, `scope_id`, `channel_id`, `workflow`, `trace_module=model_semantic_0trace`. | ✅ | 2026-06-18 |
| TASK-017 | Wrap consolidation with a LangSmith span named `memory_consolidation` and child spans for `t2_store_summary`, `t3_profile_update`, and `semantic_trace_append` where practical. | | |
| TASK-018 | Configure env-driven tracing: `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_ENDPOINT`, `LANGSMITH_PROJECT`, plus a repo-specific default project name documented as `march7-bot`. | ✅ | 2026-06-18 |
| TASK-019 | Ensure missing LangSmith config does not break bot startup or memory writes. | ✅ | 2026-06-18 |
| TASK-020 | Add LangSmith experiment metadata conventions for future evals: `models`, `prompts`, `tools`, `memory_schema_version`, and `semantic_trace_version`. | | |

### GOAL-007: Preserve LangSmith Trace Tree Across A2A

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-029 | Send current LangSmith parent headers from gateway/consolidation clients into A2A `tasks/send`, `tasks/get`, and stream requests. | ✅ | 2026-06-18 |
| TASK-030 | Continue incoming A2A task handlers under `tracing_context(parent=...)` so Evernight child spans stay in the gateway trace tree. | ✅ | 2026-06-18 |
| TASK-031 | Add focused tests for the repo `traceable` wrapper, dynamic `langsmith_extra`, and A2A parent context propagation. | ✅ | 2026-06-18 |

### GOAL-005: Tests And Verification

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-021 | Add unit tests for JSONL append/query behavior without LangSmith. | | |
| TASK-022 | Add a unit test for `ConsolidateMemoryTool` proving T2 and T3 write attempts emit `model_semantic_0trace` events. | | |
| TASK-023 | Add a unit test proving semantic trace failures are logged but do not fail consolidation. | | |
| TASK-024 | Run focused tests: `conda run -n discord_bot python -m pytest tests/unit/memory -q` and any new consolidate-memory test file. | | |
| TASK-025 | Run a local Evernight A2A smoke only after env/services are available; do not require Discord tokens for acceptance. | | |

### GOAL-006: Documentation And Rollout

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-026 | Document the `model_semantic_0trace` file, env vars, and LangSmith workflow in `.agents/PROJECT_CONTEXT.md`. | | |
| TASK-027 | Add a short README note explaining that LangSmith observes/evaluates traces, while `model_semantic_0trace` is the durable semantic-memory audit log. | | |
| TASK-028 | After implementation, update this plan to `done` and mark completed tasks with dates. | | |

## Test Plan

- Unit: instantiate `ModelSemantic0Trace` with a temp `memories` path and assert
  valid JSONL output, legacy log output, filters, and content hashing.
- Unit: mock `ConsolidateMemoryTool` dependencies and assert trace events for:
  T2 summary stored, T3 bullet appended, T3 duplicate skipped, parse failure,
  and no meaningful content.
- Unit: missing or failing trace writer must not change consolidation return
  status.
- Focused command:

```bash
conda run -n discord_bot python -m pytest tests/unit/memory -q
```

- Additional focused command after adding tests:

```bash
conda run -n discord_bot python -m pytest tests/unit/memory/test_model_semantic_0trace.py tests/unit/consolidate_memory_tool_test.py -q
```

## Assumptions

- `model_semantic_0trace` is the required module/log identity and should be
  spelled exactly with a zero before `trace`.
- `memories/semantic_trace.log` is legacy evidence, not the desired long-term
  machine-readable format.
- LangSmith is already a dependency in `requirements.txt`; implementation should
  avoid adding new dependencies.
- Semantic trace content may contain personal memory, so the structured log
  should store hashes and previews by default rather than full raw text for every
  field.
- The first implementation should hook the Evernight consolidation path first,
  because that is where T2 summaries and T3 profile writes currently happen.
