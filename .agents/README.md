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
- Bash Executor is privileged. Keep approval/audit behavior intact and do not
  log secrets.

## Current Task Status

Unified discussion memory is implemented end-to-end. See
[plans/unified-discussion-memory.md](plans/unified-discussion-memory.md)
for the full plan. Short version:

- T1 is scope-aware (`user`/`channel`) across both agents.
- Gateway separates observe / respond, with reply-to-bot triggering respond.
- Channel transcript context is injected into prompts.
- `SummaryPolicy` emits `SUMMARY_REQUESTED`; March7 calls Evernight A2A
  `consolidate_discussion`; `DiscussionConsolidator` fans out user-centric
  T2 pages; T1 cleans up on `SUMMARY_COMPLETED`.
- Each agent runs its own `InactivityTrigger` over its `SummaryStateRepository`.
- Legacy `TOKEN_LIMIT_REACHED` / snapshot overflow path is removed.

Open follow-ups: FT index migration script for production redeploy, and any
T2 search side enhancements (channel-scoped filters via `participants` TAG).

## Quick Links

- Docker/local runbook: [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)
- LLM providers: [../README_LLM_PROVIDERS.md](../README_LLM_PROVIDERS.md)
- Bash Executor security: [../README_BASH_EXECUTOR.md](../README_BASH_EXECUTOR.md)
- Docker services: [../docker/README.md](../docker/README.md)
