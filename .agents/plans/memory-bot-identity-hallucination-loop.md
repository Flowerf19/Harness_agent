---
status: done
created: 2026-06-10
---

# Fix: bot-sourced identity hallucination loop in the T2 memory pipeline

## Summary

### Root cause (confirmed live + against code)

The memory pipeline treats the **bot's own utterances** as authoritative evidence of the
**user's** identity. The extractor mints `CandidateMemory` rows with
`speaker="bot"` + `catalogs=["identity"]` (e.g. "Flowerf có tên là Quang") from `Bot:`
transcript lines. The consolidator writes those to T2 unconditionally and — because
`identity` is in `T3_PROMOTABLE` and these land at high importance/confidence —
**auto-promotes them to T3**. T3 is injected into every prompt and re-fed to the extractor
(`t3_snapshot`), so the false name is re-extracted and reinforced each cycle: a
self-reinforcing loop. Redis forensics for user `726302130318868500` (real name Hòa):
24 `identity` memories, **21 `speaker="bot"`**, 1 `speaker="user"`; T3 had 18 duplicate
"Quang" bullets; the true name was never stored. A full data wipe cleared the symptom but
the minting code is unchanged, so the loop can rebuild.

**Defect in one line:** a bot's claim about a user's name/contact is not evidence — those
facts must originate from the user (`speaker in {"user","joint"}`).

`speaker` semantics confirmed: `CandidateMemory.speaker: Literal["user","bot","joint"]`
(extractor.py:104) is the **source/author** of the asserted information; the prompt defines it
as `"user" / "bot" / "joint" (cả 2 đóng góp)` (extractor.py:73). It is carried verbatim into
`T2Memory.speaker` (models.py:117) by the consolidator at consolidator.py:327. So
`speaker="bot"` means the fact came out of the bot's mouth — exactly the rows we must reject
for `identity`/`contact`.

### Line-number corrections vs the brief

The brief's cited symbols are all correct. Precise current line numbers (verified):

| Item | Brief said | Actual (verified) |
|---|---|---|
| `CandidateMemory` model | extractor.py (model) | extractor.py:96 (`speaker` at :104) |
| `SYSTEM_PROMPT` | extractor.py | extractor.py:54–87 (`speaker` rule at :73) |
| consolidator routing loop | — | consolidator.py:196–214 |
| `_process_candidate` (T2 write) | writes T2 via store | consolidator.py:286; `T2Memory` built :321–332; `upsert_memory` :333 |
| T3 auto-promote block | gated by importance/confidence/`T3_PROMOTABLE` | consolidator.py:354–381 |
| existing dropped-candidate aggregate WARNING | "added recently" | consolidator.py:209–214 (per-drop INFO at :201–206) |
| `CATALOGS` (12) | models.py | models.py:16–20 ✓ |
| `T3_PROMOTABLE` (8) | models.py | models.py:24–27 ✓ |
| `CATALOG_TO_T3` | models.py | models.py:29–38 ✓ |
| `T2Memory.speaker` | models.py | models.py:117 ✓ |
| `T3_PROMOTE_MIN_IMPORTANCE=4`, `..._CONFIDENCE=0.8` | constants.py | constants.py:20–21 ✓ |

No corrections needed beyond pinning exact lines.

### Design

Two deterministic code guards in the consolidator (the LLM filter is the *guarantee*; the
prompt nudge is at most a soft assist). Scope is strictly `{"identity","contact"}` — the only
catalogs that assert facts only the user can author.

1. **Storage drop (primary fix).** Before writing T2, reject any candidate whose catalogs
   intersect `{"identity","contact"}` AND `speaker == "bot"`. Drop entirely (do not down-rank)
   so it never pollutes semantic recall (`search_memory` KNN over T2) nor T3. Implemented in
   the routing loop (consolidator.py:196–214) so it folds into the **existing aggregate
   dropped-candidate WARNING** at :209–214 and reuses the per-drop INFO style at :201–206.

2. **Belt-and-suspenders T3 gate.** In the promotion block (consolidator.py:354–381), never
   promote an `identity`/`contact` catalog to T3 unless `cand.speaker in {"user","joint"}` —
   even if a row somehow reaches `_process_candidate`. Cheap, per-catalog, no new state.

3. **Scope discipline.** Guard fires ONLY for `identity` and `contact`. Justification against
   the taxonomy (models.py:16–27): `identity` and `contact` are assertions only the *subject*
   can author (their name, phone, handle). The other six `T3_PROMOTABLE` catalogs —
   `relationship`, `work`, `interest`, `habit`, `psychological`, `rules` — plus the four
   T2-only catalogs (`decision`, `event`, `emotion`, `discussion`) can be **legitimately
   inferred by the bot from the user's behavior** ("seems stressed about work"), so
   bot-sourced rows in those catalogs stay. Blocking them would lose real signal.

A shared module-level constant `_SPEAKER_GATED_CATALOGS = frozenset({"identity", "contact"})`
in consolidator.py keeps storage-drop and T3-gate scopes identical and self-documenting.

### Human decisions needed

- **Block `contact` as well as `identity`?** Recommended **yes** — same logic (a bot stating a
  user's phone/handle is not evidence). Low risk: bot-authored contact facts are nonsensical.
  Plan blocks both. Flag if product wants identity-only.
- **Extractor prompt nudge?** Recommended **skip for now.** The deterministic filter is the
  guarantee; local/reasoning models are unreliable at honoring such negatives, and the prompt
  is already dense (extractor.py:54–87). A one-line nudge is cheap but unverifiable and risks
  prompt drift. Listed as optional task P-opt; default = not implemented.

## Key Changes

All edits in `twin/shared/memory/timeline/consolidator.py`. No model/constant/schema changes.
Non-fatal to the chat path (consolidation is Pass 1, async, already `never raises`).

### Edit 1 — module-level scope constant (after imports, ~consolidator.py:33)

Add:
```python
# Facts only the SUBJECT can author. A bot uttering these about a user is not
# evidence (it caused the identity-hallucination loop), so bot-sourced rows in
# these catalogs are dropped before T2 and never promoted to T3.
_SPEAKER_GATED_CATALOGS = frozenset({"identity", "contact"})
```

### Edit 2 — storage drop in the routing loop (consolidator.py:196–214)

In the `for cand in extract_result.memories:` loop, after computing `target_id` and the
existing bot/unmatched-subject drop (the `if target_id is None:` branch at :200–206), add a
second guard before `routed.append(...)`:
```python
if cand.speaker == "bot" and (
    set(cand.catalogs or []) & _SPEAKER_GATED_CATALOGS
):
    self.logger.info(
        "T2:consolidator: drop bot-sourced identity/contact "
        "catalogs=%r subject_user_id=%r scope=%s/%s",
        cand.catalogs, cand.subject_user_id, scope, scope_id,
    )
    continue
```
The existing `dropped = len(extract_result.memories) - len(routed)` at :209 already counts any
`continue`d candidate, so the aggregate WARNING at :211–214 reports these too — no change to
the aggregate line. (Note the aggregate message text says "bot/unmatched subject"; consider
broadening to "bot/unmatched/policy" — optional, cosmetic.)

Rationale for placing the guard *after* the subject-routing drop: keeps both drops in one loop,
both counted by the one aggregate WARNING, and matches the existing per-drop INFO pattern.
Catalog list is read from `cand.catalogs` (already cleaned/validated by the extractor at
extractor.py:232–248; consolidator caps again at :319).

### Edit 3 — T3 promote gate (consolidator.py:354–381)

In the promotion `for cat in catalogs:` loop, after `if cat not in T3_PROMOTABLE: continue`
(:361–362), add:
```python
if cat in _SPEAKER_GATED_CATALOGS and cand.speaker not in ("user", "joint"):
    self.logger.info(
        "T2:consolidator: refuse T3 promote of bot-sourced %s "
        "(speaker=%s) user=%s", cat, cand.speaker, user_id,
    )
    continue
```
This is unreachable for bot-sourced identity/contact once Edit 2 lands (the row is dropped
before `_process_candidate`), but is the explicit belt-and-suspenders the brief requires and
guards any future caller of `_process_candidate`.

## Test Plan

File: `tests/unit/memory/consolidator_test.py`. Reuse existing fakes (`_build`, `_cand`,
`_entry`, `appender_recorder`). Run:
`conda run -n discord_bot python -m pytest tests/unit/memory -q`

1. **(a) bot-sourced identity dropped, not written to T2** —
   `test_consolidate_drops_bot_sourced_identity`: `_build` with one `_cand(catalogs=["identity"],
   speaker="bot", importance=5, confidence=0.9)`, scope=user. Assert `store.memories == {}`,
   `res.memory_ids == []`, `res.status == "skipped"` (all candidates dropped → existing 0-routable
   path at :216–223 yields skipped + flushed T1). Parametrize catalog over `["identity","contact"]`.

2. **(a') bot-sourced identity drop logged** —
   `caplog.at_level("INFO"/"WARNING", logger="twin.shared.memory.timeline.consolidator")`;
   assert an INFO record contains `"drop bot-sourced identity/contact"` and the aggregate WARNING
   with `"dropped"` fires (mirrors existing `test_consolidate_dropped_candidates_logged`).

3. **(b) user-sourced identity kept AND promoted to T3** —
   `test_consolidate_keeps_and_promotes_user_identity`: `_cand(content="Tên người dùng là Hòa.",
   catalogs=["identity"], speaker="user", importance=5, confidence=0.9)` with `appender_recorder`.
   Assert `status=="ok"`, one memory in `store.memories`, `len(recorder)==1`, `recorder[0][1]=="basic"`,
   `len(res.promoted_to_t3)==1`. (Extends existing `test_consolidate_promotes_to_t3_when_eligible`,
   which already uses `speaker="user"` via `_cand` default — confirm it still passes unchanged.)
   Add a `speaker="joint"` variant asserting it is likewise kept + promoted.

4. **(c) scope guard — bot-sourced relationship/interest NOT dropped** —
   `test_consolidate_keeps_bot_sourced_inferred_catalogs`, parametrize catalog over
   `["relationship","work","interest","habit","psychological"]`: `_cand(catalogs=[catalog],
   speaker="bot", importance=3, confidence=0.7)`, scope=user. Assert `status=="ok"`, exactly one
   memory written, its `speaker=="bot"`. Confirms the guard is identity/contact-only.

5. **(d) T3 gate rejects bot-sourced identity even if reached** —
   `test_promote_gate_blocks_bot_identity`: call `_process_candidate` directly on a constructed
   `Consolidator` (build via `_build`, reach `cons._process_candidate`) with a
   `CandidateMemory(catalogs=["identity"], speaker="bot", importance=5, confidence=0.9)` and a
   `ConsolidationResult`. Assert the appender recorder stays empty and `result.promoted_to_t3 == []`,
   while the T2 memory IS written (proving the gate is independent of Edit 2's storage drop).

No changes expected to extractor tests. If the optional prompt nudge (P-opt) is implemented, add
`test_extract_prompt_warns_against_bot_identity` asserting the SYSTEM_PROMPT mentions not
extracting identity/contact about a user from `Bot:` lines.

### Acceptance criteria

- All four behaviors (a–d) covered and green; full `tests/unit/memory` suite passes.
- Existing consolidator/extractor tests unchanged and still green (the `_cand` default
  `speaker="user"` means current promote tests are unaffected).
- No new bot-sourced `identity`/`contact` row can be written to T2 or promoted to T3.

## Risks / edge cases

- **`speaker="joint"`** (user + bot both contributed): treated as user-authored → kept and
  promotable. Correct: the user participated in asserting it. Covered in test (b) variant.
- **Multi-catalog candidate** (`MAX_CATALOGS_PER_MEMORY=2`), e.g. `["identity","interest"]` +
  `speaker="bot"`: Edit 2 drops the *whole* candidate (any intersection with the gated set).
  Acceptable — these are atomic single-fact memories (extractor mints 1–3 sentences each); a
  genuine bot-inferred interest would not be co-tagged `identity`. Documented; no per-catalog
  splitting (would be speculative).
- **Legacy poisoned rows already in Redis**: out of scope (a wipe already cleared them); this
  fix only prevents re-minting. If re-poisoning is suspected later, a one-off cleanup script is a
  separate task.
- **Aggregate WARNING message wording** still says "bot/unmatched subject"; policy drops now also
  count toward it. Cosmetic only; optional to broaden the string.
- **Non-fatal guarantee preserved**: both edits are pure `continue`/skip inside the existing
  try-wrapped `consolidate`; no new exceptions, no chat-path impact.

## Assumptions

- `cand.catalogs` is populated and validated by the time the routing loop runs (true: extractor
  filters to `CATALOG_SET` at extractor.py:234 and the consolidator caps at :319). The guard reads
  `cand.catalogs` (pre-cap) which is a safe superset for the membership test.
- Blocking `contact` alongside `identity` is desired (default; see Human decisions).
- The extractor prompt nudge is NOT implemented in this pass (default; see Human decisions).
