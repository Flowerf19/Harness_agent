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
  bypass the boundary by reading March7 T1 keys directly.
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

Memory rewrite is implemented end-to-end. See
[plans/memory-rewrite.md](plans/memory-rewrite.md) for the final plan. Short
version:

- T1/T2/T3 source lives once under `twin/shared/memory/`.
- T1 is Redis JSON active memory scoped by `user` or `channel`.
- T2 is Redis Stack timeline memory with VECTOR HNSW 768 indexes.
- T3 is Markdown profile memory with 8 sections under `memories/`.
- `SharedMemoryManager` injects T3 profile context and T2 pre-flight retrieval
  into each turn, and fans out channel consolidation per participant.
- Legacy `twin/*/memories`, `twin/shared/memories`,
  `DiscussionConsolidator`, and `consolidate_t2_memory` paths are removed.

Open follow-up: live Discord DM/channel smoke requires real bot tokens; local
Docker health and A2A endpoints can be verified without Discord.

## Quick Links

- Docker/local runbook: [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)
- LLM providers: [../twin/shared/llm/README.md](../twin/shared/llm/README.md)
- Bash Executor security: [../scripts/README.md](../scripts/README.md)
- Docker services: [../docker/README.md](../docker/README.md)
