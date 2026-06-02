# PROJECT_CONTEXT

Runtime and architecture context for March7. Keep this file focused on facts
agents must know before changing behavior; use CodeGraph for source structure.

## Runtime Modes

### Docker Compose (primary)

Use [../docker/docker-compose.yml](../docker/docker-compose.yml) and
[../docker/README.md](../docker/README.md) for the full system.

Main services:

- `redis`: Redis Stack for T1 active memory and T2 timeline/vector memory.
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

- `March7Container.initialize()` (shared T1/T2/T3 memory stack, tools, LLM)
- March7 A2A server on port 8000
- `InactivityTrigger` over `("user", "channel")` driving `ActiveSummaryPolicy.evaluate`
- Discord adapter via `ChatGateway`

`twin/march7/__main__.py` is a thinner CLI-style entry (no gateway / no
Discord) kept for local dev. Both mount the same `InactivityTrigger` so the
unified flow works in either mode.

## Architecture Boundaries

- `gateway/`: platform adapters and routing, currently focused on Discord. Routes public messages to March7 and handles communication.
- `twin/march7/`: conversational agent, chat/tool loop, A2A server on default port `8000`, and container wiring for the shared memory stack.
- `twin/evernight/`: background consolidation and self-heal agent. Includes its own Discord bot adapter (`EvernightDiscordAdapter` listening to DMs and `!9` prefix) with chat capability (`handle_chat`), A2A server on default port `8001`, and container wiring for the same shared memory stack.
- `twin/shared/`: shared A2A, LLM, tool, memory (`active`, `timeline`, `profile`), and transport code.

Evernight must access March7 session state through A2A skills such as
`get_snapshot` and `clear_session`; do not couple it directly to March7 Redis
keys unless the architecture explicitly changes.

## Current Implementation Status

Memory rewrite is implemented end-to-end as of 2026-05-28.

- **Shared stack**: `twin/shared/memory/` is the single implementation for both
  agents. Containers build `ActiveMemory`, `MarkdownProfileStore`,
  `TimelineStore`, `TimelineSearch`, `Consolidator`, `Cleanup`, and
  `CleanupScheduler`.
- **T1 scope-aware**: `ActiveEntry.scope` (`user`/`channel`), `scope_id`, plus
  `author_*`/`guild_id`/`channel_id`/`message_id`/`reply_to` metadata. Storage
  uses Redis JSON keys `active:{scope}:{scope_id}:{entry_id}` plus
  `active_state:*` and `active_index:*`.
- **Prompt context**: `SharedMemoryManager.get_context()` injects T3 profile
  context from `MarkdownProfileStore.get_system_prompt_context()` and T2
  pre-flight retrieval from `TimelineSearch.preflight()`.
- **Consolidation flow**: `ActiveMemory` threshold/idle calls
  `SharedMemoryManager.consolidate_scope()`. User scope consolidates directly;
  channel scope fans out per participant author id. Successful consolidation
  trims summarized T1 entries and schedules cleanup.
- **T2 timeline/vector**: `T2Memory` and `T2Topic` are stored as Redis JSON with
  RediSearch `VECTOR HNSW` indexes `idx:t2:mem` and `idx:t2:topic`.
- **Legacy removed**: old `twin/*/memories/`, `twin/shared/memories/`,
  `DiscussionConsolidator`, `consolidate_t2_memory`, and the old T2 page model
  were removed.

## Memory Tiers

- **T1 Active Memory**: short-term session context in Redis JSON, scoped as
  `user` or `channel`.
- **T2 Timeline Memory**: Redis Stack semantic/vector memory, used by both
  agents for pre-flight retrieval, search tool calls, consolidation, topic
  resolution, supersede chains, and cleanup.
- **T3 Core/Profile Memory**: Markdown files via `MarkdownProfileStore`, default
  base path `memories/`, rendered as 8 profile sections.

## Key Environment Groups

Shared infrastructure and LLM:

- `REDIS_URL`
- `TIMELINE_REDIS_DB` default `0` (required for RediSearch indexes)
- `CODEBOX_API_URL`
- `BASH_EXECUTOR_URL`
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
- `POLL_INTERVAL` default `60` (both InactivityTrigger instances honor this;
  the idle-summary threshold itself is the `IDLE_TRIGGER_MINUTES` constant, not
  an env var)
- `SELF_HEAL_ENABLED` default `true`

Discord/Gateway:

- `GATEWAY_ENABLED_PLATFORMS` default `discord`
- `DISCORD_GATEWAY_ENABLED` default `true`
- `DISCORD_MARCH7_TOKEN`
- `DISCORD_EVERNIGHT_TOKEN`

Do not print `.env` files or token values.
