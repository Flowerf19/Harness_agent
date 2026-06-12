---
status: done
created: 2026-06-11
completed: 2026-06-12
---

# Auto T3 Profile Curation + Whole-File Curation Mode

## Summary

Close the T3-never-cleaned gap. Today the consolidator *fills* T3 via `append_raw`
(exact case-insensitive dedup only → paraphrased dupes pile up), and T3 is never
auto-cleaned (`cleanup.py:82` docstring: *"T3 curation belongs to
manage_user_profile"*). This plan adds:

- **A — whole-file "all" mode** on `manage_user_profile`: the same tool can rewrite
  the entire profile in one call, from a `sections = {section: [bullets]}` map (never
  raw markdown — the store renders canonical markdown), guarded against catastrophic
  bullet loss.
- **B — auto curation**: an LLM curation pass that dedups/merges/drops stale bullets,
  fired **30 min after a user goes idle** by a per-user debounced scheduler
  (`ProfileCurationScheduler`, mirroring `CleanupScheduler`), with cost/idempotency
  guards so a no-op conversation doesn't burn an LLM call.

Ordering preserved: idle-15 consolidates+promotes (fills T3) → idle-30 curates (cleans
T3). The curation window stays strictly longer than the consolidation idle window.

### Success criteria

- `replace_all` writes canonical markdown atomically, honors `expected_profile_hash`
  (returns conflict on stale), and refuses catastrophic shrink.
- `manage_user_profile` with `section` omitted runs whole-file mode; with `section`
  present behaves exactly as today.
- 30 min after a user's last message, an idempotent LLM curation pass runs once,
  reads the full profile, writes back a deduped canonical profile, and never crashes
  the chat path.
- `conda run -n discord_bot python -m pytest tests/unit/memory tests/unit/manage_profile_tool_test.py -q` passes.

---

## Grounding (verified, do not re-litigate)

| Fact | Evidence |
|---|---|
| T3 filled by promote step | `consolidator.py:368-401` `self.profile_appender(...)` → `append_raw` |
| `append_raw` dedup is exact case-insensitive only | `markdown_store.py:284-286` |
| T3 never auto-cleaned | `cleanup.py:81` docstring |
| `replace_section` lock+hash semantics to mirror | `markdown_store.py:315-372` |
| `write_raw` + `_render_markdown` + `_sanitize_bullets` building blocks exist | `markdown_store.py:301`, `:71`, `:96` |
| Poll-based can't see flushed user | `active/store.py:95-107` (`unsummarized_tokens>0` only); `summary.py:56-58` (`tokens<=0` early return) |
| Correct pattern = per-user debounce scheduler | `cleanup_scheduler.py` (cancel prior task, per-user lock, fire-and-forget, never raises) |
| Shared runtime is the single wiring point for BOTH processes | `runtime.py:63-129` `build_shared_agent_runtime` builds one `MarkdownProfileStore()` + `CleanupScheduler` |
| LLM interface | `extractor.py:197` `llm.generate_response(messages=, system_prompt=, use_native_tools=False, max_tokens=)` → `.content` |
| Prompt placement convention | `SYSTEM_PROMPT` is an inline module constant in `extractor.py:54` / `cleanup.py` (no separate prompt file) |
| Constants | `IDLE_TRIGGER_MINUTES=15`, `TOKEN_THRESHOLD=2000` in `active/constants.py`; `CLEANUP_DEBOUNCE_SECONDS=30` in `timeline/constants.py`; `T3_PROMOTE_*` in `timeline/constants.py` |
| Profile sections | `profile/constants.py` `SECTIONS` (8 fixed) |
| `manage_user_profile` tool is Evernight-only (manual) | `system_tools.py:38-44` `visible_to/allowed_to = {"evernight"}` |

### Corrected process ownership (this changes Open Decision #1)

The spec assumed *"curation is Evernight's job; `observe()` runs in both processes."*
Verified reality for the **user scope (1-1 DM)** — the only scope with a clean per-user
profile:

- Gateway observes the incoming DM into **March7's** memory manager
  (`gateway/core/handler.py` `_observe_message` → `march7.memory.observe_user_message`).
- March7 starts an `InactivityTrigger` over `("user","channel")`
  (`twin/march7/__main__.py:37-44`); Evernight's covers only `("user",)`.
- Both processes build the **same** runtime via `build_shared_agent_runtime`, and
  `MarkdownProfileStore()` is **file-backed** (`memories/<id>.md`) with a cross-process
  `flock` — so it is effectively one shared store, written by whichever process
  consolidates. For DMs that is **March7**.

Conclusion: the activity signal for a DM is available in **March7**, not Evernight. The
scheduler must therefore live in the **shared runtime** (so it exists in both
processes), and `schedule(user_id)` must be called from the **shared** `observe`/manager
path — it will then fire in whichever process observed the user (March7 for DMs). The
LLM curation callable only needs the shared `llm_service` + `profile_store`, both
present in `build_shared_agent_runtime`. No Evernight-specific wiring is required, and
the manual `manage_user_profile` tool stays Evernight-only and untouched in its
gating.

---

## Open decisions — recommendations

1. **Where `schedule(user_id)` is called + scope policy. (USER DECISION: cover BOTH DM
   and channel.)**
   Key the scheduler on the **author (the user who spoke)**, not the scope — because T3
   is user-centric and "30 min after a user stops talking" is a per-*user* event. This
   unifies both scopes cleanly:
   - `SharedMemoryManager.observe_user_message` (`manager.py:40`) → DM: schedule
     `str(user_id)` when `role != "assistant"`.
   - `SharedMemoryManager.observe_channel_message` (`manager.py:81`) → channel: schedule
     `str(author_id)` (always a user turn; `author_id` is the speaking participant).
   Both guarded `if self.curation_scheduler is not None`. The bot's own turns
   (`add_assistant_message`, or `role=="assistant"`) never schedule. Result: a user's
   curation timer resets whenever THEY speak in any DM or channel, and fires 30 min after
   their last message anywhere. The curator's trivial/idempotency guards (Phase 3) make
   scheduling a profile-less or unchanged participant a cheap near-no-op (one file read,
   no LLM call), so fanning out across every channel speaker is safe.
   **Edge note:** a participant who is *mentioned but never speaks* can get their profile
   filled by subject-routing yet never trigger curation (no idle-stop event for them) —
   the manual `manage_user_profile` still covers that case.

2. **The LLM curation pass.** New module `twin/shared/memory/profile/curator.py`
   (`ProfileCurator`), constructed `ProfileCurator(profile_store, llm_service)`, mirroring
   `Extractor(llm)` / `Cleanup(...,llm=...)`. Inline `SYSTEM_PROMPT` constant (same
   convention as `extractor.py:54`). Input = full current profile rendered with the 8
   canonical section headers; output = STRICT JSON `{"sections": {section: [bullets]}}`,
   canonical sections only. One LLM call via `generate_response(..., use_native_tools=
   False, max_tokens=PROFILE_CURATION_MAX_TOKENS)`, with the same one-retry-then-give-up
   posture as `Extractor`.

3. **Cost / idempotency guard.** Track last-curated hash per user. Storage: a sibling
   file `memories/.curation/<user_id>.hash` (one line = the profile hash last curated),
   written by `ProfileCurator` after a successful curate. This reuses the existing
   file-backed convention, needs no schema/Redis change, and survives restarts. Skip
   curation when: (a) profile is empty/trivial (`get_system_prompt_context` returns ""
   OR total bullets below a floor, e.g. `< 4`), or (b) `current_hash == last_curated_hash`.
   Recommend the file marker over Redis (profile store is already file-backed; keeps T3
   self-contained).

4. **Constants.** Add `PROFILE_CURATION_IDLE_SECONDS = 1800` (30 min) and
   `PROFILE_CURATION_MAX_TOKENS = 4000`, plus `PROFILE_CURATION_MIN_BULLETS = 4` in
   `profile/constants.py`. Add an assertion/comment that the idle window must exceed
   `IDLE_TRIGGER_MINUTES*60` (15 min) so consolidation always lands first.

5. **Non-fatal guarantee.** `ProfileCurationScheduler` copies `CleanupScheduler`'s
   try/except posture (`cleanup_scheduler.py:57-87`): the callable is wrapped, all
   exceptions logged not raised, `asyncio.CancelledError` re-raised. `schedule()` is
   fire-and-forget from `observe`, so a curation failure can never reach the chat path.

---

## Catastrophic-loss guard (the chosen rule)

In `replace_all`, after sanitizing the incoming map, compute:

```
old_total = sum(len(parsed[s]) for s in SECTIONS)         # existing bullets
new_total = sum(len(cleaned[s]) for s in SECTIONS)         # proposed bullets
```

**Rule:** reject the write when the rewrite drops more than **50%** of existing bullets
*and* the profile was non-trivial to begin with:

```
if old_total >= PROFILE_CURATION_MIN_BULLETS and new_total < old_total * 0.5
   and not allow_shrink:
       return {"ok": False, "shrink_blocked": True, "old_total", "new_total",
               "profile_hash": current_hash, "written": False}
```

Rationale: a weak local model's main failure mode is wholesale dropping; 50% on a
profile of ≥4 bullets is a strong signal of a bad rewrite while still allowing legit
heavy dedup of a bloated profile via the explicit `allow_shrink=True` escape hatch.
Tiny profiles (`old_total < 4`) are exempt so a 1→0 legitimate cleanup isn't blocked.
This is layered defense on top of canonical render (model can't invent sections /
structure) — content is the only thing it controls.

---

## Phase breakdown

### Phase 1 — Store: `replace_all`

**File:** `twin/shared/memory/profile/markdown_store.py`

Add method after `replace_section` (after `:372`):

```python
async def replace_all(
    self,
    user_id: str,
    sections: dict[str, list[str]],
    expected_profile_hash: str | None = None,
    *,
    allow_shrink: bool = False,
) -> dict[str, Any]:
```

Behavior (mirror `replace_section` lock+hash, `markdown_store.py:334-372`):
- Validate `sections` is a dict; reject keys not in `SECTIONS` (`ValueError`,
  consistent with `replace_section`'s `invalid section` raise). Missing keys default to
  current bullets? **No** — whole-file mode means the map is authoritative; a key absent
  from the map renders as empty. (Document this clearly; the tool layer always sends all
  8 keys from the curator output — see Phase 3.)
- `_sanitize_bullets` each list (reuses `markdown_store.py:96`).
- Acquire `_profile_file_lock`, read current text, `current_hash = profile_hash(text)`.
- If `expected` provided and stale → return `{ok:False, conflict:True, profile_hash:
  current_hash, expected_profile_hash, written:False}` (same shape as `replace_section`).
- Parse current → compute `old_total`; build full `cleaned` map (all 8 keys, default
  `[]`) → `new_total`. Apply catastrophic-loss guard (above) → return `shrink_blocked`
  result if tripped.
- `new_text = _render_markdown(cleaned)`; atomic write only if changed; return
  `{ok:True, conflict:False, profile_hash:new_hash, previous_profile_hash:current_hash,
  written:..., old_total, new_total, sections_changed:[...]}`.

No new imports needed (`_render_markdown`, `_sanitize_bullets`, `profile_hash`,
`_parse_markdown`, `SECTIONS` all in-module).

**Tests:** `tests/unit/memory/profile_test.py` (extend; reuse `_store(tmp_path)`):
- write path renders canonical markdown (8 headers, placeholders for empty keys)
- hash conflict returns `conflict:True`, no write
- catastrophic-loss guard blocks >50% drop on a ≥4-bullet profile; `allow_shrink=True`
  bypasses; tiny-profile exemption (3→0 allowed)
- idempotent no-op (same content) returns `written:False`
- invalid section key raises `ValueError`

### Phase 2 — Tool: "all" mode on `manage_user_profile`

**File:** `twin/shared/tools/modules/profile/manage_profile_tool.py`

Schema change (`parameters_schema`, `:28-62`):
- `section` becomes optional (remove from `required`).
- Add `sections` param: `{"type":"object","additionalProperties":{"type":"array",
  "items":{"type":"string"}}, "description":"Map section→bullets cho chế độ toàn-file
  (bỏ trống 'section'). Chỉ chứa 8 section hợp lệ."}`.
- Add `allow_shrink` (boolean, default false, description in VN: cho phép rút gọn mạnh
  >50% bullet).
- `required` becomes `["user_id","expected_profile_hash","reason"]`. Mode is decided by
  presence of `section`.

`execute` (`:64-141`): branch on mode.
- **Section mode** (`section` present, in `SECTIONS`): unchanged path → `replace_section`.
- **All mode** (`section` omitted/empty): require `sections` is a dict; validate every
  key ∈ `SECTIONS` else VN error `Lỗi: section '<k>' không hợp lệ...`; sanitize each
  bullet with the existing per-bullet loop (`:93-104`) reused as a helper; call
  `replace_all(user_id, sections, expected_profile_hash, allow_shrink=allow_shrink)`.
- Result handling: `conflict` → existing VN conflict message; `shrink_blocked` → new VN
  message *"Lỗi: rewrite làm mất >50% bullet (<old_total> -> <new_total>). Nếu cố ý, đặt
  allow_shrink=true."*; success → VN summary *"Đã ghi toàn bộ hồ sơ user <id>:
  <old_total> -> <new_total> bullet. Hash mới: <hash>."*
- Validation error messages match existing Vietnamese style (`:78-91`).

Keep `visible_to/allowed_to={"evernight"}` in `system_tools.py` unchanged (tool stays
Evernight-only; auto-curation is a separate non-tool path).

**Update guide:** `twin/shared/tools/prompts/guides/manage_user_profile.md` — document the
two modes and `allow_shrink`. (Doc only; flagged, not blocking.)

**Tests:** `tests/unit/manage_profile_tool_test.py` (extend; reuse `Store` fake, add a
`replace_all` method to it):
- all-mode: `section` omitted → calls `replace_all` with the map; success message
- all-mode validation: unknown section key → VN error, store not called
- all-mode `shrink_blocked` result → VN shrink message
- section-mode regression: existing tests still pass unchanged

### Phase 3 — Curation pass: `ProfileCurator`

**New file:** `twin/shared/memory/profile/curator.py`

```python
class ProfileCurator:
    def __init__(self, profile_store, llm) -> None: ...
    async def curate(self, user_id: str) -> dict: ...   # never raises
```

`curate(user_id)`:
1. `text = await profile_store.read_raw(user_id)`; `current_hash = profile_hash(text)`.
2. **Idempotency/cost guards:** parse → `total = sum bullets`. Skip (return
   `{"status":"skip_trivial"}`) if `total < PROFILE_CURATION_MIN_BULLETS`. Read
   `_last_curated_hash(user_id)`; if `== current_hash` → skip
   (`{"status":"skip_unchanged"}`).
3. Render the 8-section snapshot (reuse `get_system_prompt_context` or
   `_render_markdown(parsed)`), send ONE `llm.generate_response(messages=[{user:
   snapshot}], system_prompt=SYSTEM_PROMPT, use_native_tools=False,
   max_tokens=PROFILE_CURATION_MAX_TOKENS)`. Parse `.content` → strict JSON. One retry
   with a `STRICT_JSON_SUFFIX` (copy Extractor's two-attempt loop, `extractor.py:194-229`).
   On parse failure → log warning, return `{"status":"parse_failed"}`, **do not write**.
4. Validate parsed `sections`: drop unknown keys, coerce to `{k: [str,...]}`.
5. `result = await profile_store.replace_all(user_id, sections, expected_profile_hash=
   current_hash)`. If `conflict` (profile changed mid-curate) → return
   `{"status":"conflict"}`, do not retry (next idle fires again). If `shrink_blocked` →
   return `{"status":"shrink_blocked"}` (do not pass `allow_shrink` from the auto path —
   a weak-model rewrite that wants to drop >50% is exactly what we distrust).
6. On success → write `_set_last_curated_hash(user_id, result["profile_hash"])`; return
   `{"status":"ok", ...}`.

Marker helpers `_last_curated_hash` / `_set_last_curated_hash` read/write
`memories/.curation/<sanitized_id>.hash` (reuse `_sanitize_user_id` logic — import or
re-derive; the dir is created lazily).

**Prompt (`SYSTEM_PROMPT`, inline VN, JSON contract):**
> Bạn là bộ biên tập hồ sơ người dùng. Đầu vào là hồ sơ T3 với 8 section cố định. Nhiệm
> vụ: gộp các bullet trùng/diễn đạt lại, bỏ thông tin lỗi thời/đã bị mâu thuẫn, GIỮ
> nguyên 8 section (không tạo section mới), không bịa thông tin mới. Trả về DUY NHẤT
> JSON: `{"sections": {"basic":[...], "contact":[...], ..., "rules":[...]}}`. Mỗi bullet
> là một dòng ngắn, không prefix "- ". Section không có gì thì trả mảng rỗng.

`STRICT_JSON_SUFFIX`: *"CHỈ trả JSON, không giải thích, không markdown fence."*

**Tests:** `tests/unit/memory/profile_curator_test.py` (new):
- skip when trivial (`< MIN_BULLETS`) — no LLM call
- skip when hash unchanged (seed marker) — no LLM call
- happy path: fake LLM returns deduped JSON → `replace_all` called, marker updated
- parse failure → no write, status `parse_failed`
- conflict path: store returns conflict → no marker write
- never raises on LLM exception

### Phase 4 — Scheduler + wiring

**New file:** `twin/shared/memory/profile/curation_scheduler.py` — copy
`CleanupScheduler` verbatim (`cleanup_scheduler.py`), rename class
`ProfileCurationScheduler`, default `debounce_seconds=PROFILE_CURATION_IDLE_SECONDS`,
swap log prefixes to `T3:curation_scheduler`, and simplify the report-summary block in
`_run_now` (curate returns a dict — log `status` when not a skip). Keep `flush()` and
`close()` for tests + shutdown.

**Wire in `twin/shared/agent/runtime.py`** (`build_shared_agent_runtime`, near
`:82-108`):
```python
curator = ProfileCurator(profile_store, llm_service)
curation_scheduler = ProfileCurationScheduler(curator.curate)
```
Add `curation_scheduler` to `SharedAgentRuntime` dataclass (`:38-50`) and close it in
`close()` (`:52-60`, before/with `cleanup_scheduler`). Pass the scheduler's `schedule`
into the memory manager:
```python
memory_manager = SharedMemoryManager(
    active=active, profile_store=profile_store, timeline_search=timeline_search,
    consolidator=consolidator, curation_scheduler=curation_scheduler.schedule,
)
```

**`twin/shared/memory/manager.py`:**
- `__init__` gains `curation_scheduler: Callable[[str], None] | None = None`
  (`manager.py:21-33`), stored as `self.curation_scheduler`.
- In `observe_user_message` (`:40-48`): after `t1.observe`, if `role != "assistant"` and
  `self.curation_scheduler is not None`: `self.curation_scheduler(str(user_id))`.
- In `observe_channel_message` (`:81-102`): after `t1.observe`, if
  `self.curation_scheduler is not None`: `self.curation_scheduler(str(author_id))`
  (channel turns are always user turns; key on the speaking participant).
- The bot path `add_assistant_message` (`:50-79`) never schedules.
- `schedule()` is a cheap sync fire-and-forget (creates/cancels one asyncio task); doing
  it per user-message is fine (same cost profile as the existing cleanup debounce).

**Containers:** `march7/container.py:58` and `evernight/container.py:58` already pull
fields off `self.runtime`; add `self.curation_scheduler = self.runtime.curation_scheduler`
for symmetry (optional — the scheduler is owned by the runtime and closed via
`runtime.close()`, so no extra start/stop wiring is needed; it's driven entirely by
`observe`). No `__main__.py` changes required.

**Tests:** `tests/unit/memory/profile_curation_scheduler_test.py` (new):
- `schedule` then `flush` runs the callable once (reuse `CleanupScheduler` test style)
- repeated `schedule` within window collapses to one run (debounce)
- distinct user ids schedule independently (channel fan-out: two authors → two runs)
- callable raising → scheduler swallows, no propagation
- `close()` cancels pending without firing

**Manager wiring tests:** `tests/unit/memory/manager_test.py` (extend):
- `observe_user_message` with `role="user"` calls the injected scheduler with the user id;
  `role="assistant"` does NOT
- `observe_channel_message` calls the scheduler with the speaking `author_id`

### Phase 5 — Constants + tests green

- `profile/constants.py`: add `PROFILE_CURATION_IDLE_SECONDS=1800`,
  `PROFILE_CURATION_MAX_TOKENS=4000`, `PROFILE_CURATION_MIN_BULLETS=4`, with a comment
  that idle must exceed `IDLE_TRIGGER_MINUTES*60`.
- Export `ProfileCurator`, `ProfileCurationScheduler` from
  `twin/shared/memory/profile/__init__.py` if other modules import them (runtime imports
  the modules directly, so export is optional — match existing `__init__` style).

---

## Test Plan

Run: `conda run -n discord_bot python -m pytest tests/unit/memory tests/unit/manage_profile_tool_test.py -q`

| Area | File | Cases |
|---|---|---|
| `replace_all` | `tests/unit/memory/profile_test.py` (extend) | write+canonical render, hash conflict, catastrophic-loss guard (block / allow_shrink / tiny-exempt), no-op, invalid key |
| tool all-mode | `tests/unit/manage_profile_tool_test.py` (extend) | section-omitted → `replace_all`; unknown-key VN error; `shrink_blocked` VN message; section-mode regression |
| curator | `tests/unit/memory/profile_curator_test.py` (new) | skip-trivial, skip-unchanged, happy dedup, parse_failed no-write, conflict no-marker, never-raises |
| scheduler | `tests/unit/memory/profile_curation_scheduler_test.py` (new) | debounce-collapse, flush-fires-once, swallow-exception, close-cancels |

Acceptance: all four areas pass + no regression in existing `profile_test.py`,
`cleanup_test.py`, `consolidator_test.py`, `manage_profile_tool_test.py`.

---

## Risks / edge cases

- **Hash rotation between append (consolidation) and curate.** Curation reads
  `current_hash` immediately before `replace_all` and passes it as `expected_profile_hash`.
  If a promotion `append_raw` lands between read and write, the hash is stale →
  `replace_all` returns `conflict`, no write, curation no-ops and the next idle re-fires.
  Safe by construction (same optimistic-concurrency contract as `replace_section`).
- **Concurrent curation vs live `update_user_profile` append.** Same hash guard: whoever
  writes second on a stale hash gets `conflict` and retries. The per-user `flock` in the
  store serializes the actual writes; the hash guard serializes intent. Auto-curation
  always defers (never `allow_shrink` from the auto path).
- **Weak-model bad rewrite.** Two layers: (1) canonical render — model only supplies
  bullet *content*, never structure or new sections; (2) catastrophic-loss guard blocks
  >50% drops on non-trivial profiles. Auto path never sets `allow_shrink`, so a
  destructive rewrite is rejected, not written.
- **Cost.** Idempotency marker skips unchanged profiles; trivial-floor skips near-empty
  ones; 30-min debounce collapses a whole conversation into at most one curation per
  idle gap. Expected steady-state: one LLM call per user per active session, only when
  the profile actually changed since last curate.
- **Process double-fire.** A user active in both March7 (DMs + all channels) and
  Evernight (its own DM/tag/`!9` chats) gets a debounce timer in each process. Both can
  fire, but the per-user `flock` + `expected_profile_hash` guard + last-curated-hash
  marker make the second curate a no-op (`skip_unchanged`). Safe, mildly redundant.
- **Both scopes curated (per user decision).** Auto-curation keys on the speaking
  author, so DM users (`observe_user_message`) and channel participants
  (`observe_channel_message`) are both covered. A *mentioned-but-silent* participant
  whose profile is filled by subject-routing but who never speaks gets no idle-stop
  event → not auto-curated; manual `manage_user_profile` covers that residual case.

---

## Assumptions a human must confirm

1. **Scope policy (DECIDED by user):** auto-curation covers **BOTH DM (user scope) and
   channel scope**, keyed on the speaking author. Channel participants who actually speak
   are curated; mentioned-but-silent participants are not (residual handled by the manual
   tool).
2. **Process placement:** scheduler lives in the **shared runtime**, fires in whichever
   process observed the user (March7 for DMs) — *not* Evernight-exclusive as the spec's
   prose assumed. This is the load-bearing correction; confirm it's acceptable that the
   curation LLM call runs in the March7 process for DMs (it has `llm_service` +
   `profile_store` via the same shared runtime).
3. **Marker storage:** last-curated hash as `memories/.curation/<id>.hash` file (vs
   Redis). Chosen for self-containment with the file-backed T3 store.
4. **Threshold:** 50% drop on ≥4-bullet profiles as the catastrophic-loss line; tiny
   profiles exempt. Confirm the fraction/floor.
5. **Idle window:** 30 min (`PROFILE_CURATION_IDLE_SECONDS=1800`), strictly > the 15-min
   consolidation idle.
6. **`replace_all` semantics:** the map is authoritative — a section absent from the map
   renders empty. The auto path always sends all 8 keys; the manual tool must too.
   Confirm this "absent = clear" rule (vs "absent = keep").

---

## Outcome (2026-06-12)

Implemented end-to-end across 4 phases (constants+store → tool all-mode → curator →
scheduler+wiring), **channel-inclusive** per user decision. **183 passed** in
`tests/unit/memory tests/unit/manage_profile_tool_test.py`.

**Shipped:**
- `replace_all` on `MarkdownProfileStore` — same lock+hash contract as `replace_section`,
  map-authoritative, catastrophic-loss guard (reject >50% drop on ≥4-bullet profile unless
  `allow_shrink`).
- `manage_user_profile` whole-file mode — `section` optional; omit it + pass `sections`
  map → rewrite all 8 sections in one call. Section mode unchanged. Tool stays
  Evernight-only.
- `ProfileCurator.curate()` — 1 LLM pass, never raises; statuses
  `ok/skip_trivial/skip_unchanged/parse_failed/conflict/shrink_blocked/write_rejected/error`;
  idempotency marker `memories/.curation/<id>.hash`; auto path never sets `allow_shrink`.
- `ProfileCurationScheduler` — per-user 30-min debounce (clone of `CleanupScheduler`),
  wired in `build_shared_agent_runtime`, scheduled from `SharedMemoryManager` on **both**
  `observe_user_message` (key=user_id, skip assistant turns) and `observe_channel_message`
  (key=author_id). Bot turns never schedule (verified: two `if message.author.bot: return`
  guards at the Discord adapter entry points block the bot from ever reaching the channel
  observe path).

**Decisions confirmed by user:** scope = both DM + channel (keyed on speaker); 30-min
idle; 50%/≥4-bullet shrink line; file marker; absent-section = clear.

**Review:** inline 5-dimension review (correctness / concurrency / channel-trigger /
robustness / tests) — no blocker/major. One honesty fix applied: a non-conflict
non-shrink `ok:False` from the store now reports `write_rejected` instead of the
misleading `parse_failed`.

**Deferred (not done, out of scope):** container-symmetry one-liners (dead assignments,
intentionally skipped); a mentioned-but-silent participant whose profile is filled by
subject-routing is not auto-curated (no idle-stop event) — manual tool covers it.
