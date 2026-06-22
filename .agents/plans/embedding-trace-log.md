---
status: draft
created: 2026-06-22
last_updated: 2026-06-22
---

# Implementation Plan: Embedding Model Trace Log

## Goal

Add a detailed, machine-parseable trace log for embedding model debug/accuracy analysis. The log must capture model identity, vector statistics, latency, cache hits, and similarity metrics — richer than the current `memories/semantic_trace.log` (which only records timestamp, query text, matched text, cosine similarity, token overlap, and action).

## Success Criteria

- A new trace log file is written when `EMBEDDING_TRACE_LOG_ENABLED=true`.
- Each trace entry contains: model/provider/dimensions, input text, raw vector stats (L2 norm), latency, cache hit, API URL, cosine similarity, token overlap, and the final decision/action.
- Log format is JSON Lines for easy downstream parsing (accuracy evaluation scripts).
- When disabled, zero runtime overhead (no file I/O, no stat collection).
- Existing `semantic_trace.log` remains untouched; the new log is separate.

---

## Architecture

### New Module

- `twin/shared/llm/embedding/embedding_trace_logger.py`
  - `EmbeddingTraceLogger` class: holds config, writes JSON Lines to a rotating/appended file.
  - `TraceRecord` dataclass: schema for one trace event.
  - `cosine_similarity(a, b)` and `token_overlap(a, b)` utility functions (needed because current `semantic_trace.log` computes these at the caller level; moving them to a shared utility makes the trace logger self-contained and reusable).

### Files to Modify

- `twin/shared/config/settings.py` — add env vars for trace log toggle and path.
- `twin/shared/llm/embedding/base_embedding_service.py` — inject `EmbeddingTraceLogger` into `get_embedding` flow; collect latency, cache hit, vector stats.
- `twin/shared/llm/embedding/openai_embedding_service.py` — pass API URL and raw response dimension to trace logger.
- `twin/shared/llm/embedding/gemini_embedding_service.py` — pass API URL and raw response dimension to trace logger.
- `twin/shared/memory/manager.py` — `_preflight_context`: log query text and search results (matched text, cosine similarity, token overlap, action).
- `twin/shared/memory/timeline_summary_store.py` — `search`: optionally emit KNN/BM25 scores into the trace if the trace logger is present (injected or global).

### Interface

```python
# twin/shared/llm/embedding/embedding_trace_logger.py

class EmbeddingTraceLogger:
    def __init__(self, log_path: str, enabled: bool = False) -> None: ...
    def log_embedding(
        self,
        *,
        model_name: str,
        provider: str,
        api_url: str,
        vector_dim: int,
        raw_dim: int | None,
        l2_norm: float | None,
        latency_ms: float,
        cache_hit: bool,
        input_text: str,
        query_text: str | None = None,
        matched_text: str | None = None,
        cosine_similarity: float | None = None,
        token_overlap: float | None = None,
        action: str | None = None,
        extra: dict | None = None,
    ) -> None: ...


def cosine_similarity(a: list[float], b: list[float]) -> float: ...
def token_overlap(a: str, b: str) -> float: ...
```

---

## Metrics to Log

| Field | Source | Why |
|-------|--------|-----|
| `timestamp` | `datetime.now(timezone.utc).isoformat()` | Ordering |
| `model_name` | `BaseEmbeddingService.model_name` | Model identity |
| `provider` | `embedding_factory` resolved alias | Provider identity |
| `api_url` | `OpenAIEmbeddingService.api_url` / `GeminiEmbeddingService.api_url` | Endpoint identity (catches LM Studio vs DashScope vs Gemini) |
| `vector_dim` | `len(vector)` after `_fit_vector` | Final dimension stored in Redis |
| `raw_dim` | `len(vector)` before `_fit_vector` | Detects MRL truncation or provider mismatch |
| `l2_norm` | `math.sqrt(sum(x*x for x in vector))` | Detects unnormalized vectors (critical for Gemini MRL) |
| `latency_ms` | `time.perf_counter()` delta inside `get_embedding` | Performance regression detection |
| `cache_hit` | `cached is not None` | Cache effectiveness |
| `input_text` | The text passed to `get_embedding` (may include `"query: "` prefix) | Reproducibility |
| `query_text` | The original user query (without prefix) | Human-readable query |
| `matched_text` | The best matched summary text from `TimelineSummaryStore.search` | Ground truth for accuracy evaluation |
| `cosine_similarity` | Computed between query embedding and matched embedding | Primary accuracy metric |
| `token_overlap` | Jaccard-like overlap of token sets between query and matched text | Lexical sanity check |
| `action` | `"DUPLICATE DETECTED"` / `"APPENDED"` / `"KNN_RESULT"` / etc. | Decision label for accuracy scoring |
| `knn_score` | Redis KNN `score` (cosine distance) | Raw retrieval score |
| `bm25_score` | Redis BM25 score (if hybrid) | Lexical retrieval score |
| `rrf_rank` | Final rank after RRF fusion | Rank position |

---

## Log Format

**JSON Lines (`.jsonl`)** — one JSON object per line.

- Easy to parse with `jq`, `pandas.read_json(..., lines=True)`, or Python `json.loads` line-by-line.
- Extensible: new fields are backward-compatible.
- Human-readable fallback: pretty-print with `jq .`.

No structured text format. The existing `semantic_trace.log` is plain text; the new trace is explicitly for machine consumption, so JSON Lines only.

Example line:
```json
{"timestamp":"2026-06-22T10:00:00+00:00","model_name":"text-embedding-v3","provider":"openai_compat","api_url":"https://dashscope-intl.aliyuncs.com/compatible-mode/v1","vector_dim":1024,"raw_dim":1024,"l2_norm":1.0,"latency_ms":45.2,"cache_hit":false,"input_text":"query: Hoà thích ăn thịt bò.","query_text":"Hoà thích ăn thịt bò.","matched_text":"Hoà cực kỳ thích ăn thịt bò.","cosine_similarity":0.91,"token_overlap":0.71,"action":"DUPLICATE DETECTED","knn_score":0.09,"bm25_score":null,"rrf_rank":1}
```

---

## Integration into `get_embedding` (Zero Overhead When Disabled)

### Design: Lazy Logger + Guarded Stat Collection

1. `BaseEmbeddingService.__init__` receives an optional `trace_logger: EmbeddingTraceLogger | None = None`.
2. Inside `get_embedding`:
   - Start `perf_counter` only if `trace_logger is not None`.
   - After obtaining the vector, compute `l2_norm` and `raw_dim` only if `trace_logger is not None`.
   - Call `trace_logger.log_embedding(...)` only if `trace_logger is not None`.
3. When disabled (`trace_logger=None`), the code path is a single `if` check — no file I/O, no math, no timer.

### Wiring

- `embedding_factory.create_embedding_service()` constructs the logger from `Config` and passes it to the service constructor.
- Alternatively, use a module-level singleton `get_embedding_trace_logger()` initialized on first import, so callers don't need to thread it through. The factory sets it on the service instance.

---

## `cosine_similarity` and `token_overlap` — Where to Place

**Yes, add them.** The current `semantic_trace.log` computes these at an unknown caller (likely outside the repo or in a different module). To make the trace logger self-contained and testable, these utilities should live in the new module.

- `cosine_similarity(a: list[float], b: list[float]) -> float` — dot product / (norm_a * norm_b). Handle zero vectors.
- `token_overlap(a: str, b: str) -> float` — Jaccard index of token sets (split on whitespace, lowercase, strip punctuation). Matches the existing `semantic_trace.log` semantics.

Placement: `twin/shared/llm/embedding/embedding_trace_logger.py` (top-level functions). They are pure math/string utilities with no side effects.

---

## Configuration (Env Vars)

Add to `twin/shared/config/settings.py`:

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_TRACE_LOG_ENABLED` | `false` | Toggle trace logging. |
| `EMBEDDING_TRACE_LOG_PATH` | `logs/embedding_trace.jsonl` | Output file path. |

Notes:
- `EMBEDDING_TRACE_LOG_ENABLED` uses string comparison (`"true"`) to match existing boolean env patterns (`REDIS_ENABLED`, etc.).
- Path is relative to repo root or absolute. Logger ensures parent directory exists (`os.makedirs`).

---

## Implementation Steps

### GOAL-001: Bootstrap Trace Logger Module

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-001 | Create `twin/shared/llm/embedding/embedding_trace_logger.py` with `TraceRecord` dataclass, `EmbeddingTraceLogger`, `cosine_similarity`, `token_overlap`. | | |
| TASK-002 | Add env vars `EMBEDDING_TRACE_LOG_ENABLED` and `EMBEDDING_TRACE_LOG_PATH` to `twin/shared/config/settings.py`. | | |

### GOAL-002: Integrate Trace Logger into Embedding Services

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-003 | Modify `BaseEmbeddingService.__init__` to accept optional `trace_logger`. Add guarded latency/stat collection in `get_embedding` (subclasses call `super()._log(...)` or the base handles it). | | |
| TASK-004 | Modify `OpenAIEmbeddingService.get_embedding` to pass `api_url`, `raw_dim`, and `latency_ms` to trace logger. | | |
| TASK-005 | Modify `GeminiEmbeddingService.get_embedding` to pass `api_url`, `raw_dim`, `l2_norm` (post-normalization), and `latency_ms` to trace logger. | | |
| TASK-006 | Modify `embedding_factory.create_embedding_service` to instantiate `EmbeddingTraceLogger` from `Config` and inject into service. | | |

### GOAL-003: Log Search Results from Callers

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-007 | Modify `SharedMemoryManager._preflight_context` to capture `query_text`, `matched_text`, `cosine_similarity`, `token_overlap`, and `action` (e.g., `"KNN_RESULT"`) and pass to `trace_logger.log_embedding`. | | |
| TASK-008 | Modify `TimelineSummaryStore.search` to optionally return KNN/BM25/RRF scores so `_preflight_context` can log them. | | |

### GOAL-004: Testing

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-009 | Write unit tests for `cosine_similarity` and `token_overlap` (edge cases: zero vectors, empty strings, unicode). | | |
| TASK-010 | Write unit tests for `EmbeddingTraceLogger` (disabled writes nothing, enabled writes valid JSON Lines, handles missing dirs). | | |
| TASK-011 | Write integration test for `OpenAIEmbeddingService.get_embedding` with a mock trace logger verifying all fields. | | |
| TASK-012 | Write integration test for `GeminiEmbeddingService.get_embedding` with a mock trace logger verifying L2 norm and raw_dim. | | |
| TASK-013 | Run existing test suite (`pytest tests/unit/memory/`) to ensure no regressions. | | |

---

## Test Plan

- **Unit tests**: `tests/unit/llm/embedding/test_embedding_trace_logger.py`
  - `test_cosine_similarity_identical` -> 1.0
  - `test_cosine_similarity_orthogonal` -> 0.0
  - `test_cosine_similarity_zero_vector` -> 0.0 (no division by zero)
  - `test_token_overlap_identical` -> 1.0
  - `test_token_overlap_no_overlap` -> 0.0
  - `test_trace_logger_disabled` -> no file created
  - `test_trace_logger_enabled` -> file exists, each line is valid JSON, required fields present
  - `test_trace_logger_makes_dirs` -> creates parent directories

- **Integration tests**: `tests/unit/llm/embedding/test_openai_embedding_service.py`, `test_gemini_embedding_service.py`
  - Mock `aiohttp.ClientSession.post` to return a fake embedding vector.
  - Assert `trace_logger.log_embedding` was called with expected `model_name`, `api_url`, `latency_ms > 0`, `cache_hit=False`, `raw_dim`, `vector_dim`.
  - Assert second call with same text has `cache_hit=True` and `latency_ms` still collected.

- **Regression tests**:
  - `pytest tests/unit/memory/test_e5_prefix.py` — must pass (no behavior change).
  - `pytest tests/unit/memory/test_store_schema.py` — must pass.

---

## Assumptions

- The accuracy evaluation pipeline will read `embedding_trace.jsonl` directly; no additional exporter needed.
- `token_overlap` semantics should match the existing `semantic_trace.log` (Jaccard over whitespace tokens). If the evaluator expects a different metric, update `token_overlap` accordingly.
- `action` values are caller-defined strings; the trace logger does not validate them.
- File rotation is not required for MVP; simple append mode is sufficient. If log size becomes an issue, add `RotatingFileHandler` later.
- The trace logger is not async; file I/O is synchronous but called from async `get_embedding`. This is acceptable because writes are small and buffered. If latency is critical, switch to `aiofiles` or an async queue.

---

## Files to Read / Modify

| File | Action | Reason |
|------|--------|--------|
| `twin/shared/llm/embedding/embedding_trace_logger.py` | **Create** | New trace logger module |
| `twin/shared/config/settings.py` | **Modify** | Add env vars |
| `twin/shared/llm/embedding/base_embedding_service.py` | **Modify** | Inject trace logger, collect stats |
| `twin/shared/llm/embedding/openai_embedding_service.py` | **Modify** | Log provider-specific fields |
| `twin/shared/llm/embedding/gemini_embedding_service.py` | **Modify** | Log provider-specific fields |
| `twin/shared/llm/embedding/embedding_factory.py` | **Modify** | Wire logger into factory |
| `twin/shared/memory/manager.py` | **Modify** | Log query/matched/similarity/action |
| `twin/shared/memory/timeline_summary_store.py` | **Modify** | Return scores for trace |
| `tests/unit/llm/embedding/test_embedding_trace_logger.py` | **Create** | Unit tests for logger + math utils |
| `tests/unit/llm/embedding/test_openai_embedding_service.py` | **Create** | Integration test for OpenAI service |
| `tests/unit/llm/embedding/test_gemini_embedding_service.py` | **Create** | Integration test for Gemini service |
| `memories/semantic_trace.log` | **Read-only** | Reference for existing format |
