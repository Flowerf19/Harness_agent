# Agent Guidance Index

Repo guidance is intentionally small. Use it for policy, runtime boundaries, and
verified commands. Use CodeGraph for structural code questions.

## Read Order

1. [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) - runtime, architecture boundaries,
   service ownership, key env vars.
2. [AGENT_RULES.md](AGENT_RULES.md) - safety, workflow, style, PR hygiene,
   verified gotchas.
3. [TESTING_GUIDE.md](TESTING_GUIDE.md) - test layout and verification commands.

## CodeGraph Usage

Prefer CodeGraph over broad file reads for structural questions:

- Definitions/signatures: `codegraph_search` or `codegraph_node`
- Callers/callees/impact: `codegraph_callers`, `codegraph_callees`,
  `codegraph_impact`
- Feature or bug context: `codegraph_context`, then one focused
  `codegraph_explore`
- File tree from the index: `codegraph_files`

Use native search/read for literal text, comments, docs, configs, manifests,
or after CodeGraph has identified the exact file to inspect.

## Specialized Skills

Skills live globally at `~/.claude/skills/` (clone of [Flowerf19/agents-skills](https://github.com/Flowerf19/agents-skills)) — applies to all projects, all agents. Claude Code auto-discovers; other agents read `SKILL.md` at that path.

- `implementation-planner` — turn spec/feature/bug into execution-ready plan (run BEFORE writing code).
- `thoughtful-coder` — surgical code changes: Correctness → Minimal diff → Consistency → Verifiable → Simplicity.
- `debug-investigator` — root-cause investigation BEFORE any fix (Iron Law: no patch without cause).
- `code-reviewer` — independent review of a change after `thoughtful-coder` completes; before merge.
- `architecture-docs` — maintain/refresh `.agents/` docs after architectural changes.
- `create-readme` — write/update root README from real repo evidence.

Update: `cd ~/.claude/skills && git pull`.

## Copilot MCP Setup

GitHub Copilot supports MCP tools, but CodeGraph is not built in. If Copilot
does not already expose CodeGraph tools, configure a local MCP server manually
with this command shape:

```json
{
  "mcpServers": {
    "codegraph": {
      "type": "stdio",
      "command": "codegraph",
      "args": ["serve", "--mcp", "--path", "/home/flowerf/Projects/march7"]
    }
  }
}
```

For Copilot custom agents, allow either all tools (`tools: ["*"]`) or the
specific CodeGraph MCP tool names exposed by the client. Without this MCP
server, agents should fall back to targeted search/read.

## Critical Boundaries

- **March7** owns primary public chat, tool calling, its own T1/T3 memory, and reads T2.
- **Evernight** owns consolidation, background jobs, self-heal, and private owner chat (via DM and `!9` prefix) with its own T1/T3 memory.
- Evernight must use A2A to interact with March7 session memory; it must not
  bypass the boundary by reading March7 T1 keys directly. Cross-agent
  consolidation ships T1 entries over A2A; Evernight must not re-observe or
  clear March7's T1 by direct Redis access.
- **Gateway must be platform-agnostic.** Discord, Zalo, or any future chat
  surface are compatibility adapters. They translate native events into
  unified gateway models and send unified replies back out. Core agent,
  memory, tool, and approval logic must not require Discord native objects.
- Bash Executor is privileged. Keep approval/audit behavior intact and do not
  log secrets.

## Current Task Status

Gateway/platform abstraction is partially refactored as of 2026-06-07. See
[plans/gateway-platform-abstraction.md](plans/gateway-platform-abstraction.md).
Production `gateway/__main__.py` now boots `gateway.core.GatewayChatHandler`
and `gateway.core.AgentRouter`; Discord admin-channel/mention/typing behavior
lives in the Discord adapter. Evernight Discord DM/tag/`!9` owner chat also
enters the same unified gateway contract before reaching `EvernightAgent`.
Zalo remains planned but not implemented. Shared approval uses neutral context;
the current DM delivery backend is still Evernight's Discord bot.

T2 diary/retrieval is implemented, deployed, and live-verified as of
2026-07-03. See the live verification note at
[`/home/flowerf/.claude/projects/-home-flowerf-Projects-march7/memory/t2-plan-progress.md`](/home/flowerf/.claude/projects/-home-flowerf-Projects-march7/memory/t2-plan-progress.md).
Current facts:

- T1/T2/T3 source lives once under `twin/shared/memory/`.
- T1 is Redis JSON active memory scoped by `user` or `channel`. Archiving is
  enabled by default (`T1_ARCHIVE_ENABLED=true`, `T1_ARCHIVE_TTL_DAYS=90`);
  trim uses exact `entry_ids` and archives summarized entries before deleting
  them.
- T2 is Redis Stack timeline memory with `VECTOR HNSW FLOAT32 COSINE DIM=1024`,
  using `qwen3-embedding:0.6b` via the openai-compat provider. Query/passage
  prefixes are configurable through env vars (`EMBEDDING_QUERY_PREFIX`,
  `EMBEDDING_PASSAGE_PREFIX`). The cosine gate `T2_MIN_COSINE` defaults to
  `0.0` in Config and is calibrated/deployed to `0.35`; same-day diary merge
  uses `T2_MERGE_MIN_COSINE=0.60` and `T2_MERGE_MAX_CHARS=1500`.
- T2 recall is **tool-only**. `SharedMemoryManager.get_context` returns only
  T1 + T3 context; it no longer embeds or searches T2. The model calls
  `search_memory` when it needs timeline context.
- `search_memory` accepts `user_id`, optional `channel_id` (dual-scope),
  optional `query`, optional `days_back`, and `limit`. It no longer accepts
  `mode`, `topic`, `hours`, or `days`. Hybrid KNN+BM25 is used when `query`
  is provided; time-range fallback uses `get_recent`. BM25-only fused docs are
  still gated by `T2_MIN_COSINE`.
- Channel scope stores T2 summaries with `user_id=channel_id`, so channel
  timelines are searchable alongside user timelines.
- Cross-DB consolidation is fixed via "Cách B": March7 ships T1 entries to
  Evernight over A2A, Evernight consolidates the shipped entries without
  re-reading March7's Redis, and March7 trims its own T1 by the returned
  `entry_ids`.
- Legacy `twin/*/memories`, `twin/shared/memories`,
  `DiscussionConsolidator`, and `consolidate_t2_memory` paths are removed.

Verification (2026-07-03): `conda run -n discord_bot python -m pytest tests -q
--ignore=tests/unit/discord_send_response_test.py
--ignore=tests/unit/evernight_discord_adapter_test.py
--ignore=tests/services/system_gateway_cli_test.py -p no:phoenix` —
479 passed, 6 skipped.

Open follow-up: live Discord DM/channel smoke requires real bot tokens; local
Docker health and A2A endpoints can be verified without Discord.

## Quick Links

- Docker/local runbook: [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)
- LLM providers: [../twin/shared/llm/README.md](../twin/shared/llm/README.md)
- Bash Executor security: [../scripts/README.md](../scripts/README.md)
- Docker services: [../docker/README.md](../docker/README.md)
- T2 live verification: [`/home/flowerf/.claude/projects/-home-flowerf-Projects-march7/memory/t2-plan-progress.md`](/home/flowerf/.claude/projects/-home-flowerf-Projects-march7/memory/t2-plan-progress.md)
