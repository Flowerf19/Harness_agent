# Gateway Platform Abstraction Plan

Status: partially implemented. Phase 2, Phase 3, the first slice of Phase 4,
and Phase 9 are in code; Zalo remains held.

Date: 2026-06-07.

## Problem

The intended design is good: keep March7/Evernight as agents, keep
`ChatGateway` as the platform gate, and make Discord/Zalo compatibility layers
compile native messages into unified gateway models.

The original code only partially followed that design. `UnifiedMessage` and
`ChatGateway` existed, but production March7 boot wired a
`DiscordGatewayHandler` that expected `_raw_discord_message`, performed
Discord admin-channel/typing/reply behavior itself, called `AgentRouter`, sent
Discord replies directly, and returned `""`. That first cut has now been split:
production boot uses `gateway.core.GatewayChatHandler`, while Discord-specific
policy and native sending live in the Discord adapter.

Known hard dependencies to remove or isolate:

- `gateway/adapters/discord/handler.py` remains as a Discord compatibility
  helper for retry UI and response splitting, not production chat routing.
- `twin/shared/tools/approval_context.py` stores `discord.Message`.
- `twin/shared/tools/approval_gate.py` imports Discord button views.
- `twin/shared/tools/dm_client.py` accepts `discord.Message`.
- `gateway/adapters/factory.py` still does not implement Zalo; it now fails
  clearly with `NotImplementedError`.
- `gateway/adapters/discord/evernight_adapter.py` routes owner chat directly to
  Evernight instead of through the same gate contract.

## Target Architecture

Keep the current broad architecture, but make layer ownership strict:

- **Platform adapters** own native SDKs and native UI:
  Discord `discord.py`, Zalo SDK/API, mention parsing, message cleaning,
  typing indicators, native buttons, max message length, and send retries.
- **Gateway core** owns platform-neutral routing:
  observe message, determine scope, apply generic respond/silence policy, call
  the selected agent, and hand a unified reply back to the originating adapter.
- **Agents** own conversation intelligence:
  `March7Agent` and `EvernightAgent` should receive platform-neutral user,
  channel, assistant identity, and mention metadata. They should not receive or
  require native Discord objects.
- **Shared memory/tools** must remain platform-neutral:
  use labels like `Platform user ID`, `conversation_id`, `space_id`, or
  `channel_id`; never require `discord.Message`.
- **Approval is a gateway capability**, not a Discord global:
  shared tools ask an approval service for a decision. A Discord approval
  backend can render Discord buttons; a Zalo backend can do its own flow; a
  missing backend rejects by default unless explicit dev auto-approve is set.
- **March7 and Evernight share runtime primitives, not identity/behavior**:
  both agents can reuse common LLM/tool-loop and memory-runtime construction,
  but they should remain separate classes. March7 owns public/channel chat
  behavior; Evernight owns consolidation, private owner chat, background jobs,
  and self-heal.

Suggested module shape:

```text
gateway/
  core/
    agent_router.py          # no Discord imports
    handler.py               # GatewayChatHandler, UnifiedMessage only
    policy.py                # generic observe/respond/silence decisions
    response.py              # reply parts, platform-neutral helpers
  shared/
    model.py                 # unified message + neutral metadata
    approval.py              # approval backend protocol/context
  adapters/
    discord/
      adapter.py             # discord.py client, to/from unified models
      policy.py              # Discord admin-channel and mention/reply mapping
      approval.py            # Discord buttons/views integration
    zalo/
      adapter.py             # future Zalo native API adapter
```

The exact names can change, but dependencies must point inward:

```text
Discord/Zalo adapters -> gateway core/shared -> twin agents/shared
```

Never:

```text
twin/shared -> gateway.adapters.discord
gateway core -> gateway.adapters.discord
```

Suggested shared agent-runtime shape:

```text
twin/shared/agent/
  contracts.py          # Protocols such as ChatAgent / AgentRuntime
  chat_turn.py          # ChatTurnRunner: LLM/tool loop + response normalization
  runtime.py            # Shared runtime bundle/build helpers for containers
  cards.py              # optional AgentCard helper, only if it removes duplication
```

Use composition first:

```text
March7Agent
  uses ChatTurnRunner
  keeps March7-specific channel scope, allow-silence, active marker,
  BashExecutorUnavailableError propagation, assistant message persistence.

EvernightAgent
  uses ChatTurnRunner
  keeps Evernight-specific consolidation/private-chat behavior and does not
  inherit March7 public-channel rules.
```

Avoid a large `BaseAgent` template class unless a later refactor proves the
shared API is stable. A small `Protocol` is safer than inheritance here because
Evernight is intentionally not just a second March7 skin.

## Refactor Plan

### Phase 1 - Freeze the Boundary

Goal: document and test the desired boundary before moving behavior.

1. Add/update tests proving a clean non-Discord `UnifiedMessage` can pass
   through a core handler and produce a reply through `ChatGateway`.
2. Add a regression test that core handler modules import without `discord.py`
   installed or without importing `gateway.adapters.discord`.
3. Add a small fixture for platform metadata: direct/group/channel, addressed,
   reply-to-bot, bot identity, and participant mentions.

Review point: tests should describe the abstraction without changing runtime.

### Phase 2 - Move AgentRouter Out Of Discord

Goal: remove the first structural smell.

1. Move `AgentRouter` to `gateway/core/agent_router.py`.
2. Keep a temporary compatibility import in
   `gateway/adapters/discord/agent_router.py` if needed.
3. Update `gateway/__main__.py` to import the core router.
4. Keep route behavior unchanged.

Expected verification:

```bash
conda run -n discord_bot python -m pytest tests/gateway tests/unit/march7_handle_chat_scope_test.py -q
```

### Phase 3 - Introduce GatewayChatHandler

Goal: make production handling accept `UnifiedMessage` without native Discord.

1. Create `gateway/core/handler.py` with `GatewayChatHandler`.
2. Move generic logic from `DiscordGatewayHandler`:
   observe user/channel messages, debounce by scope, allow silence for ambient
   messages, call `AgentRouter`, and return response text.
3. Define neutral metadata in `UnifiedMessage.extensions` for the first pass:
   `is_addressed`, `is_reply_to_bot`, `respond_mode`, `bot_id`, `bot_name`,
   `space_id`, and normalized `mentioned_users`.
4. Update `gateway/__main__.py` to use `GatewayChatHandler`.
5. Keep `DiscordGatewayHandler` only as a compatibility wrapper or remove it
   after Discord adapter owns all native behavior.

Review point: a mock adapter and a Discord-converted message should both run
through the same handler.

### Phase 4 - Push Native Discord Behavior Back To Discord Adapter

Goal: Discord remains fully featured without leaking raw objects into core.

1. Discord adapter computes clean content, bot mention, reply-to-bot, route
   hints, and channel mode before creating `UnifiedMessage`.
2. Discord adapter handles native side effects:
   unconfigured-channel warning, typing indicator, Discord-specific send chunk
   limits, native button views, and HTTP exceptions.
3. `ChatGateway.route_message()` owns the generic response handoff again:
   handler returns text, gateway builds a unified reply, adapter sends it.
4. Remove `_raw_discord_message` from handler requirements. If raw native
   payload is kept in `extensions`, only Discord adapter may read it.

### Phase 5 - Platform-Neutral Memory And Agent Context

Goal: March7 does not teach the model that every user is on Discord.

1. Replace prompt labels `Discord ID` with `Platform user ID` or
   `{platform_name} user ID`.
2. Keep existing `channel_id`/`guild_id` parameters only as compatibility
   aliases while introducing neutral names where useful:
   `conversation_id`, `space_id`, `assistant_id`, `assistant_name`,
   `mentioned_participants`.
3. Do not perform a broad schema migration unless required. T1 metadata keys
   can keep `channel_id` initially because they already mean conversation
   scope, but docs and prompts should be neutral.

### Phase 6 - Platform-Neutral Approval

Goal: Bash approval does not depend on Discord globals.

1. Replace `approval_context` with a neutral `ApprovalContext`:
   platform, requester id, channel/conversation id, message id, display name,
   and an approval backend reference or capability key.
2. Move Discord button approval imports from `twin/shared/tools` into
   `gateway/adapters/discord`.
3. `ApprovalGate` calls an `ApprovalBackend` protocol.
4. Add safe fallback behavior:
   no approval backend means reject, unless explicit dev auto-approve env is
   enabled.

### Phase 7 - Evernight Chat Surface Through Gate Contract

Goal: Evernight's owner chat is also a compatibility surface.

Short-term acceptable state:

- Evernight can keep a Discord-specific private adapter for approval DMs while
  it is clearly isolated and not used by March7 core/gateway code.

Preferred target:

1. Evernight process creates its own `ChatGateway` with a core handler routed
   to `EvernightAgent`, or uses the same core handler with `agent_name`
   defaults.
2. Discord `!9`, DM, and mention behavior becomes Discord adapter route hints
   for Evernight instead of direct calls to `EvernightAgent`.
3. A future Zalo owner/private chat can register another adapter without
   touching `EvernightAgent`.

### Phase 8 - Add Zalo Adapter Skeleton

Goal: make `GATEWAY_ENABLED_PLATFORMS=zalo` honest.

1. Add `gateway/adapters/zalo/` package only after the core handler no longer
   depends on Discord.
2. Implement minimal receive/send contract or remove the factory branch until
   implementation is ready.
3. Add tests for adapter factory behavior when Zalo env is missing.

### Phase 9 - Share Agent Runtime Without Merging Agents

Status: implemented in a small composition slice. `March7Agent` and
`EvernightAgent` now use `ChatTurnRunner`; both classes still own their own
memory, persistence, silence, and failure behavior.

Goal: remove duplicate March7/Evernight plumbing while preserving their
different responsibilities.

1. Add `twin/shared/agent/chat_turn.py` with a small `ChatTurnRunner`.
   It should own only common mechanics:
   LLM type detection, `run_strict_tool_loop`, `LLMResponse` normalization,
   `LLM_ERROR_RESPONSES` handling, reasoning-only detection, and optional token
   logging hooks.
2. Update `March7Agent.handle_chat()` to use `ChatTurnRunner` but keep all
   March7-specific behavior in `March7Agent`: active marker, channel/user
   context parameters, silence sentinel, Bash Executor unavailable propagation,
   and assistant message persistence with channel metadata.
3. Update `EvernightAgent.handle_chat()` to use `ChatTurnRunner` but keep
   Evernight-specific behavior in `EvernightAgent`: private user-scope chat,
   consolidation methods, and its own failure text.
4. Add focused tests around both agents or the runner so behavior stays
   equivalent for normal text, LLM error sentinels, reasoning-only responses,
   silence handling, and Bash Executor propagation where applicable.
5. If the agent constructors still duplicate enough code after `ChatTurnRunner`,
   extract only a light shared helper or protocol. Do not introduce a broad
   `BaseAgent` with many hooks in the first pass.

### Phase 10 - Share Container Runtime Builder

Goal: reduce duplication between `March7Container` and `EvernightContainer`
without hiding agent-specific wiring.

1. Extract the shared LLM, embedding, Redis, active memory, timeline store,
   timeline search, profile store, consolidator, cleanup scheduler, summary
   state, and summary policy setup into a small runtime builder/bundle under
   `twin/shared/agent/` or `twin/shared/runtime/`.
2. Keep container-owned differences explicit:
   config type, Redis DB, persona path, tool registry `agent_name`,
   March7's Evernight DM approval flag, March7 redis active marker, and
   Evernight's `march7_url`/consolidator/self-heal integration.
3. Add focused tests or smoke imports for both containers. Full runtime tests
   may still require Redis; do not fake confidence by adding broad unrun tests.

## Design Notes

The current architecture is worth keeping. The problem is not `ChatGateway` or
`UnifiedMessage`; the problem is that a Discord-specific handler became the
production brain path. The smallest safe correction is to move shared behavior
out of `gateway/adapters/discord/handler.py`, not to rewrite agents or memory
from scratch.

The same principle applies to March7/Evernight. The duplication is real, but
the safest fix is to share mechanics (`ChatTurnRunner`, runtime bundle) rather
than force both agents into a large inheritance hierarchy. Evernight is a
background/consolidation/private-chat agent, not merely another public chat
adapter.

Some Discord vocabulary can remain inside the Discord adapter and docs for
Discord setup. It should not appear in platform-neutral prompts, shared tools,
or core gateway modules.

Prefer compatibility aliases over large one-shot renames. For example, support
`guild_id` while introducing `space_id`; support `mentioned_users` while
introducing `mentioned_participants`. Remove old names later after tests and
call sites are migrated.

## Review Checklist

- Does every non-Discord module import without importing `discord`?
- Can a mock/Zalo-like adapter emit a clean `UnifiedMessage` and receive a
  reply through `ChatGateway`?
- Does Discord still support admin channels, mentions, replies, typing,
  chunking, and approval buttons after behavior moves into its adapter?
- Does March7 memory prompt say platform-neutral IDs?
- Does Bash approval reject safely when no platform approval backend exists?
- Are March7 and Evernight still separated by A2A where required?
