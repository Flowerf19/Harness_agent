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

- **March7** owns chat, tool calling, T1 active memory, and T3 profile memory.
- **Evernight** owns consolidation, background jobs, and self-heal flows.
- Evernight must use A2A to interact with March7 session memory; it must not
  bypass the boundary by reading March7 T1 keys directly.
- Bash Executor is privileged. Keep approval/audit behavior intact and do not
  log secrets.

## Quick Links

- Docker/local runbook: [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)
- LLM providers: [../README_LLM_PROVIDERS.md](../README_LLM_PROVIDERS.md)
- Bash Executor security: [../README_BASH_EXECUTOR.md](../README_BASH_EXECUTOR.md)
- Docker services: [../docker/README.md](../docker/README.md)
