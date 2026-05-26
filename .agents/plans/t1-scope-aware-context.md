---
status: done
created: 2026-05-26
---

# T1 Scope-Aware Context Loading

## Summary

T1 active memory already separates `scope="user"` (DM) from `scope="channel"`
(guild channel), but March7's chat pipeline still loads context and stores bot
replies in the **user** scope regardless of the originating channel. The result
is cross-scope contamination: prompts the same `user_id` sent in DM (or in
another channel) leak into the LLM prompt when that user posts in any channel,
and bot replies written in a channel are filed under the user scope, leaving
channel-scope history one-sided.

Fix: route T1 reads and writes by the scope the turn actually belongs to. In
channel turns, use channel scope for both `context_msgs` and the bot's reply.
In DM turns, keep using user scope as today. The string-blob
`channel_context` injection into the system prompt becomes redundant once the
real conversation history is the channel scope, so it goes away.

## Success Criteria

- A March7 channel turn loads `context_msgs` only from the channel scope of
  that channel, not from `("user", user_id)`.
- A March7 channel turn persists the bot reply (assistant message) into the
  channel scope of that channel.
- A March7 DM turn still loads and persists in user scope; behavior unchanged.
- LLM no longer hallucinates "what user just said" by pulling messages from a
  different scope. Verified by a regression unit test seeded with cross-scope
  entries.
- Evernight chat behavior (DM / `!9` only) is unchanged.
- `pytest tests/unit` stays green; new tests cover the scope routing.

## Key Changes

### 1. `MemoryManager.get_context` — read from the right scope

[twin/march7/memories/memory_manager.py:125-144](twin/march7/memories/memory_manager.py#L125-L144)

- When `channel_id` is provided → load `t1.storage.get_entries("channel", channel_id)`
  and pass through `context_builder.build_context` to become `context_msgs`.
- When `channel_id` is `None` → keep current behavior:
  `t1.get_context_for_llm(user_id)`.
- Drop the separate `channel_context` string return value and its sys_prompt
  injection in [twin/march7/agent.py:95-102](twin/march7/agent.py#L95-L102).
  The channel scope IS the conversation history; one source of truth.
- Signature becomes `get_context(user_id, current_query, channel_id=None) -> Tuple[str, List[Dict]]`.

### 2. `ContextBuilder.build_context` — speaker-aware for channel scope

[twin/march7/memories/activate_memory/management/context_builder.py](twin/march7/memories/activate_memory/management/context_builder.py)

Channel entries carry `author_name`; the LLM needs to disambiguate speakers in
a multi-participant transcript. Two adjustments inside the existing builder:

- For entries with `scope == "channel"` and `role == "user"`, prepend
  `author_name:` (or `user_id:` fallback) to `content` in the returned dict.
  Keep `role` as `"user"` so the LLM treats it as a turn from the human side.
- For entries with `scope == "channel"` and `role == "assistant"`, leave
  `content` as-is and pass `role="assistant"` — those are the bot's own past
  replies, no prefix needed.
- User-scope entries continue to map straight through (no prefix). Both DM and
  channel paths share the same builder; the format choice keys on
  `entry.scope`, not on a builder parameter.

### 3. Persist bot reply into the active scope

[twin/march7/agent.py:163-165](twin/march7/agent.py#L163-L165) currently calls
`self.memory.add_message(user_id, role="assistant", content=bot_response)`,
which always writes to user scope.

- Replace with a scope-aware save:
  - Channel turn (i.e., `channel_id` is set and the agent has guild/author
    info from the gateway) → write to channel scope as
    `observe_channel_message`-style entry with
    `role="assistant"`, `author_id=<bot id or "march7">`,
    `author_name=<bot display name or "March7">`, `guild_id`, `channel_id`,
    plus the existing content/token fields.
  - DM turn → existing `add_message` (user scope) is fine.
- Easiest path: extend `MemoryManager` with a single new method
  `add_assistant_message(user_id, content, *, channel_id=None, guild_id=None, bot_id=None, bot_name=None)`
  that dispatches by `channel_id` and is called from both March7 and Evernight
  paths. Keeps `add_message` available for tests / DM use.

### 4. Pass channel metadata down from the gateway

[gateway/adapters/discord/handler.py:87-103](gateway/adapters/discord/handler.py#L87-L103) already passes
`channel_id`. To save assistant entries with full metadata, also forward
`guild_id` and the bot's identity to `agent_router.route(...)`, then to
`March7Agent.handle_chat`. The agent forwards them to
`memory.add_assistant_message`.

- `AgentRouter.route` and `March7Agent.handle_chat` gain `guild_id`,
  `bot_id`, `bot_name` keyword args, all optional and defaulting to `None`.
- Evernight call path in `AgentRouter` is untouched.

### 5. Allow `role="assistant"` for channel entries in storage

[twin/march7/memories/activate_memory/activate_memory_service.py:61-92](twin/march7/memories/activate_memory/activate_memory_service.py#L61-L92)

Today `observe_channel_message` is shaped for inbound user messages. Add a
sibling method `observe_channel_reply(channel_id, guild_id, bot_id, bot_name, content, message_id=None)`
or extend the existing one with `role` and `message_id` optional params. The
`MemoryEntry` schema in
[models.py:14-41](twin/march7/memories/activate_memory/models.py#L14-L41) already
permits any `role: str`, so no schema migration is required.

### 6. Stop bot from becoming its own T2 participant

With bot replies now stored in channel scope as `author_id=<bot id>`, the
`SUMMARY_REQUESTED` payload will include the bot among the entries.
[discussion_consolidator.py:134-142](twin/shared/memories/discussion_consolidator.py#L134-L142)
gathers every distinct `author_id` into `participants`, and the multi-user
fan-out at [discussion_consolidator.py:80-85](twin/shared/memories/discussion_consolidator.py#L80-L85)
creates one T2 page per `active_participant`. Without a filter the bot ends
up with its own user-centric T2 page about its own replies — a real duplicate
of context that already lives inside the human participants' pages.

Fix in `DiscussionConsolidator`, not in the agent:

- Add a `bot_user_ids: set[str]` constructor param (sourced from the
  `EvernightContainer` / `March7Container` wiring — both bots' ids are known
  at startup, pass through to the shared consolidator).
- In `_participants_from_payload` and in the `active_participants` post-LLM
  block, drop any id present in `bot_user_ids` before fan-out.
- Keep bot lines in the **transcript** untouched — the LLM still needs them
  to understand "what the assistant told this user".
- Mode resolution: if filtering empties `active_participants`, fall back to
  `single_user` against the original `scope_id` when scope was `user`, or
  treat as `skipped` when scope was `channel` and only bot lines remain.

This is a small, additive change to a shared module; both agents benefit.

### 7. Drop `build_channel_context` injection

[twin/march7/agent.py:98-102](twin/march7/agent.py#L98-L102) currently builds a
`[Recent channel context]` block and prepends it to the system prompt. With
channel scope as the actual conversation history this is duplicate context
that wastes tokens.

- Remove the injection branch.
- Keep `twin/march7/memories/channel_context.py` for now (no callers after
  this change). Mark for cleanup in a follow-up only if unused —
  `architecture-docs` will catch it.

### 8. Data cleanup / migration

Existing T1 user-scope data in Redis (from before this fix) still contains the
contaminated entries. AGENT_RULES allows treating local T1 as disposable in
dev. The plan:

- For dev: instruct `thoughtful-coder` to `FLUSHDB` the March7 Redis DB
  (`MARCH7_REDIS_DB`, default `0`) after merging, or call
  `MemoryManager.clear_session(user_id)` for the affected user(s) ad-hoc.
- For prod: no automated migration; T3 profile memory (Markdown) is the
  durable layer and remains intact. A one-time `redis-cli -n 0 FLUSHDB` is
  the documented action — flag in PR description.

## Out of Scope

- Evernight chat path: it never receives `channel_id` (DM/!9 only). Leave
  `EvernightMemoryManager.get_context` and `EvernightAgent.handle_chat`
  signatures alone. They keep working unchanged.
- T2 / consolidation: scope-aware T2 already exists (channel ids in
  `source_refs`, `participants` TAG). No change needed.
- `SummaryPolicy` / `InactivityTrigger`: already scope-aware. No change.
- Cross-channel "did this user say something in another channel" awareness.
  If we want that later, it's an explicit T2 search, not a T1 leak.

## Test Plan

All new tests under `tests/unit/`. Existing tests must stay green.

1. **`tests/unit/t1_context_builder_test.py`** — extend
   - Add `test_context_builder_channel_scope_prefixes_user_messages_with_author`:
     channel-scope `MemoryEntry` with `role="user"`, `author_name="Hoà"`,
     `content="alo"` → output content is `"Hoà: alo"`.
   - Add `test_context_builder_channel_scope_keeps_assistant_messages_clean`:
     channel-scope `role="assistant"` → output content unchanged, role
     `"assistant"`.
   - Add `test_context_builder_user_scope_unchanged`: user-scope entries map
     straight through, no prefix (regression guard).

2. **`tests/unit/march7_handle_chat_scope_test.py`** — new
   - Fake `MemoryManager` capturing `get_context` and `add_assistant_message`
     calls; fake LLM returning a fixed string.
   - `test_handle_chat_in_channel_loads_channel_scope_only`: handle_chat with
     `channel_id="c1"` → `get_context` invoked with `channel_id="c1"`; loaded
     entries pulled from channel scope; user-scope T1 contains only
     pre-seeded DM data which must NOT appear in `context_msgs`.
   - `test_handle_chat_in_channel_saves_assistant_reply_to_channel_scope`:
     after handle_chat returns, the new entry in T1 is `scope="channel"`,
     `scope_id="c1"`, `role="assistant"`.
   - `test_handle_chat_in_dm_uses_user_scope`: handle_chat with
     `channel_id=None` → reads + writes user scope (regression guard).

3. **`tests/unit/t1_redis_stack_storage_test.py`** — no schema change, but
   add a sanity check that storing `role="assistant"` under
   `scope="channel"` round-trips cleanly. Reuse the existing `FakeRedis`
   fixture; small addition.

4. **`tests/gateway/test_gateway.py`** — if the existing gateway tests touch
   `DiscordGatewayHandler.handle_message`, extend (or add a sibling test) to
   confirm `channel_id`, `guild_id`, and bot identity are forwarded to the
   router. If they don't exercise this path, leave alone — covered by the
   unit handle_chat test.

5. **`tests/unit/discussion_consolidator_test.py`** — extend
   - `test_consolidate_filters_bot_id_from_participants`: payload with mixed
     human + bot author_ids → bot id is dropped from `active_participants`;
     no T2 page is embedded for the bot id.
   - `test_consolidate_skips_when_only_bot_speaks`: channel payload with
     only bot entries → `status="skipped"`, no pages embedded.
   - Existing tests stay green: bot filter is additive.

Run:

```bash
pytest tests/unit -v
pytest tests/gateway -v
python -m compileall twin gateway
```

Manual verification on the running stack:

- DM to March7: confirm context still continuous.
- Send in a channel where mode is `OBSERVE_ONLY`, then `@mention` once — bot
  reply must reflect only what was said in that channel, not DM history.
- Send the same user a question in DM after a channel reply — DM history
  must not contain the channel turns.

## Assumptions / Defaults

- The agent always knows its own Discord identity (`bot.user.id` /
  `bot.user.display_name`) at the moment of replying. Confirmed via
  [gateway/adapters/discord/handler.py:35](gateway/adapters/discord/handler.py#L35)
  and the `set_bot` classmethod. If unavailable for any reason, fall back to
  `bot_id="march7"`, `bot_name="March7"` to keep the entry well-formed.
- Channel-scope `MemoryEntry.role` will be `"user"` for inbound and
  `"assistant"` for the bot's own reply. No new enum needed.
- Channel-scope `context_builder` output for user messages is
  `{"role": "user", "content": f"{author_name}: {content}"}`. If the LLM
  provider needs a different multi-speaker convention later, change in the
  builder only.
- Local Redis T1 will be flushed in dev after this change. Production rollout
  needs a one-line `redis-cli -n 0 FLUSHDB` in the deploy notes — no code
  migration shipped.
- `build_channel_context` helper stays on disk (orphan) until a docs/cleanup
  pass; not deleting it now keeps the diff focused.
- Evernight's `MemoryManager.get_context` signature stays
  `(user_id, current_query)`. No `channel_id` parameter added — keeps the
  A2A boundary clean.
- Token thresholds (`MAX_WORKING_TOKENS=2000`,
  `CHANNEL_SUMMARY_TOKEN_LIMIT=2000`) and idle (`SUMMARY_IDLE_MINUTES=30`,
  `SUMMARY_MIN_MESSAGES=30`) stay unchanged. With bot replies now also
  counting toward the channel scope's `unsummarized_token_count`, the cap
  fills modestly faster, but staying inside 2000 tokens for the LLM window
  is the goal — no retuning planned. If channel consolidation fires too
  often in practice, bump `CHANNEL_SUMMARY_TOKEN_LIMIT` in a follow-up
  rather than as part of this change.
- Bot user ids passed to `DiscussionConsolidator` are sourced from the
  active Discord clients at container init. If a bot id is missing (e.g.,
  in a unit test fixture), the filter is a no-op and existing behavior is
  preserved.
