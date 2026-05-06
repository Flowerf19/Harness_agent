---
goal: Fix all 8 discrepancies between original Discord cog (src/cogs/chat_gateway.py) and gateway Discord adapter (gateway/adapters/discord/)
version: '1.0'
date_created: '2026-05-05'
last_updated: '2026-05-05'
owner: developer
status: Planned
tags:
  - bug
  - discord
  - gateway
  - adapter
---

# Fix Gateway Discord Adapter Discrepancies

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

## Overview

The gateway Discord adapter (`gateway/adapters/discord/`) has 8 functional discrepancies compared to the original cog implementation (`src/cogs/chat_gateway.py`). These cause the gateway to forward ALL messages (no filtering), lack response chunking (will crash on long replies), skip loading essential cogs (no commands available), and fail to start the nightly background task. This plan brings the gateway adapter to behavioral parity with the original cog.

## Requirements

- **REQ-001**: Gateway must filter messages identically to original: only respond to DMs, mentions, or approved admin channels (via `AdminChannels.is_bot_channel()`)
- **REQ-002**: Gateway must chunk responses > 1900 chars using the same `\n`-split → `_chunk_text()` hybrid logic as original
- **REQ-003**: `AdminChannels` cog must be loaded in gateway mode so `is_bot_channel()` works and slash commands (`/addbotchannel`, `/removebotchannel`, `/listbotchannels`, `/clearbotchannels`) are available
- **REQ-004**: `UserCommands` cog must be loaded in gateway mode so prefix commands (`!ping`, `!status`) work
- **REQ-005**: Gateway must skip messages where `ctx.valid` is True (bot commands like `!clear`, `!addbotchannel`)
- **REQ-006**: Gateway must strip `<@bot_id>` mention tags from message content before sending to LLM
- **REQ-007**: Gateway must show typing indicator and apply `Config.PART_BREAK_DELAY` between multi-segment response parts
- **REQ-008**: Gateway must send Vietnamese error message to user when coordinator fails, instead of silently returning empty string
- **REQ-009**: `NightlyTrigger` must be started in gateway mode via `asyncio.create_task(container.nightly_trigger.start())`

## Constraints & Guidelines

- **CON-001**: DO NOT modify `src/cogs/chat_gateway.py`, `src/cogs/admin_channels.py`, `src/cogs/user_commands.py`, or `src/bot.py` — these are the reference implementations
- **CON-002**: The `UnifiedMessage` dataclass is frozen (immutable) — extension data must be passed via `extensions` dict at construction time
- **CON-003**: The `DiscordPlatformAdapter` holds a reference to `CoreBot` (`self._bot`) which is a `commands.Bot` instance — cogs are loaded via `self._bot.load_extension()`
- **CON-004**: The gateway handler has no direct access to the `discord.Message` object — it receives a `UnifiedMessage`. The original message must be stored in `extensions` by the converter for typing indicator and channel access
- **GUD-001**: Chunking logic must be copied exactly: `\n` replacement → line splitting → `_chunk_text()` with `sent_tokenize` fallback → 1900 char limit
- **GUD-002**: Error message must match original: `"Hệ thống não bộ của tớ đang bị quá tải xíu, cậu thử lại sau vài giây nhé!"`
- **PAT-001**: Use the existing `DiscordMessageConverter` to extend `to_unified()` with `is_mentioned` flag and store raw `discord.Message` in extensions for later access
- **PAT-002**: Load cogs in `DiscordPlatformAdapter.connect()` after `container.initialize()` but before `self._bot.start(token)` — matching the order in `CoreBot.setup_hook()`

## Implementation Phases

### Phase 1: Add `is_mentioned` flag and raw message storage to converter
**Goal**: GOAL-001 — `UnifiedMessage` from Discord carries `is_mentioned` boolean and raw `discord.Message` reference for downstream filtering

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| TASK-001 | Add `is_mentioned` key to `UnifiedMessage.extensions` in `DiscordMessageConverter.to_unified()`, computed as `self._bot.user in message.mentions` — but converter is static, so pass `bot_user` as optional parameter | `gateway/adapters/discord/converter.py` | None | ☐ | |
| TASK-002 | Store raw `discord.Message` object in `UnifiedMessage.extensions` under key `_raw_discord_message` for later access to channel typing indicator | `gateway/adapters/discord/converter.py` | TASK-001 | ☐ | |
| TASK-003 | Update `DiscordPlatformAdapter._register_events()` to pass `self._bot.user` to `DiscordMessageConverter.to_unified()` call | `gateway/adapters/discord/adapter.py` | TASK-001, TASK-002 | ☐ | |

### Phase 2: Load cogs and start NightlyTrigger in adapter connect()
**Goal**: GOAL-002 — `AdminChannels`, `UserCommands` cogs are loaded and `NightlyTrigger` is started when gateway Discord adapter connects

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| TASK-004 | In `DiscordPlatformAdapter.connect()`, after `container.initialize()` and before `self._bot.start(token)`, add `await self._bot.load_extension("src.cogs.admin_channels")` | `gateway/adapters/discord/adapter.py` | None | ☐ | |
| TASK-005 | Add `await self._bot.load_extension("src.cogs.user_commands")` after admin_channels load | `gateway/adapters/discord/adapter.py` | TASK-004 | ☐ | |
| TASK-006 | Start NightlyTrigger: `if container.nightly_trigger: asyncio.create_task(container.nightly_trigger.start())` after cog loading | `gateway/adapters/discord/adapter.py` | TASK-005 | ☐ | |
| TASK-007 | Wrap cog loading in try/except with logging matching `src/bot.py` pattern; if a cog fails to load, log error but continue (non-fatal) | `gateway/adapters/discord/adapter.py` | TASK-006 | ☐ | |

### Phase 3: Add command filter and mention stripping to event registration
**Goal**: GOAL-003 — Bot commands are skipped and mention tags are stripped from message content before forwarding

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| TASK-008 | In `_register_events.on_message()`, after bot check, add `ctx = await self._bot.get_context(message)` and `if ctx.valid: return` to skip prefix commands | `gateway/adapters/discord/adapter.py` | None | ☐ | |
| TASK-009 | Compute `is_mentioned = self._bot.user in message.mentions`; if True, strip `<@{self._bot.user.id}>` from `message.content` before passing to converter | `gateway/adapters/discord/adapter.py` | TASK-008 | ☐ | |
| TASK-010 | Pass stripped content to converter — modify converter `to_unified()` to accept optional `content_override` parameter, or strip in adapter before calling converter | `gateway/adapters/discord/adapter.py` | TASK-009 | ☐ | |
| TASK-011 | Pass `is_mentioned` flag to converter for storage in extensions | `gateway/adapters/discord/adapter.py` | TASK-010 | ☐ | |

### Phase 4: Implement channel/mention/DM filtering, chunking, typing, and error handling in handler
**Goal**: GOAL-004 — `DiscordGatewayHandler.handle_message()` replicates original cog's filtering, response chunking, typing indicator, and error messaging

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| TASK-012 | In `handle_message()`, extract `is_mentioned` from `msg.extensions`; extract raw `discord.Message` from `msg.extensions["_raw_discord_message"]`; extract `channel_type` from `msg.channel` | `gateway/adapters/discord/handler.py` | Phase 1 | ☐ | |
| TASK-013 | Implement DM check: `is_dm = msg.channel.channel_type == "dm"` | `gateway/adapters/discord/handler.py` | TASK-012 | ☐ | |
| TASK-014 | Implement admin channel check: fetch `AdminChannels` cog via `self._get_bot().get_cog("AdminChannels")`, call `is_bot_channel(guild_id, channel_id)` — need guild_id which must come from raw message extensions | `gateway/adapters/discord/handler.py` | TASK-013, TASK-001 | ☐ | |
| TASK-015 | Add filtering logic: `if not (is_dm or is_mentioned or is_allowed_channel): return ""` — skip processing | `gateway/adapters/discord/handler.py` | TASK-014 | ☐ | |
| TASK-016 | After content strip check (`if not content: return ""`), implement coordinator call with try/except — on error, send Vietnamese error message via raw channel | `gateway/adapters/discord/handler.py` | TASK-015 | ☐ | |
| TASK-017 | Implement `_send_response()` method on handler: replicate original's `\n` replacement, line splitting, 2000 char check, `_chunk_text()` call for oversized segments | `gateway/adapters/discord/handler.py` | TASK-016 | ☐ | |
| TASK-018 | Implement `_chunk_text()` method on handler: copy exact logic from original `ChatGateway._chunk_text()` — line-based splitting with `sent_tokenize` fallback, 1900 limit | `gateway/adapters/discord/handler.py` | TASK-017 | ☐ | |
| TASK-019 | Add typing indicator: before sending each response segment, call `async with raw_message.channel.typing(): await asyncio.sleep(Config.PART_BREAK_DELAY)` between segments (not after last) | `gateway/adapters/discord/handler.py` | TASK-017 | ☐ | |
| TASK-020 | Add import for `underthesea.sent_tokenize` and `Config` at top of handler file | `gateway/adapters/discord/handler.py` | TASK-018, TASK-019 | ☐ | |
| TASK-021 | Wire `_send_response()` result back through the handler return path — instead of returning raw string, send via raw channel and return empty string (gateway already handles the send) | `gateway/adapters/discord/handler.py` | TASK-017 | ☐ | |

### Phase 5: Update gateway routing to skip adapter send_message for Discord
**Goal**: GOAL-005 — Gateway's `route_message()` does not double-send for Discord since the handler now sends directly via raw channel

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| TASK-022 | Modify `handle_message()` return semantics: return `None` or a sentinel when handler sends directly (via raw channel), so gateway `route_message()` skips its own `adapter.send_message()` call | `gateway/adapters/discord/handler.py` | Phase 4 | ☐ | |
| TASK-023 | Update `ChatGateway.route_message()` to check for `None`/empty response before calling `adapter.send_message()` — already has `if response_text and response_text.strip():` guard, so returning `""` suffices | `gateway/gateway.py` | TASK-022 | ☐ | |

## Alternatives Considered

- **ALT-001**: Move filtering logic entirely into the adapter's `_register_events()` instead of the handler. **Rejected** — the handler is the correct layer for business logic (filtering, chunking), keeping the adapter thin as a transport bridge. Mixing filtering into the adapter would violate separation of concerns and make testing harder.
- **ALT-002**: Create a new `DiscordUnifiedMessage` subclass with `is_mentioned` and `raw_message` fields. **Rejected** — `UnifiedMessage` is a frozen dataclass used across all platforms. Adding platform-specific fields via `extensions` dict is the established pattern and avoids breaking other adapters.
- **ALT-003**: Have the gateway handler import the original `ChatGateway` cog and delegate to its `on_message()`. **Rejected** — the cog expects `discord.Message` and `commands.Context` which creates tight coupling. The handler must replicate the logic using the unified model + raw message escape hatch.

## Dependencies

- **DEP-001**: `discord.ext.commands.Bot.load_extension()` — used to load cogs dynamically at runtime
- **DEP-002**: `underthesea.sent_tokenize` — Vietnamese sentence tokenizer used in `_chunk_text()`, already in `requirements.txt`
- **DEP-003**: `src.config.settings.Config.PART_BREAK_DELAY` — float config value for inter-message delay (default 0.6s)
- **DEP-004**: `src.cogs.admin_channels.AdminChannels.is_bot_channel(guild_id, channel_id)` — must be available after cog load
- **DEP-005**: `src.tasks.nightly_trigger.NightlyTrigger.start()` — async method that creates background task loop
- **DEP-006**: `src.services.dependencies.AppContainer` — singleton container initialized before cog loading

## Affected Files

- **FILE-001**: `gateway/adapters/discord/converter.py` — modify `DiscordMessageConverter.to_unified()` to accept `bot_user` parameter, store `is_mentioned` and raw `discord.Message` in extensions
- **FILE-002**: `gateway/adapters/discord/adapter.py` — modify `_register_events()` to add command filter, mention stripping, pass bot_user to converter; modify `connect()` to load cogs and start NightlyTrigger
- **FILE-003**: `gateway/adapters/discord/handler.py` — add channel/mention/DM filtering, `_send_response()`, `_chunk_text()`, typing indicator, Vietnamese error message, imports for `sent_tokenize` and `Config`
- **FILE-004**: `gateway/shared/model.py` — no changes needed (extensions dict already exists for this purpose)

## Testing Strategy

- **TEST-001**: Unit test — `DiscordMessageConverter.to_unified()` stores `is_mentioned` correctly when bot is in `message.mentions` — mock `discord.Message` with/without mentions
- **TEST-002**: Unit test — `_chunk_text()` produces correct output for: (a) text under 1900 chars, (b) text over 1900 chars with newlines, (c) single long line over 1900 chars requiring `sent_tokenize` split
- **TEST-003**: Unit test — handler filtering logic returns `""` for: (a) non-DM non-mention non-approved-channel message, (b) empty content after mention stripping
- **TEST-004**: Integration test — verify `AdminChannels` cog is loaded after `adapter.connect()` by checking `bot.get_cog("AdminChannels")` is not None
- **TEST-005**: Integration test — verify `NightlyTrigger` is started after `adapter.connect()` by checking `container.nightly_trigger.is_running()` is True
- **TEST-006**: Integration test — send a message with `!ping` content and verify it is NOT forwarded to gateway (ctx.valid check)
- **TEST-007**: Manual test — send a 3000+ character message to bot and verify it is chunked into multiple Discord messages, each under 2000 chars
- **TEST-008**: Manual test — send a message that triggers coordinator error and verify Vietnamese error message is received in Discord

## Risks

- **RISK-001**: Storing raw `discord.Message` in `UnifiedMessage.extensions` creates a memory leak if messages are queued for long periods — Impact: Medium, Likelihood: Low, Mitigation: The gateway processes messages immediately; no long-term queuing exists in current architecture
- **RISK-002**: Loading cogs in `connect()` may conflict with cog state if `connect()` is called multiple times (e.g., reconnection) — Impact: High, Likelihood: Medium, Mitigation: discord.py's `load_extension()` raises `ExtensionAlreadyLoaded` if called twice; wrap in try/except and catch that specific exception to make it idempotent
- **RISK-003**: `NightlyTrigger.start()` creates an `asyncio.Task` — if `disconnect()` is called, the task is never cancelled — Impact: Medium, Likelihood: Medium, Mitigation: Store reference to the nightly trigger task in adapter and call `container.nightly_trigger.stop()` in `disconnect()`
- **RISK-004**: The `_chunk_text()` method depends on `underthesea.sent_tokenize` which may not handle all edge cases (e.g., mixed English/Vietnamese text) — Impact: Low, Likelihood: Low, Mitigation: This is existing behavior from the original cog; any bugs here predate this change

## Assumptions

- **ASSUMPTION-001**: The `CoreBot` instance passed to `DiscordPlatformAdapter` is the same instance used by `AppContainer` — verified by reading `adapter.py` `connect()` which calls `AppContainer.get_instance()` independently
- **ASSUMPTION-002**: The `UnifiedMessage.extensions` dict is the intended escape hatch for platform-specific data — confirmed by docstring "Platform-specific extra data (e.g. Discord embeds, Zalo stickers)"
- **ASSUMPTION-003**: The gateway's `route_message()` already guards against empty responses (`if response_text and response_text.strip():`), so returning `""` from handler when filtering skips processing will prevent double-sends
- **ASSUMPTION-004**: Guild ID is available from the raw `discord.Message` — confirmed as `message.guild.id` when `message.guild` is not None

## Related Resources

- Original cog: `src/cogs/chat_gateway.py` — reference for message filtering, response sending, chunking
- Admin channels cog: `src/cogs/admin_channels.py` — reference for `is_bot_channel()` method
- User commands cog: `src/cogs/user_commands.py` — reference for `!ping`, `!status` commands
- Bot setup: `src/bot.py` — reference for cog loading order and NightlyTrigger startup
- Nightly trigger: `src/tasks/nightly_trigger.py` — reference for `start()`/`stop()` lifecycle
- Gateway router: `gateway/gateway.py` — reference for `route_message()` flow
- Unified model: `gateway/shared/model.py` — reference for `UnifiedMessage.extensions` field
