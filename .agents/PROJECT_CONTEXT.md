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
- `system-gateway`: native host service that executes structured host actions
  and gates raw shell access (replaces the legacy `bash-executor`).
- `bash-executor`: **legacy** privileged host command execution; kept only for
  migration and will be removed once all host workflows use `system-gateway`.
- `march7`: Gateway, Discord bot, and March7 A2A server.
- `evernight`: Evernight bot, consolidation, and self-heal worker.

Expected local endpoints:

- March7 A2A: `http://localhost:8000/.well-known/agent.json`
- Evernight A2A: `http://localhost:8001/.well-known/agent.json`
- Codebox: port `8069`
- System Gateway: port `8380` (native host service)
- Bash Executor: port `8374` (legacy, do not use for new features)

### Local Python (secondary)

```bash
pip install -r requirements.txt
python -m gateway          # March7 in-process (Discord adapter + March7 A2A)
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
- Discord adapter via `ChatGateway`

`twin/march7/__main__.py` is a thinner CLI-style entry (no gateway / no
Discord) kept for local dev. Both modes support the unified flow.

## Architecture Boundaries

- `gateway/`: platform adapter orchestration and routing. Design intent:
  Discord, Zalo, and future surfaces are compatibility adapters that compile
  native events into unified gateway models, then send unified replies back to
  their native platform. Gateway core must not require native platform message
  objects.
- `twin/march7/`: conversational agent, chat/tool loop, A2A server on default port `8000`, and container wiring for the shared memory stack.
- `twin/evernight/`: background consolidation and self-heal agent. Includes its own Discord bot adapter (`EvernightDiscordAdapter` listening to DMs and `!9` prefix) with chat capability (`handle_chat`), A2A server on default port `8001`, and container wiring for the same shared memory stack.
- `twin/shared/`: shared A2A, LLM, tool, memory (`active`, `timeline`, `profile`), and transport code.

Evernight must access March7 session state through A2A skills such as
`get_snapshot` and `clear_session`; do not couple it directly to March7 Redis
keys unless the architecture explicitly changes.

### Tool Runtime Boundary

Declared logical tools have two backend kinds:

- `local`: direct `BaseTool` / `ToolRegistry` execution for in-process tools and
  app-owned services.
- `remote_mcp`: external MCP servers outside this app's trust boundary, called
  through `MCPClient` only when a real integration exists.

The prompt contract stays local: `ToolPromptCatalog`, local guide files, local
schema descriptions, visibility, and approval remain the model-facing source of
truth. Remote MCP `tools/list` metadata is untrusted data and must not be
rendered into the system prompt, lazy guide, or native tool schema descriptions.

Current classification: `web_search` is `remote_mcp` and calls Tavily's remote
MCP endpoint (`TAVILY_MCP_URL`, default `https://mcp.tavily.com/mcp`) with
`Authorization: Bearer <TAVILY_API_KEY>`. Its public name, schema, and guide
remain the local `web_search` contract; the adapter maps arguments to Tavily's
`tavily_search` MCP tool and trims results back to the local schema's requested
`max_results`. There is no legacy Tavily HTTP backend path. Memory/profile/
consolidation tools are internal stateful tools, `run_python_code` calls the
codebox sandbox, and `host_system` calls the native System Gateway. The
`execute_host_bash` tool is legacy and hidden from the catalog; do not use it
for new host interactions.

Future bot-created tools start as drafts and must not become visible or allowed
without validation and approval. Generated workflow tools should use the
`local` backend unless they proxy a real external MCP server. This phase does
not add a local MCP server process, generated tool runtime, workflow engine,
automatic remote `tools/list` import, or sampling support by default.

### System Gateway

The System Gateway is the host OS boundary for agent-issued actions.

- Native service package: `services/system_gateway/`
- Agent client: `twin.shared.system_gateway.HostGatewayClient`
- Model-facing tool: `host_system` (`twin/shared/tools/modules/system/host_system_tool.py`)
- Evernight admin/monitor: `twin/evernight/system_gateway/`

Key points:

- The service runs **on the host**, not inside a container, and listens on
  `127.0.0.1:8380` by default.
- Containers reach it via `SYSTEM_GATEWAY_URL` (e.g. `http://host.docker.internal:8380`).
- All mutating requests must be signed with HMAC-SHA256 using
  `SYSTEM_GATEWAY_SHARED_SECRET`.
- Mutating actions and raw shell also require an action-bound, actor-bound,
  single-use approval token minted by the owner approval path (Evernight or the
  owner CLI).
- Read-only structured actions (`system.status`, `system.disk_usage`,
  `docker.list_containers`, `docker.container_logs`, `service.status`) execute
  without a shell and with validated arguments.
- Raw shell is denied by default (`SYSTEM_GATEWAY_RAW_SHELL=false`).
- Evernight monitors health via `GatewayMonitor` and can request container
  restarts (`container.restart`) through the gateway with owner approval.
- First install requires a one-time owner-run bootstrap command generated by
  `system-gateway pair` and `system-gateway install`.

### Gateway Status

The gateway is partially refactored toward the platform-agnostic design:

- `gateway/__main__.py` imports `AgentRouter`, `EvernightClient`, and
  `GatewayChatHandler` from `gateway.core`.
- `GatewayChatHandler` accepts clean `UnifiedMessage` objects and uses neutral
  route hints from `msg.extensions` (`is_addressed`, `should_respond`,
  `respond_mode`, `conversation_id`, `space_id`, `assistant_*`).
- Discord adapter owns Discord admin-channel mode, mention/reply detection,
  typing indicator, approval context setup, and Discord send splitting/chunking.
- `ChatGateway.route_message()` owns generic outbound handoff again on the
  March7 production path.
- Shared approval flow stores `discord.Message` in context and imports Discord
  button views from shared tool code; this is still a known TODO.
- `gateway/adapters/factory.py` intentionally raises `NotImplementedError` for
  `zalo`; no Zalo SDK/adapter exists yet.

Before implementing platform features, follow
[plans/gateway-platform-abstraction.md](plans/gateway-platform-abstraction.md).

## Current Implementation Status

Memory rewrite is implemented end-to-end as of 2026-05-28, with a subsequent refactoring to the **A2A Consolidation** mechanism.

- **Shared stack**: `twin/shared/memory/` contains the core implementation components: `ActiveMemory`, `MarkdownProfileStore`, `TimelineSummaryStore`. 
- **T1 scope-aware**: `ActiveEntry.scope` (`user`/`channel`), `scope_id`, plus
  `author_*`/`guild_id`/`channel_id`/`message_id`/`reply_to` metadata. Storage
  uses Redis JSON keys `active:{scope}:{scope_id}:{entry_id}` plus
  `active_state:*` and `active_index:*`.
- **Prompt context**: `SharedMemoryManager.get_context()` injects T3 profile
  context from `MarkdownProfileStore.get_system_prompt_context()` and T2
  pre-flight retrieval from `TimelineSummaryStore.search()` (embed query → KNN vector search).
- **Consolidation flow (A2A)**: When thresholds are met (managed by Evernight's `InactivityTrigger`), March7 uses `ConsolidationClient` to send a consolidation task via A2A HTTP port 8001 to Evernight. Evernight then executes the `ConsolidateMemoryTool`, which summarizes directly from `ActiveMemory` and writes to `TimelineSummaryStore` / `MarkdownProfileStore` via a single LLM call (Summarizer prompt).
- **T2 timeline/vector**: `TimelineSummary` entries are stored as Redis HASH with
  RediSearch `VECTOR HNSW` index `timeline_summaries`. Replaces the old `T2Memory` + `T2Topic` JSON model and `idx:t2:mem` / `idx:t2:topic` indexes.
- **Legacy removed**: The old local Python pipeline mechanism—including `Extractor`, `PromotionGuard`, `CleanupScheduler`, `Curator`, `TopicResolver`, `Consolidator`, `DiscussionConsolidator`, the old T2 page model, `TimelineStore`, `TimelineSearch`, and `T2Memory`—have been completely removed. InactivityTrigger is also removed from March7's gateway, now exclusively managed by Evernight.

- **Hybrid Profile Consolidation (T2->T3)**: `MarkdownProfileStore.append_raw`
  dedups only on exact case-insensitive match, so paraphrased bullets accumulate.
  The profile is now merged directly during the A2A consolidation step via `ConsolidateMemoryTool` instead of relying on a separate `ProfileCurator` and `DebouncedScheduler`.
- **`manage_user_profile` tool modes**: The tool supports both a single-section mode (modifying one specific section with `bullets` list) and a whole-file mode (accepting a `sections` map of all sections, where unspecified sections are deleted). Both modes check `expected_profile_hash` to guard against conflicts. Whole-file mode also supports an `allow_shrink` flag (default false) to prevent LLM errors or accidental large deletions from shrinking the profile by >50%.
- **Agent loop (Think/Act)**: Chat/tool orchestration lives in `twin/shared/agent/agent_loop.py`. The loop is `Think(Decide) -> Think(Refine) -> Act -> ... -> Think(Decide)`. `Think` is the only LLM-facing stage and keeps the bot's persona by going through the existing LLM service prompt builder. `Act` is pure tool execution: it has no LLM access, loads no persona, and only calls `ToolRegistry.execute_tool`. `Think(Decide)` either answers the user directly or selects the next tool; `Think(Refine)` remains the mandatory selected-tool validation pass before execution. Refine cancellation/error and loop-limit exits ask a final `Think(Decide)` pass with native tools disabled; there is no separate Resolve stage. `BaseLLMService.generate_response` accepts `include_tool_catalog`; only `Think(Decide)` passes `True`, while `Think(Refine)` receives the selected-tool guide and no full catalog. Prerequisite routing is still supported: if the tool selected in pass 1 lacks required arguments, `Think(Refine)` may switch to a prerequisite tool (e.g. `get_profile` to obtain `expected_profile_hash` for `manage_user_profile`).

## Memory Tiers

- **T1 Active Memory**: short-term session context in Redis JSON, scoped as
  `user` or `channel`.
- **T2 Timeline Memory**: Redis Stack semantic/vector memory via `TimelineSummaryStore`, used by both agents for pre-flight retrieval and consolidation. Replaces the old `TimelineStore`/`TimelineSearch` stack.
- **T3 Core/Profile Memory**: Markdown files via `MarkdownProfileStore`, default base path `memories/`, rendered as 8 profile sections.

## Key Environment Groups

Shared infrastructure and LLM:

- `REDIS_URL`
- `TIMELINE_REDIS_DB` default `0` (required for RediSearch indexes)
- `CODEBOX_API_URL`
- `SYSTEM_GATEWAY_URL` default `http://host.docker.internal:8380`
- `SYSTEM_GATEWAY_SHARED_SECRET` HMAC secret shared with the native gateway
- `BASH_EXECUTOR_URL` legacy; prefer `SYSTEM_GATEWAY_URL`
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
- `EVERNIGHT_A2A_URL` default `http://evernight:8001` (March7 uses `ConsolidationClient` to reach Evernight's port 8001 for consolidation tasks)
- `POLL_INTERVAL` default `60` (Evernight's `InactivityTrigger` honors this;
  the idle-summary threshold itself is the `IDLE_TRIGGER_MINUTES` constant, not
  an env var)
- `SELF_HEAL_ENABLED` default `true`

Discord/Gateway:

- `GATEWAY_ENABLED_PLATFORMS` default `discord`
- `DISCORD_GATEWAY_ENABLED` default `true`
- `DISCORD_MARCH7_TOKEN`
- `DISCORD_EVERNIGHT_TOKEN`
- Zalo env placeholders currently exist (`ZALO_ACCESS_TOKEN`, `ZALO_APP_ID`,
  `ZALO_ENABLED`) but there is no working Zalo adapter package yet.

Do not print `.env` files or token values.
