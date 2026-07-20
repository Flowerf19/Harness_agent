# AGENT_RULES

Rules for coding agents working in this repository.

## Safety

- Do not reveal secrets. Never print full `.env` files, Discord tokens, API
  keys, or URLs containing credentials.
- **System Gateway is the host boundary.** Use `host_system` for new host
  interactions. Do not add direct host shell calls from containers.
- **System Gateway invariants:**
  - Mutating requests must carry a valid HMAC-SHA256 signature from
    `SYSTEM_GATEWAY_SHARED_SECRET`.
  - Mutating actions and raw shell require an action-bound, actor-bound,
    single-use approval token. Bare approval IDs or unconsumed tokens are not
    enough.
  - Never bypass the gateway by having Evernight or March7 execute host
    commands through Redis, Docker socket, or any other side channel.
  - `SYSTEM_GATEWAY_RAW_SHELL` is an emergency kill switch and defaults to
    `true` in the native service; even when enabled, raw shell still requires
    owner approval.
  - Do not log the shared secret or approval tokens.
- Keep the March7/Evernight A2A boundary intact. Evernight must not read or
  clear March7 T1 state by direct Redis key access.
- Keep the gateway/platform boundary intact. Discord, Zalo, and future chat
  surfaces are adapters only; core gateway handlers, agents, shared memory, and
  shared tools must not require `discord.Message`, Discord views, Discord
  logger names, or Discord-only prompt labels.

## Working Style

- **Use CodeGraph first** for structural questions (definitions, signatures, callers, callees, impact, and feature context).
- **NEVER re-read code files** with native read/grep for exploration once `codegraph` tools (`codegraph_explore`, `codegraph_node`) have already returned the symbol/source. Native read/search is only for confirming specifics CodeGraph didn't cover, or for inspecting config/docs/manifests.
- **Plan before coding.** For any non-trivial feature/bug, produce a plan (via the `implementation-planner` skill) and get user approval before editing code. The plan is part of the conversation — do not write it into an external app-data directory.
- Make small, task-scoped changes. Avoid broad refactors, speculative abstractions, unrelated formatting, and new tooling unless requested.
- If a change affects runtime flow, env vars, Docker, memory schema, or public
  behavior, update relevant docs in this folder and project READMEs.
- If touching `gateway/`, first check the current gateway status in
  [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) and
  [../ARCHITECTURE.md](../ARCHITECTURE.md). Keep Discord SDK concerns in
  `gateway.adapters.discord`; do not add new dependencies from
  `twin/shared/*`, `twin/march7/*`, or gateway core files back into that adapter
  layer.

## Skills

Curated skills live globally at `~/.claude/skills/` (clone of [Flowerf19/agents-skills](https://github.com/Flowerf19/agents-skills)) — applies to all agents in every project, not just this repo.

- **Claude Code** auto-discovers them at `~/.claude/skills/`. Invoke with `/<skill-name>` or via the Skill tool.
- **Other agents** (Antigravity, Gemini, Cursor, generic LLMs): point them at `~/.claude/skills/<name>/SKILL.md`.

Available: `implementation-planner` (plan before code), `thoughtful-coder` (surgical changes), `debug-investigator` (root cause before any fix), `code-reviewer` (independent review before merge), `architecture-docs` (refresh `.agents/`), `create-readme` (root README from evidence).

Update upstream: `cd ~/.claude/skills && git pull`.

## Python Conventions

- Prefer clear async I/O with explicit timeouts for HTTP, Discord, Redis, and
  LLM calls.
- Handle cancellation and clean shutdown for background tasks.
- Use type hints on public functions and methods. Prefer `str | None` over
  `Optional[str]` for new Python 3.10+ code.
- Log enough context to debug, but never log secrets.
- Add retry/backoff only for concrete transient failure modes.

## Verification And PR Hygiene

- Choose focused tests from [TESTING_GUIDE.md](TESTING_GUIDE.md).
- For external I/O changes, verify timeout/error paths where practical.
- PR summaries should include context, change list, and exact verification.
- Commit messages should be short and specific, preferably
  `type(scope): message`.

## Verified Gotchas

- **Gateway abstraction is partially refactored.** Production boot now uses
  `gateway.core.GatewayChatHandler` and `gateway.core.AgentRouter`; Discord
  policy/send behavior belongs in `gateway.adapters.discord`. Approval and
  some tool docs still contain Discord-specific assumptions, so do not copy
  those into new platforms.
- **`manage_user_profile` tool supports two modes:** single-section mode (when `section` and `bullets` are provided) and whole-file/all mode (when `section` is omitted and `sections` map is passed). Omitted sections in whole-file mode are deleted, and a shrink check prevents dropping >50% of profile bullets unless `allow_shrink=True` is explicitly passed. Both modes require `expected_profile_hash`.
- **Agent loop (Think/Act) and prerequisite routing:** Chat/tool orchestration is now `Think(Decide) -> Think(Refine) -> Act -> ... -> Think(Decide)` in `twin/shared/agent/agent_loop.py`. `Think` is the only LLM-facing stage; `Act` has no LLM access and loads no persona. `Think(Decide)` can answer the user directly or select the next tool and includes persona. `Think(Refine)` remains mandatory before tool execution but omits persona; it receives the selected-tool guide, dynamic context, conversation, and fresh server time through stage messages. It may route/switch to a prerequisite tool (e.g. `get_profile`) when the selected tool is missing required arguments such as `expected_profile_hash`. Runtime values must stay stage-owned and must not be appended globally by `PromptManager` or persisted into T1. Refine cancellation/error and loop-limit exits ask a final `Think(Decide)` pass with native tools disabled; do not reintroduce a Resolve stage.
- **No Zalo adapter implementation exists yet.** `gateway/adapters/factory.py`
  raises `NotImplementedError` for `zalo`. Treat Zalo as planned/held until the
  Zalo webhook/token settings and adapter contract are defined.
- **Run tests through the project interpreter.** Prefer `python -m pytest ...`
  from an environment with the repository dependencies installed. When the
  `discord_bot` Conda environment exists, use
  `conda run -n discord_bot python -m pytest ...`; do not assume that
  environment exists on every host and do not use bare `pytest`.
- T3 storage is Markdown via `MarkdownProfileStore`, not YAML.
- `README.md` is the project README filename currently used at repo root.
- Root lint/format/type-check config is not currently established; do not add
  or run repo-wide formatters as part of unrelated work.
- Memory source lives under `twin/shared/memory/`. Do not recreate
  `twin/march7/memories/`, `twin/evernight/memories/`, or
  `twin/shared/memories/`.
- T2 timeline keeps memories user-centric for user scope, and also stores
  channel scope summaries with `user_id=channel_id`. Channel scope is
  consolidated via A2A with shipped entries; do not invent channel sentinel ids
  as `user_id` in `TimelineSummaryStore`.
- The legacy local Python consolidation paths (including `DiscussionConsolidator`, `consolidate_t2_memory`, `Consolidator`, `CleanupScheduler`, `TimelineStore`, `TimelineSearch`, and `T2Memory`) were removed. Current flow uses **A2A Consolidation**: `ActiveMemory` can invoke a consolidation callback when a scope reaches `TOKEN_THRESHOLD`; idle polling is provided by the standalone `twin.march7` entrypoint for user/channel scopes and by production Evernight for user scopes. March7 ships its T1 entries via `ConsolidationClient` and Evernight runs `ConsolidateMemoryTool` on those entries without re-reading March7's T1, then writes to `TimelineSummaryStore` / `MarkdownProfileStore`.
- Each agent builds its own runtime from the shared components (`ActiveMemory`,
  `MarkdownProfileStore`, `TimelineSummaryStore`). T1 uses isolated agent Redis
  DBs (`MARCH7_REDIS_DB=0`, `EVERNIGHT_REDIS_DB=1`); the T2 RediSearch index is
  shared on Redis DB 0 (`TIMELINE_REDIS_DB=0`).
- **`twin/shared/tools/` consolidated 2026-05-26.** Core types live in `twin.shared.tools.registry`; individual tool classes live under `twin/shared.tools.modules.<domain>.<tool>` (domains: `execution`, `memory`, `profile`, `web`). The paths `twin.shared.tools.base_tool` / `tool_registry` / `tool_discovery` / `implementations.system.*` no longer exist — do not recreate them.
- **LLM/embedding endpoints chạy trên host phải dùng `host.docker.internal`, không phải `localhost`.** Container march7/evernight có `extra_hosts: host.docker.internal:host-gateway` trong compose; `localhost` trong `.env` sẽ trỏ vào chính container và fail với `Cannot connect to host localhost:<port>`. Áp dụng cho `OPENAI_API_URL`, `EMBEDDING_API_URL`, `LM_STUDIO_API_URL`, `TOOL_LLM_ENDPOINT`. Service nội-mạng Docker (redis, codebox, evernight) thì dùng service name.
- **Docker entry for March7 is `python -m gateway`** (`gateway/__main__.py`),
  not `python -m twin.march7`. When wiring new background tasks (triggers,
  workers, schedulers) for March7, add them to `gateway/__main__.py` so they
  run inside the container. `twin/march7/__main__.py` is a thinner local-dev
  entry — keep it in sync but treat the gateway entry as authoritative.
- Local Redis/T2 data may be disposable during development because T3 Markdown
  is the durable profile/core memory. Confirm before deleting production data.
- New host interactions must use the `host_system` tool through the native
  `system-gateway` service. Do not recreate privileged container-side host
  bridges.
- **System Gateway runs on the host, not in a container.** Containers reach it
  via `SYSTEM_GATEWAY_URL` (e.g. `http://host.docker.internal:8380`). The
  secret is shared through `SYSTEM_GATEWAY_SHARED_SECRET`.
- **T2 recall is tool-only.** `SharedMemoryManager.get_context` returns only
  T1 + T3 context and no longer embeds or searches T2. The model obtains
  timeline context by calling `search_memory`.
- **T2 index dimension is 1024, not 768.** T2 uses `qwen3-embedding:0.6b`
  (`EMBEDDING_MODEL_NAME`) with `VECTOR HNSW FLOAT32 COSINE DIM=1024`
  (`EMBEDDING_VECTOR_SIZE`). Only dimension or index-type changes require
  `FT.DROPINDEX timeline_summaries` and a restart; adding `day`,
  `period_start`, and `period_end` is done via `FT.ALTER` without reindex.
- **New T2/T1 env vars control current behavior:** `EMBEDDING_MODEL_NAME`,
  `EMBEDDING_VECTOR_SIZE`, `EMBEDDING_QUERY_PREFIX`,
  `EMBEDDING_PASSAGE_PREFIX`, `T2_MIN_COSINE` (default `0.0`; calibrated/deployed
  `0.35`), `T1_ARCHIVE_ENABLED` (default `true`),
  `T1_ARCHIVE_TTL_DAYS` (default `90`).
- **`search_memory` is the only supported T2 retrieval tool.** It accepts
  `user_id`, optional `channel_id` (dual-scope), optional `query`, optional
  `days_back`, and `limit`. It does not accept `mode`, `topic`, `hours`, or
  `days`. BM25-only fused docs are still cosine-gated by `T2_MIN_COSINE`.
- **`TimelineSummaryStore` is a package (`twin/shared/memory/diary/`).** Import
  `TimelineSummaryStore` from `twin.shared.memory.diary`; import `_rrf_fuse`
  from `twin.shared.memory.diary.store` if needed for tests.
- **`TimelineSummaryStore` writes are append-only.** The constructor takes only
  `redis_client` and `embedding_dim`. The same-day diary merge (and its
  `embedding_service` constructor arg) was removed 2026-07-20 — each
  consolidation pass writes its own doc.
