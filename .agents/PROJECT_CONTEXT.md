# PROJECT_CONTEXT

Runtime and architecture context for March7. Keep this file focused on facts
agents must know before changing behavior; use CodeGraph for source structure.

## Runtime Modes

### Docker Compose (primary)

Use [../docker/docker-compose.yml](../docker/docker-compose.yml) and
[../docker/README.md](../docker/README.md) for the full system.

Main services:

- `redis`: Redis Stack for T1 coordination/storage and T2 semantic memory.
- `codebox`: sandboxed Python execution service.
- `bash-executor`: privileged host command execution with approval/audit.
- `march7`: Gateway, Discord bot, and March7 A2A server.
- `evernight`: Evernight bot, consolidation, and self-heal worker.

Expected local endpoints:

- March7 A2A: `http://localhost:8000/.well-known/agent.json`
- Evernight A2A: `http://localhost:8001/.well-known/agent.json`
- Codebox: port `8069`
- Bash Executor: port `8374`

### Local Python (secondary)

```bash
pip install -r requirements.txt
python -m gateway          # March7 in-process (Discord adapter + March7 A2A + InactivityTrigger)
python -m twin.evernight   # Evernight (A2A + DM bot + InactivityTrigger + self-heal)
python -m twin.march7      # Standalone March7 A2A only — local dev fallback, no Discord
```

Integration and e2e flows usually still need Redis, preferably provisioned by
Docker.

**Entry points — important.** The March7 container's Docker `CMD` is
`python -m gateway`, so `gateway/__main__.py` is the production entry that
owns:

- `March7Container.initialize()` (T1/T3, SummaryPolicy, EvernightClient)
- March7 A2A server on port 8000
- `InactivityTrigger` over `("user", "channel")` driving `SummaryPolicy.evaluate`
- Discord adapter via `ChatGateway`

`twin/march7/__main__.py` is a thinner CLI-style entry (no gateway / no
Discord) kept for local dev. Both mount the same `InactivityTrigger` so the
unified flow works in either mode.

## Architecture Boundaries

- `gateway/`: platform adapters and routing, currently focused on Discord. Routes public messages to March7 and handles communication.
- `twin/march7/`: conversational agent, chat/tool loop, T1 active memory (via `activate_memory`), T2 semantic memory (read-only search capability), T3 profile memory, A2A server on default port `8000`.
- `twin/evernight/`: background consolidation and self-heal agent. Includes its own Discord bot adapter (`EvernightDiscordAdapter` listening to DMs and `!9` prefix) with chat capability (`handle_chat`), and A2A server on default port `8001`.
- `twin/shared/`: shared A2A, LLM, tool, memory (including T2 memory store/search), and transport code.

Evernight must access March7 session state through A2A skills such as
`get_snapshot` and `clear_session`; do not couple it directly to March7 Redis
keys unless the architecture explicitly changes.

## Current Implementation Status

Unified discussion memory is implemented end-to-end as of 2026-05-25.

- **T1 scope-aware**: `MemoryEntry.scope` (`user`/`channel`), `scope_id`, plus
  `author_*`/`guild_id`/`channel_id`/`message_id`/`reply_to` metadata. Storage
  keys are `active_memory:{scope}:{scope_id}` across `RamStorage`,
  `RedisStorage`, and `RedisStackStorage`. Both March7 and Evernight T1 share
  the same schema (Evernight uses it for DM / `!9` chat).
- **Gateway split**: `should_observe` (DM | mention | reply-to-bot | observe
  channel) and `should_respond` (DM | mention | reply-to-bot | respond
  channel). `AdminChannels` cog stores per-channel `ChannelMode`
  (`observe`/`respond`).
- **Channel prompt context**: `build_channel_context` injects recent channel
  transcript with `author_name` when the bot is invoked in a channel.
- **Unified summary flow**: `SummaryPolicy.evaluate` fires
  `SUMMARY_REQUESTED` on token / message_count / idle thresholds.
  `MemoryManager` routes the event to Evernight via the A2A skill
  `consolidate_discussion` (`EvernightClient.request_consolidation`), then
  emits `SUMMARY_COMPLETED` / `SUMMARY_FAILED` locally. `cleanup_summarized`
  trims raw T1 entries after success while keeping the most recent few.
- **T2 user-centric fan-out**: `DiscussionConsolidator` lives in
  `twin/shared/memories/discussion_consolidator.py`. For each
  `active_participant` the LLM returns, it generates a deterministic
  `T2Page` (per real user_id) and merges with existing pages. Channel ids
  stay in `source_refs`. Page schema also includes `participants` (TAG
  indexed for future joint filters).
- **InactivityTrigger**: rewritten to poll `SummaryStateRepository.list_active`
  and call `SummaryPolicy.evaluate` per scope. Each agent runs its own
  instance in-process — March7 scans `("user", "channel")`, Evernight scans
  `("user",)`. The legacy snapshot-based path was removed.
- **Legacy removed**: `TOKEN_LIMIT_REACHED` event, `_handle_memory_overflow`,
  `ActiveMemoryService.force_cleanup`, the `else` fallback in
  `observe_user_message`, and the `overflow_queue` parameter of
  `MemoryManager` are gone. `MemoryJobQueue` and `MemoryWorker` still exist
  as backwards-compat consumers for any external tooling that pushes jobs
  directly to the legacy queue.

## Memory Tiers

- **T1 Active Memory**: short-term session context in Redis. `redis_stack` is
  the default stable path (set via `T1_STORAGE_PHASE` in settings); `legacy`
  Redis/HASH is the fallback. Keys are now scoped as
  `active_memory:{scope}:{scope_id}` for hash storage and equivalent
  `scope/scope_id` JSON fields for Redis Stack storage.
- **T2 Episodic/Wiki Memory**: Redis Stack semantic/vector memory, used by
  March7 for search queries and Evernight for consolidation. T2 remains
  user-centric; channel ids belong in `source_refs`, not `T2Page.user_id`.
- **T3 Core/Profile Memory**: Markdown files via `MarkdownStorage`, default
  base path `memories/`.

## Key Environment Groups

Shared infrastructure and LLM:

- `REDIS_URL`
- `CODEBOX_API_URL`
- `BASH_EXECUTOR_URL`
- `T1_STORAGE_PHASE`
- `T1_CONTEXT_MAX_TOKENS`
- `T1_CONTEXT_MAX_MESSAGES`
- `LLM_PROVIDER` and provider-specific chat/embedding variables

March7:

- `MARCH7_A2A_PORT` default `8000`
- `MARCH7_REDIS_DB` default `0`
- `MARCH7_PERSONA_PATH` default `twin/march7/personas`

Evernight:

- `EVERNIGHT_A2A_PORT` default `8001`
- `EVERNIGHT_REDIS_DB` default `1`
- `EVERNIGHT_PERSONA_PATH` default `twin/evernight/personas`
- `MARCH7_URL` default `http://march7:8000`
- `EVERNIGHT_A2A_URL` default `http://evernight:8001` (March7 reads this to
  reach Evernight's `consolidate_discussion` skill)
- `INACTIVITY_SECONDS` default `1800`
- `POLL_INTERVAL` default `60` (both InactivityTrigger instances honor this)
- `SELF_HEAL_ENABLED` default `true`

Discord/Gateway:

- `GATEWAY_ENABLED_PLATFORMS` default `discord`
- `DISCORD_GATEWAY_ENABLED` default `true`
- `DISCORD_MARCH7_TOKEN`
- `DISCORD_EVERNIGHT_TOKEN`

Do not print `.env` files or token values.
