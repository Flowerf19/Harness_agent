---
status: done
created: 2026-06-10
---

# T2 extraction-failure data loss (P0) + silent-failure observability (P2)

## Summary

Two coupled changes to the hot-path consolidation pipeline under
`twin/shared/memory/timeline/` + `twin/shared/memory/manager.py`:

- **P0 (bug, HIGH):** `Extractor.extract()` swallows LLM/parse failures and
  returns an empty `ExtractResult`, which the consolidator cannot tell apart
  from a transcript that legitimately had nothing worth saving. Both produce
  `status="skipped"`, and `SharedMemoryManager._trim_if_complete` trims T1 on
  `{"ok","skipped"}`. Net: when extraction *fails*, a transcript full of real
  facts is flushed from T1 with zero T2 writes — unrecoverable loss. Fix:
  distinguish failure from genuine-empty and map failure to `status="failed"`
  so T1 is preserved for the next cycle. Genuine-empty keeps skipping + trimming
  (intentional behavior, do not change).

- **P2 (observability):** Several silent failure points (extraction failure,
  dropped candidates, embedding failure, cleanup JSON-parse failures) and the
  entirely-discarded `CleanupReport` make memory rot invisible. There is **no
  metrics framework** in this repo (the only instrumentation is `langsmith`
  `@traceable` on LLM/chain entry points). Fix uses **structured logging only**,
  matching the existing `logger.warning/info("T2:<component>: ...", ...)`
  convention. No new dependency, no new abstraction.

All changes stay **non-fatal to chat**: the consolidator still never raises, the
extractor still never raises, and `consolidate_scope`/the active trigger callback
keep returning normally.

### Line numbers in the original brief — all CONFIRMED (no drift)

Every cited line was accurate as of this commit:

| Claim | Location | Status |
|---|---|---|
| extractor LLM-call exception | `extractor.py:202-204` | ✓ |
| extractor parse/validate fail after strict retry | `extractor.py:221-225` | ✓ |
| consolidator 0-routable → skipped + summarized_ids | `consolidator.py:197-204` | ✓ |
| manager `consolidate_scope` | `manager.py:153-163` | ✓ |
| manager `_trim_if_complete` trims on ok/skipped | `manager.py:308-317` | ✓ |
| consolidator dropped-candidate info log | `consolidator.py:188-194` | ✓ |
| consolidator embed failure → empty vector, still written | `consolidator.py:291-297` | ✓ |
| cleanup supersede JSON parse fail returns [] | `cleanup.py:201-205` | ✓ |
| cleanup topic-merge JSON parse fail returns False | `cleanup.py:292-296` | ✓ |

---

## Root cause (P0), confirmed by trace

1. `Extractor.extract()` (`extractor.py:156`, docstring "never raises") returns
   `_empty_result()` on two failure branches:
   - LLM call raises → `extractor.py:202-204`.
   - JSON parse/validate fails after the strict-JSON retry → `extractor.py:221-225`.
   `_empty_result()` (`extractor.py:145-146`) is `ExtractResult(memories=[],
   primary_catalog="discussion", primary_confidence=0.0)` — **byte-identical** to
   the result for a transcript that genuinely had nothing to save.

2. `Consolidator.consolidate()` (`consolidator.py:93`) calls `extract()` at
   `:167`, gets `memories=[]`, routes 0 candidates, hits the
   `if not routed:` branch at `:197-204`, sets `status="skipped"` **and**
   `result.summarized_entry_ids = summarized_ids` (the full transcript), returns.
   The consolidator's own `try/except` already maps *unexpected* exceptions to
   `status="failed"` (`:232-239`) — but a swallowed extraction failure never
   reaches it.

3. `SharedMemoryManager.consolidate_scope()` (`manager.py:153-163`) calls
   `_trim_if_complete(result)`. `_trim_if_complete` (`manager.py:308-317`) trims
   T1 when `status in {"ok","skipped"}`. So `skipped` + populated
   `summarized_entry_ids` → `self.t1.trim(scope, scope_id, summarized_ids)` →
   the real-fact transcript is gone.

**The bug is entirely at hop 1**: the failure signal is erased before the
consolidator can act on it. The three-state `status` machinery
(`Literal["ok","skipped","failed"]`) and the early-return in `_trim_if_complete`
already exist — they just never see the failure.

### Call sites that pin the contract (verified via codegraph + grep)

- `Extractor.extract` — single production caller: `Consolidator.consolidate`
  (`consolidator.py:167`). Test fake: `FakeExtractor.extract`
  (`consolidator_test.py:89`) returns a canned `ExtractResult`.
- `_empty_result` — only caller is `extract` itself.
- `consolidate_scope` — callers: `consolidate_snapshot` (`manager.py:186`),
  `consolidate_payload` (`manager.py:210`), and wired as
  `active.trigger_callback` + the `ActiveSummaryPolicy` trigger
  (`runtime.py:109,114`). The active trigger **discards the return value**
  (`active/service.py:102`), so a `failed` dict is safe there.
- `Consolidator.consolidate` — also reachable via A2A:
  `EvernightA2AHandler.handle_consolidate_discussion_task` →
  `consolidator.consolidate_payload(payload)` (`a2a_server.py:95-96`); the
  result dict is serialized into an A2A `data` part. So **`status` must stay a
  string in the result dict** — already true.
- `consolidate_snapshot` returns `bool` via `result.get("status") in
  {"ok","skipped"}` (`manager.py:187`); `EvernightAgent.consolidate`
  (`agent.py:77-83`) forwards that bool. With the fix, a failed extraction
  makes this return `False` — correct (consolidation did not succeed).
- `CleanupReport` — produced by `Cleanup.run` (`cleanup.py:103`). Only
  production consumer is `CleanupScheduler._run_now` (`cleanup_scheduler.py:60`),
  which calls `await self._callable(user_id)` and **throws the report away**.
  Confirmed: report is never logged/returned/metered outside tests.

---

## Design

### P0 — contract change: an `ok` flag on `ExtractResult`

**Chosen approach: add `ok: bool = True` to `ExtractResult`** (vs. a typed
exception caught by the consolidator).

Rationale:
- The extractor's documented contract is "never raises" and the consolidator's
  is "never raises"; a typed exception would invert both contracts and force a
  new `try/except` in the consolidator's hot path purely for control flow.
- `ExtractResult` is a Pydantic model already threaded through the one caller
  and the test `FakeExtractor`. A defaulted field is a **purely additive**
  change: every existing `ExtractResult(...)` construction (production
  `_empty_result`, all `consolidator_test.py` fakes, all `extractor_test.py`
  payload-driven results) keeps compiling and defaults to `ok=True`. Only the
  two failure branches set `ok=False`.
- Genuine-empty stays `ok=True, memories=[]` → consolidator skips + trims,
  exactly as today. Failure becomes `ok=False` → consolidator returns `failed`
  → T1 preserved. The two cases are now distinguishable with a one-field check.

Exact signature change (`extractor.py`):

```python
class ExtractResult(BaseModel):
    ok: bool = True                     # NEW: False only when extraction FAILED
    memories: list[CandidateMemory] = Field(default_factory=list)
    primary_catalog: str | None = None
    primary_confidence: float = 0.0
```

`_empty_result()` gains a keyword so the failure branches can flag themselves
without changing the genuine-empty default:

```python
def _empty_result(*, ok: bool = True) -> ExtractResult:
    return ExtractResult(ok=ok, memories=[], primary_catalog="discussion",
                         primary_confidence=0.0)
```

- `extract()` empty-transcript guard (`:166-167`): stays `_empty_result()`
  (ok=True) — empty input is genuine-empty, not failure.
- LLM-call exception (`:202-204`): `return _empty_result(ok=False)`.
- Parse/validate failure after strict retry (`:221-225`): `return
  _empty_result(ok=False)`.
- Defensive `if result is None` (`:227-228`): `return _empty_result(ok=False)`
  (this only reaches here on an internal logic error, treat as failure).
- Success path (`:250`) already returns the validated `result` with default
  `ok=True`. No change.

Consumer change (`consolidator.py`), inserted **immediately after the
`extract()` call** (after `:173`, before the `summarized_ids`/routing block):

```python
extract_result = await self.extractor.extract(...)
result.primary_catalog = extract_result.primary_catalog
result.primary_confidence = extract_result.primary_confidence

if not extract_result.ok:
    # Extraction FAILED (LLM/parse error), not "nothing to save". Do NOT
    # populate summarized_entry_ids → _trim_if_complete sees status="failed"
    # and preserves T1 for retry next cycle.
    self.logger.warning(
        "T2:consolidator: extraction FAILED scope=%s/%s — preserving T1 for retry",
        scope, scope_id,
    )
    result.status = "failed"
    result.error = "extraction_failed"
    return result
```

Because this returns **before** `result.summarized_entry_ids` is set, the
result carries an empty `summarized_entry_ids`. `_trim_if_complete` returns
early on `status="failed"` (already true at `manager.py:309`), so T1 is doubly
safe (early-return + empty id list). The genuine-empty branch (`:197-204`) is
untouched and still flushes.

**No change needed in `manager.py`.** `_trim_if_complete` already early-returns
on any status not in `{"ok","skipped"}`, and `_result_to_dict` already includes
`status` and `error`. Verified.

### P2 — observability via structured logging (no new framework)

Reuse the exact existing pattern: `self.logger.warning(...)` /
`logger.warning(...)` with the `"T2:<component>: ..."` prefix and `%s`
placeholders. Upgrade the chosen silent points from `debug`/`info`/silent to a
visible level, and surface the dropped `CleanupReport`.

1. **Extractor failure** — already covered by P0: the two failure branches keep
   their existing `logger.warning(...)` (`:203`, `:221-224`), and the
   consolidator adds the `extraction FAILED ... preserving T1` warning above.
   That is the single, authoritative "extraction failed" signal.

2. **Dropped candidates** (`consolidator.py:188-194`) — currently
   `self.logger.info(...)` per dropped candidate. Keep the per-drop info line,
   but add **one aggregate warning after the routing loop** when drops occurred,
   so a transcript that yields candidates but routes none (or mostly bot/
   unmatched) is visible without grepping per-line:

   ```python
   dropped = len(extract_result.memories) - len(routed)
   if dropped:
       self.logger.warning(
           "T2:consolidator: dropped %d/%d candidate(s) (bot/unmatched subject) "
           "scope=%s/%s", dropped, len(extract_result.memories), scope, scope_id,
       )
   ```
   Place this right after the routing `for` loop (after `:195`), before the
   `if not routed:` check.

3. **Embedding failure** (`consolidator.py:291-297`) — already
   `self.logger.warning("T2:consolidator: embed failed: %s", exc)`. The gap is
   that the memory is then written with an **empty vector** (`:304`,
   `embedding or []`), which silently makes it invisible to vector KNN. Make the
   consequence explicit by extending the existing warning (do not add a counter):

   ```python
   self.logger.warning(
       "T2:consolidator: embed failed, writing memory WITHOUT vector "
       "(not retrievable by KNN) scope-user=%s: %s", user_id, exc,
   )
   ```
   (Single edit to the existing log call; behavior of writing the memory is
   intentionally preserved — better a non-vector memory than data loss.)

4. **Cleanup JSON-parse failures** (`cleanup.py:201-205` supersede,
   `:292-296` topic-merge) — currently `logger.debug(...)`. Promote both to
   `logger.warning(...)` (parse failure means an LLM cleanup pass silently did
   nothing). Keep the messages, change the level:
   - `:204` `logger.debug` → `logger.warning("T2:cleanup: supersede JSON parse failed: %s", exc)`
   - `:295` `logger.debug` → `logger.warning("T2:cleanup: topic merge JSON parse failed: %s", exc)`

   These already feed `report.errors` indirectly only when the *step* crashes;
   the parse-fail path returns `[]`/`False` without recording an error, so the
   log is the only signal — warning level is correct.

5. **Surface `CleanupReport`** — the report is computed and discarded. Surface
   it at the one production consumer, `CleanupScheduler._run_now`
   (`cleanup_scheduler.py:57-72`), with **no signature change** to
   `Cleanup.run` (keeps all cleanup tests intact):

   ```python
   async def _run_now(self, user_id: str) -> None:
       async with self._lock_for(user_id):
           try:
               report = await self._callable(user_id)
           except asyncio.CancelledError:
               raise
           except Exception as exc:
               logger.warning(
                   "T2:cleanup_scheduler: cleanup failed for %s: %s",
                   user_id, exc, exc_info=True,
               )
           else:
               if report is not None and (
                   getattr(report, "supersedes_applied", 0)
                   or getattr(report, "topics_merged", 0)
                   or getattr(report, "errors", None)
               ):
                   logger.info(
                       "T2:cleanup_scheduler: user=%s supersedes=%s topics_merged=%s errors=%s",
                       user_id,
                       getattr(report, "supersedes_applied", 0),
                       getattr(report, "topics_merged", 0),
                       getattr(report, "errors", []),
                   )
           finally:
               current = self._pending.get(user_id)
               if current is not None and current.done():
                   self._pending.pop(user_id, None)
   ```

   `getattr(...)` is defensive because the scheduler's type hint says the
   callable returns `None` and `test_scheduler_*` pass plain callables that
   return `None`; those stay quiet (report is `None`). The real `cleanup.run`
   returns a `CleanupReport`, so production gets a summary line only when
   something happened or errored.

**Out of scope (explicitly not doing):** no prometheus/statsd/OpenTelemetry, no
new `@traceable` spans (those wrap user-facing LLM turns, not memory internals),
no changes to log *format* elsewhere, no `errors` plumbing into the
consolidation result dict.

---

## Ordered edits

### File 1 — `twin/shared/memory/timeline/extractor.py`
1. Add `ok: bool = True` as the first field of `ExtractResult` (after `:118`).
2. Change `_empty_result` signature to `def _empty_result(*, ok: bool = True)`
   and pass `ok=ok` into the `ExtractResult(...)` (`:145-146`).
3. In `extract`: LLM-call except branch (`:204`) → `_empty_result(ok=False)`.
4. parse/validate give-up branch (`:225`) → `_empty_result(ok=False)`.
5. defensive `result is None` branch (`:228`) → `_empty_result(ok=False)`.
   (Empty-transcript guard at `:167` stays `_empty_result()` = ok=True.)

### File 2 — `twin/shared/memory/timeline/consolidator.py`
6. After `result.primary_confidence = extract_result.primary_confidence`
   (`:175`), add the `if not extract_result.ok:` block → set
   `status="failed"`, `error="extraction_failed"`, warn, `return result`.
7. After the routing loop (after `:195`, before `if not routed:`), add the
   aggregate dropped-candidate warning.
8. Extend the embed-failure warning message (`:294-296`) to state the memory is
   written without a vector.

### File 3 — `twin/shared/memory/timeline/cleanup.py`
9. `:204` supersede parse-fail `logger.debug` → `logger.warning`.
10. `:295` topic-merge parse-fail `logger.debug` → `logger.warning`.

### File 4 — `twin/shared/memory/timeline/cleanup_scheduler.py`
11. In `_run_now` (`:57-72`), capture the return of `self._callable(user_id)`
    and add an `else:` branch logging a `CleanupReport` summary when non-trivial.

**No edit to `manager.py`** (already correct). **No edit to `__init__.py`**
(no new exports — `ExtractResult` already exported).

---

## Test plan

Tests live in `tests/unit/memory/`, run with:
`conda run -n discord_bot python -m pytest tests/unit/memory -q`
(per `.agents/TESTING_GUIDE.md`; use `python -m pytest`, not bare `pytest`).
Unit memory tests mock Redis/LLM — no external services. The redis-backed
cleanup tests skip automatically when Redis is down.

### A. `extractor_test.py` — new `ok` contract
- **Update** `test_extract_invalid_json_returns_empty` (`:134`): add
  `assert res.ok is False` (failure case).
- **Update** `test_extract_llm_raises_returns_empty` (`:142`): add
  `assert res.ok is False`.
- **Update** `test_extract_gives_up_after_retry` (`:172`): add
  `assert res.ok is False`.
- **Update** `test_extract_empty_transcript_returns_empty` (`:63`): add
  `assert res.ok is True` (genuine-empty stays ok).
- **Add** `test_extract_success_sets_ok_true`: valid payload with memories →
  `assert res.ok is True`.
- **Add** `test_extract_genuine_empty_sets_ok_true`: valid JSON with
  `memories: []` (LLM said "nothing worth saving") → `res.ok is True and
  res.memories == []`. Pins the distinction at the extractor boundary.

### B. `consolidator_test.py` — failure vs genuine-empty routing
The `FakeExtractor` returns a canned `ExtractResult`; pass `ok=` to drive cases.
- **Add** `test_consolidate_extraction_failure_status_failed`: build with
  `extract_result=ExtractResult(ok=False, memories=[])`, entries present →
  `res.status == "failed"`, `res.error == "extraction_failed"`, and crucially
  `res.summarized_entry_ids == []` (so manager won't trim).
- **Verify unchanged** `test_consolidate_no_candidates_skipped` (`:163`) and
  `test_consolidate_channel_no_match_skipped` (`:468`): genuine-empty / 0-routable
  still `status="skipped"` with populated `summarized_entry_ids`. (These pass
  as-is because `ExtractResult` defaults `ok=True`; assert no regression.)
- **Add** `test_consolidate_dropped_candidates_logged` (optional, uses
  `caplog`): channel scope, candidates that all route to bot/unmatched →
  assert a `WARNING` record containing `"dropped"` is emitted and status is
  `skipped` (drops are not a failure).

### C. `manager_test.py` — T1 preservation is the real acceptance gate
Add a focused test wiring a real `SharedMemoryManager` + real `ActiveMemory`
(in-memory `FakeRedis` already exists in this file) + a `FakeConsolidator`
that returns a chosen `ConsolidationResult`:
- **Add** `test_manager_does_not_trim_t1_when_extraction_fails`: seed 2 T1
  entries; `FakeConsolidator.consolidate` returns
  `ConsolidationResult(status="failed", scope=..., scope_id=...,
  summarized_entry_ids=[])`; call `consolidate_scope`; assert
  `len(await active.get_context(scope, scope_id)) == 2` (T1 intact) and the
  returned dict `status == "failed"`.
- **Add** `test_manager_trims_t1_when_extraction_genuinely_empty`: same seeding;
  `FakeConsolidator` returns `status="skipped"` with
  `summarized_entry_ids=[<both ids>]`; assert T1 is trimmed (context empties /
  shrinks per `ActiveMemory.trim` semantics — mirror the existing
  `test_manager_channel_consolidation_extracts_once` assertion style).
  These two tests are (a) and (b) from the brief and are the load-bearing proof
  that the bug is fixed without breaking the intentional flush.

### D. `cleanup_test.py` — parse-fail visibility + report surfacing
- **Add** `test_supersede_parse_failure_logs_warning` (`caplog`): cluster of 2
  similar memories (reuse `StubStore`/`_vec_mix` pattern at `:161`), `FakeLLM`
  returns non-JSON `"not json"`; `await cleanup.run(...)` → assert a `WARNING`
  with `"supersede JSON parse failed"` and that `run` still returns a
  `CleanupReport` (non-fatal). Same shape for topic-merge if cheap.
- **Add** `test_scheduler_logs_report_summary` (`caplog`): `CleanupScheduler`
  with a `cb` returning a `CleanupReport(supersedes_applied=1)`; `schedule` +
  `flush`; assert an `INFO` record containing `"supersedes=1"`. Also assert the
  existing `test_scheduler_*` (callable returns `None`) emit **no** summary line
  (report is `None`).

### Acceptance criteria
1. `tests/unit/memory -q` green, including the existing skipped/flush tests
   (no regression to intentional genuine-empty flushing).
2. New tests prove: (a) T1 NOT trimmed on extraction failure, (b) T1 IS trimmed
   on genuine-empty, (c) the new log signals fire (extraction-failure warning,
   dropped-candidate warning, cleanup parse-fail warning, cleanup-report summary).
3. Chat path cannot crash: `extract` and `consolidate` still never raise;
   `consolidate_scope` still returns a dict; the active trigger still ignores it.

---

## Risks / edge cases / human decisions

- **`consolidate_snapshot` bool flip (low risk, correct):** on extraction
  failure it now returns `False` (`status="failed"` ∉ `{"ok","skipped"}`), so
  `EvernightAgent.consolidate` reports failure over A2A
  (`a2a_server.py:62` "Consolidation failed"). This is accurate — consolidation
  genuinely failed and T1 was preserved. No retry scheduler exists today; the
  preserved T1 is re-attempted on the next threshold/idle trigger
  (`active/service.py:94-102`), which is the intended recovery path. **Confirm
  the caller is OK with `False`/"failed" surfacing instead of a silent success.**
- **`error="extraction_failed"` string:** chosen as a stable, greppable
  sentinel distinct from the consolidator's `str(exc)` (`:238`). If any consumer
  pattern-matches `error`, this is new — grep found none. Flag for review.
- **Empty-vector memory on embed failure is intentionally preserved.** The plan
  only makes it *visible*, not fixed. If the team prefers to *drop* a memory
  that cannot be embedded (instead of writing a non-retrievable one), that is a
  separate behavior decision — out of scope here. **Human decision.**
- **Log-level noise:** promoting cleanup parse-fails to `warning` and adding the
  consolidator dropped-candidate + extraction-failure warnings increases WARN
  volume if the local LLM is flaky. That is the point (rot must be visible), but
  if WARN is alert-wired, consider INFO for dropped-candidate. Default chosen:
  WARNING for failure/parse-fail (actionable), aggregate dropped-candidate at
  WARNING, per-candidate drop stays INFO.
- **`CleanupReport` returned-type vs hint:** `CleanupScheduler.__init__` types
  `cleanup_callable` as `Callable[[str], Awaitable[None]]` while `Cleanup.run`
  returns `CleanupReport`. The plan reads the return defensively via `getattr`
  rather than tightening the hint, to avoid touching the test callables that
  return `None`. Tightening the type hint to `Awaitable[CleanupReport | None]`
  is optional cleanup, not required.
- **No metrics layer exists** — confirmed by grep (only `langsmith.traceable` +
  `collections.Counter` for tallying). Introducing one would violate the
  "no new framework" constraint. If the team later wants counters, the
  structured-log call sites added here are the natural seams.

## Assumptions
- Pydantic v2 (`model_validate_json`, `field_validator` already in use) — adding
  a defaulted bool field is backward-compatible.
- `tests/unit/memory` is run without Redis for the extractor/consolidator/manager
  cases (mirrors existing fakes); the new cleanup `caplog` tests use `StubStore`
  and avoid the redis fixture.
- No other repo (e.g. a separate Evernight deployment) imports `ExtractResult`
  positionally; the new first field `ok` defaults so keyword/`memories=`
  construction is unaffected — grep shows all constructions are keyword-based.

---

## Outcome (2026-06-10) — shipped

Implemented exactly as specified; **`manager.py` untouched** as predicted (its
three-state machinery + `_trim_if_complete` early-return already handled
`status="failed"`).

Independent `code-reviewer` pass: **Approve** — no blocker/major. One **[Minor]**:
the failure-case manager test seeded 2 entries with an empty
`summarized_entry_ids`, so it would have passed even if the `_trim_if_complete`
status guard regressed (an empty trim payload + 2 entries inside `keep_recent=5`
never trims regardless). **Addressed** by strengthening
`test_manager_does_not_trim_t1_when_extraction_fails`: seed **7** entries
(> `keep_recent=5`) **and** `CannedConsolidator(fill_summarized_ids=True)`, so a
full trim payload is present and only the `status="failed"` guard keeps T1 intact.
**Mutation-verified:** temporarily adding `"failed"` to the trim set made the test
fail (`assert 5 == 7`); reverting restored green. → This supersedes the "seed 2"
sketch in Test plan §C, which could not observe trimming inside the kept window.

- Files: `extractor.py`, `consolidator.py`, `cleanup.py`, `cleanup_scheduler.py`
  + `extractor_test.py`, `consolidator_test.py`, `manager_test.py`, `cleanup_test.py`.
- Tests: **142 passed** (`tests/unit/memory`); full `tests/unit` **214 passed**.
- Commit: `715f954` on `feature/memory-rewrite` (not pushed).
- Deferred (not in this change): **P1a** supersede window (24h/100), **P1b** T3
  staleness / missing provenance back-link, **P3** embedding-dim guard.
