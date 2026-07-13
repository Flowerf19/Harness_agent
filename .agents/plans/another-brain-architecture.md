---
status: draft
owner: architecture
created: 2026-07-09
---

# Another Brain Architecture

`Another Brain` is a standalone memory service for agent systems. It should be
usable by Claude, Codex, Discord bots, local chat bots, or any other MCP-capable
host without knowing how those agents are implemented.

The service owns memory storage, retrieval, identity boundaries, and policy. The
client agent only sends observations or explicit memories and asks for recall.

## Goals

- Provide one shared long-term memory store for many agents.
- Support MCP as the primary integration surface.
- Track which agent wrote or read a memory through `agent_id`.
- Keep agent implementation details outside the service contract.
- Store canonical memory text in English so small models and embedding models
  have the strongest common operating language.
- Add a lightweight memory model for translation, normalization, and compact
  topic summaries; keep it separate from any chat/persona model.
- Run locally first, with a Docker deployment that includes persistent storage.
- Allow an npm package to act as a convenient MCP launcher, not as the core
  storage implementation.

## Non-Goals

- Do not depend on March7, Evernight, Discord, or any project-specific runtime.
- Do not require a chat framework, persona system, or agent loop.
- Do not require a heavyweight chat LLM. Any model inside Another Brain should
  be a small memory model with narrow prompts and replaceable providers.
- Do not partition shared memory by `agent_id` by default; that would prevent
  agents from sharing the same brain.

## Product Shape

Another Brain has three install shapes:

1. **Docker service**
   - Primary deployment.
   - Runs the MCP server and connects to Redis Stack or another supported store.
   - Best for shared memory across multiple agents and long-lived data.

2. **MCP stdio adapter**
   - Local process launched by an MCP host.
   - Can either run the service in-process for simple local use or proxy to a
     Docker/HTTP service.

3. **npm launcher**
   - Convenience package such as `@another-brain/mcp`.
   - Provides a familiar MCP config for clients that prefer `npx`.
   - Should not reimplement the memory engine in Node unless the project later
     chooses a TypeScript core.

## Identity Model

Identity is the core contract. The server should infer trusted identity from
configuration or auth whenever possible, instead of requiring the LLM to provide
it correctly in every tool call.

| Field | Meaning | Source |
| --- | --- | --- |
| `brain_id` | Shared memory namespace, e.g. `flowerf-main` | server config, token claim, or admin input |
| `agent_id` | Calling agent/client, e.g. `claude-desktop`, `march7`, `codex` | env var, token claim, MCP adapter config |
| `subject_id` | Person/project/entity the memory is about | tool input |
| `scope` | Memory boundary: `user`, `channel`, `project`, `global`, `entity` | tool input |
| `scope_id` | Stable id inside the scope | tool input |
| `source` | Origin detail such as `discord`, `claude`, `manual`, `api` | tool input or adapter default |

`brain_id` is the isolation boundary. `agent_id` is provenance and permission
context. Agents that share a `brain_id` can share memories unless policy says
otherwise.

## Core Data Model

The canonical storage model remains a **timeline**. Another Brain is not a
generic key-value note store; it stores dated memory entries that can be recalled
by semantic meaning, keyword match, subject, scope, and time.

Each timeline memory record should be explicit, versioned, and filterable.

```text
memory_id: uuid
brain_id: string
agent_id: string
scope: user | channel | project | global | entity
scope_id: string
subject_id: string | null
kind: fact | preference | event | summary | profile | note
content: string
original_content: string | null
original_language: string | null
canonical_language: "en"
summary: string | null
period_start: timestamp | null
period_end: timestamp | null
timeline_day: yyyy-mm-dd
source_event_ids: string[]
chunk_strategy: topic_timeline | explicit | imported
merge_count: integer
tags: string[]
importance: 1..5
confidence: 0.0..1.0
metadata: object
source: string | null
observed_at: timestamp
created_at: timestamp
updated_at: timestamp
expires_at: timestamp | null
deleted_at: timestamp | null
memory_model: string | null
embedding_model: string
embedding_dim: integer
schema_version: integer
```

The first storage backend can be Redis Stack because it supports RediSearch,
BM25, vector search, and local Docker deployment. The schema must include
`brain_id`, `scope`, `scope_id`, `subject_id`, `agent_id`, `kind`, `tags`, and
time fields as indexed filters.

Timeline fields are first-class:

- `content` is the canonical English memory text used for search and recall.
- `original_content` keeps the source-language text when preservation is useful.
- `canonical_language` is fixed to `en` for MVP.
- `observed_at` is when the source event happened.
- `period_start` and `period_end` bound the source conversation/event window
  covered by a timeline chunk.
- `created_at` is when Another Brain stored the memory.
- `updated_at` changes when a memory is merged or corrected.
- `timeline_day` is derived from `period_start` in the configured timezone, or
  `observed_at` for point memories.
- `source_event_ids` keeps provenance for the raw messages/events summarized by
  the chunk.
- `expires_at` supports retention by importance or policy.

This keeps the useful behavior of the current T2 timeline: memories are not just
facts; they are time-positioned summaries/events that can be widened by date
range when a narrow search returns nothing.

## Reference: Current T2 Chunking

The starting reference is March7's current T2 diary implementation:

- GitHub: `https://github.com/Flowerf19/March7/tree/main/twin/shared/memory/diary`
- Local code: `twin/shared/memory/diary/`
- Write entrypoint: `twin/shared/tools/modules/memory/consolidate_memory_tool.py`
- Read entrypoint: `twin/shared/tools/modules/memory/search_memory_tool.py`

Agents implementing this plan should inspect that directory before changing the
chunking policy. The current architecture is:

1. T1 messages are collected for one scope, either from local active memory or
   from shipped entries.
2. A summarizer reads that message window and returns up to five topic objects.
3. Each topic object becomes one T2 timeline chunk. This is the important
   boundary: chunks are semantic topic summaries over a time window, not raw
   token-size slices.
4. Each chunk is embedded with the passage embedding prefix, then stored as a
   Redis HASH under the timeline index.
5. The stored chunk carries `topic`, `topic_display`, `importance`,
   `period_start`, `period_end`, `source_entry_ids`, `day`, and `embedding`.
6. `day` is derived from the source period, not from the time the summarizer ran.
   This makes a late consolidation still land on the day the conversation
   happened.
7. The write path attempts a same-scope same-day merge before appending a new
   chunk. It finds the nearest existing chunk by vector search, requires cosine
   similarity above the configured merge floor, refuses merges that would exceed
   the configured max characters, concatenates old and new summaries, re-embeds,
   unions source ids, expands the period bounds, keeps max importance, and
   refreshes TTL from importance.
8. Search is timeline-aware: semantic KNN and BM25 are fused, filtered by scope
   and optional time range, then widened by policy when a narrow time window
   returns no result.

Another Brain should preserve this shape, but rename the fields and boundaries
for a standalone MCP service:

- current `summary_id` -> `memory_id`
- current `user_id` filter -> explicit `brain_id` + `scope` + `scope_id` +
  optional `subject_id`
- current `source_entry_ids` -> `source_event_ids`
- current `day` -> `timeline_day`
- current topic chunk -> `chunk_strategy=topic_timeline`

Do not preserve project-specific shortcuts such as storing channel memory under
`user_id=channel_id`. The new schema should represent scope explicitly.

## Language and Memory Model Policy

Another Brain should store memories in English by default, even when the input
conversation is Vietnamese or mixed-language. The reason is pragmatic: small
local models and many embedding models are more reliable in English, and a
shared MCP memory server should optimize for recall quality across many agents.

The service should own this normalization. Clients may send raw text in any
language, but the stored timeline chunk should be normalized server-side:

1. Detect or accept `original_language`.
2. Translate and compress the memory into English.
3. Preserve names, ids, commands, paths, dates, numbers, and quoted user
   preferences exactly.
4. Store the English result in `content`.
5. Optionally keep the source text in `original_content` for audit/debug.
6. Embed the English `content`, not the source-language text.

Use a dedicated lightweight memory model for this step. It is not a chat model
and should not know agent persona. Its jobs are narrow:

- translate source text to English;
- produce compact timeline chunks from observations;
- normalize relative dates into absolute dates when the caller supplies time
  context;
- return strict JSON for storage.

Suggested config:

```text
MEMORY_MODEL_PROVIDER=openai_compat | ollama | gemini | local
MEMORY_MODEL_NAME=...
MEMORY_MODEL_API_URL=...
MEMORY_MODEL_API_KEY=...
MEMORY_CANONICAL_LANGUAGE=en
STORE_ORIGINAL_CONTENT=true
```

The memory model is separate from the embedding provider. Changing the memory
model should not require reindexing unless the canonical text is regenerated.

## Memory Write Policy

Another Brain should support two write paths:

1. **Explicit memory write**
   - Tool: `brain_remember`.
   - Client sends the final memory text.
   - Server validates, normalizes to English, embeds, deduplicates, stores, and
     returns `memory_id`.
   - This is the required MVP path.

2. **Observation ingest**
   - Tool: `brain_ingest`.
   - Client sends raw messages/events with timestamps and actors.
   - Server uses the lightweight memory model to produce English topic timeline
     chunks.
   - This richer ingest path is not required for MVP; MVP can start with
     explicit memory writes.

The server should never silently trim or delete source data unless the caller
explicitly requests that behavior. Data loss policy belongs in the memory
service, not in each agent.

## Retrieval Policy

Search should be hybrid by default:

- vector similarity for semantic recall;
- keyword/BM25 search for names, ids, and exact terms;
- reciprocal-rank or similar fusion;
- filters for `brain_id`, `scope`, `scope_id`, `subject_id`, `kind`, `agent_id`,
  `tags`, and time range;
- similarity floor to avoid injecting weak memories;
- timeline widening: search within the requested date window first, then widen
  by policy if no results are found, and label the wider result window.

The tool output should expose enough evidence for the agent to judge relevance:

```text
memory_id
content or summary (canonical English)
original_language
kind
subject_id
scope/scope_id
source
agent_id
observed_at
importance
relevance score
```

## MCP Surface

MCP tools should be small and stable. Tool names use `brain_*` to stay short.

### `brain_remember`

Stores one explicit memory.

Required inputs:

- `content`
- `scope`
- `scope_id`

Optional inputs:

- `subject_id`
- `kind`
- `tags`
- `importance`
- `confidence`
- `observed_at`
- `metadata`

Server-filled fields:

- `brain_id`
- `agent_id`
- `memory_id`
- normalized English `content`
- `original_language`
- embeddings
- timestamps

### `brain_search`

Searches memories.

Inputs:

- `query`
- `scope`
- `scope_id`
- `subject_id`
- `k`
- `since`
- `until`
- `kind`
- `tags`
- `include_agent_ids`

`query` may be empty when the caller wants recent memories.

### `brain_recent`

Returns recent memories by scope/time without requiring embeddings.

### `brain_get`

Fetches one memory by `memory_id`.

### `brain_forget`

Soft-deletes one memory. Hard delete should be an admin-only operation.

### `brain_health`

Reports service status, storage status, index version, embedding model, and
embedding dimension. It must not return secrets.

## MCP Resources

Resources should expose machine-readable context, not agent instructions:

- `brain://schema` - current memory schema and version.
- `brain://health` - same health data as `brain_health`.
- `brain://memory/{memory_id}` - one memory record if authorized.

Prompts are optional. If added, they should be generic usage hints such as
`brain-recall-guidance`, not agent-specific behavior.

## Auth and Permissions

Local stdio can rely on local process trust, but the server should still require
configuration:

```text
ANOTHER_BRAIN_ID=flowerf-main
ANOTHER_BRAIN_AGENT_ID=claude-desktop
ANOTHER_BRAIN_API_TOKEN=...
```

Remote HTTP must authenticate every request. The token should map to:

- allowed `brain_id` values;
- caller `agent_id`;
- allowed operations: read, write, delete, admin;
- optional scope restrictions.

The LLM should not be trusted to declare its own `agent_id` or permissions.
Tool inputs may include `agent_id` only for admin/debug use.

## Storage Architecture

Recommended MVP:

```text
another-brain-server
  -> MCP transport: stdio and/or Streamable HTTP
  -> service layer: validation, auth context, memory policy
  -> memory model: lightweight translation/normalization/summarization
  -> embedding provider: OpenAI-compatible, Ollama, Gemini, or local model
  -> repository: Redis Stack
  -> persistent volume: Redis data
```

Redis keys should be prefixed:

```text
ab:{brain_id}:memory:{memory_id}
ab:{brain_id}:audit:{date}
```

RediSearch can use one global index with `brain_id` as a required filter, or one
index per `brain_id`. Start with one global index for simpler migrations; never
run a query without the `brain_id` filter.

## Embedding Policy

The service owns embedding configuration.

Required config:

```text
EMBEDDING_PROVIDER=openai_compat | ollama | gemini | local
EMBEDDING_MODEL=...
EMBEDDING_DIM=...
EMBEDDING_API_URL=...
EMBEDDING_API_KEY=...
```

Rules:

- store `embedding_model` and `embedding_dim` on every memory;
- refuse writes when vector dimension mismatches the active index;
- expose the active embedding model through `brain_health`;
- embed canonical English `content`, not `original_content`;
- require a migration/reindex command when changing dimensions.

## Packaging

### Docker

Primary install target:

```text
docker compose up -d
```

Compose should include:

- `another-brain` service;
- `redis-stack` service;
- named volume for Redis data;
- `.env` for embedding provider and auth;
- healthcheck for MCP/HTTP and Redis.

### npm

Secondary install target:

```text
npx -y @another-brain/mcp
```

The npm package should:

- read MCP client env/config;
- start a stdio adapter;
- connect to a configured HTTP service, or optionally start Docker if enabled;
- avoid owning the database itself.

This keeps the easy MCP UX without making Node the source of truth.

## Suggested Repository Layout

```text
another-brain/
  README.md
  docs/
    architecture.md
    mcp-tools.md
    deployment.md
  src/
    another_brain/
      server.py
      config.py
      auth.py
      mcp/
        stdio.py
        http.py
        tools.py
        resources.py
      memory/
        models.py
        service.py
        repository.py
        search.py
        embeddings.py
      storage/
        redis_store.py
        migrations.py
      audit.py
  docker/
    Dockerfile
    docker-compose.yml
  packages/
    npm-launcher/
      package.json
      src/
  tests/
```

## MVP Milestones

1. Core memory model and Redis Stack repository.
2. Lightweight memory model abstraction for English normalization.
3. Embedding provider abstraction and `brain_health`.
4. MCP stdio server with `brain_remember`, `brain_search`, `brain_recent`.
5. Docker Compose deployment.
6. Auth context with server-filled `brain_id` and `agent_id`.
7. `brain_get` and `brain_forget` with audit log.
8. npm launcher that proxies to the service.
9. Optional richer observation ingest pipeline.

## Migration From Existing T2

Existing T2 data can be migrated later by mapping:

```text
old user_id      -> subject_id or scope_id
old summary      -> content
old original text -> original_content when available
old topic        -> tags/kind
old importance   -> importance
old period_start -> period_start/observed_at/timeline_day
old period_end   -> period_end
old source_entry_ids -> source_event_ids
old created_at   -> created_at
source           -> "march7-t2-migration"
agent_id         -> migration agent id
brain_id         -> configured destination brain
```

Do not preserve the old `user_id=channel_id` shortcut in the new schema. The
new schema should represent channel and user scopes explicitly.

## Open Decisions

- Whether Redis Stack remains the only supported backend after MVP.
- Whether server-side summarization belongs in core or in a plugin.
- Whether remote MCP should be exposed directly or through a small gateway.
- Whether memory export/import should use JSONL, SQLite, or both.
- Whether `brain_id` should support multiple users on one server from day one.
