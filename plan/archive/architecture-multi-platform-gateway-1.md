---
goal: Refactor Discord bot into a multi-platform chat gateway supporting Discord, Zalo, and future platforms
version: '1.0'
date_created: '2026-05-05'
last_updated: '2026-05-05'
owner: flowerf
status: 'Planned'
tags:
  - architecture
  - refactor
  - multi-platform
  - gateway
  - discord
  - zalo
---

# Refactor Discord Bot into Multi-Platform Chat Gateway

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

## Overview

Transform the current single-platform Discord bot (`src/bot.py`, `src/cogs/`) into a multi-platform chat gateway architecture that routes messages between Discord, Zalo, and future platforms through a unified, platform-agnostic core. The existing `ChatCoordinator`, `MemoryManager`, `LLMService`, and `MCPClient` remain untouched as the platform-agnostic brain. Only the input/output layer (currently Discord-specific cogs) is restructured into platform adapters.

## Requirements

- **REQ-001**: All platform-agnostic logic (ChatCoordinator, MemoryManager, LLM services, MCP tools, memory system) remains unchanged in `src/`
- **REQ-002**: Define platform-agnostic message models (UnifiedMessage, UnifiedUser, UnifiedChannel, UnifiedEvent) in `gateway/shared/model.py`
- **REQ-003**: Create a core gateway orchestrator in `gateway.py` that manages adapter lifecycle and routes messages
- **REQ-004**: Implement Discord adapter in `gateway/adapters/discord/` that wraps existing `CoreBot` and cogs
- **REQ-005**: Implement Zalo adapter scaffold in `gateway/adapters/zalo/` with connection stubs
- **REQ-006**: Platform adapters must translate between platform-specific formats and unified models in both directions
- **REQ-007**: Gateway must support hot-reload/reconnection of individual platform adapters without affecting others
- **REQ-008**: Backward compatibility: running `python3 -m src` must still start the Discord bot with identical behavior
- **REQ-009**: New entry point `python3 -m gateway` starts the multi-platform gateway with all configured adapters
- **REQ-010**: Platform-specific features (Discord embeds, Zalo rich messages) must be expressible via optional extension fields on unified models

## Constraints & Guidelines

- **CON-001**: Do not modify `src/services/chat_coordinator.py`, `src/services/dependencies.py`, `src/services/memories/`, `src/services/llm/`, `src/services/tools/`, `src/agents/` — these are the shared brain
- **CON-002**: The Discord adapter must reuse the existing `CoreBot` class and `AppContainer` singleton, not duplicate connection logic
- **CON-003**: Zalo API SDK (`zalo-api` or equivalent) is not yet integrated; scaffold only with placeholder connection logic
- **CON-004**: No changes to `.env` variable names for existing Discord config; new platform variables use `ZALO_` prefix
- **GUD-001**: Use Python `abc.ABC` and `@abstractmethod` for platform adapter interface definitions
- **GUD-002**: Use `dataclasses.dataclass` for unified message models with `Optional` extension fields
- **GUD-003**: Each adapter lives in its own sub-package under `gateway/adapters/<platform>/` with `__init__.py`, `adapter.py`, and `converter.py`
- **GUD-004**: Error handling per adapter must be isolated — one adapter crashing must not take down the gateway or other adapters
- **PAT-001**: Adapter pattern for platform-specific implementations
- **PAT-002**: Strategy pattern for message conversion (platform ↔ unified)
- **PAT-003**: Observer pattern for event dispatching from adapters to gateway handlers

## Implementation Phases

### Phase 1: Define Unified Models and Adapter Interface
**Goal**: GOAL-001 Create platform-agnostic message models and abstract adapter interface that all platform adapters must implement

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| TASK-001 | Create `gateway/__init__.py` with package docstring | `gateway/__init__.py` | None | ☐ | |
| TASK-002 | Create `gateway/shared/__init__.py` | `gateway/shared/__init__.py` | TASK-001 | ☐ | |
| TASK-003 | Define `UnifiedUser` dataclass with fields: platform_id, platform_name, display_name, avatar_url, is_bot, raw_data: Optional[dict] | `gateway/shared/model.py` | TASK-002 | ☐ | |
| TASK-004 | Define `UnifiedChannel` dataclass with fields: channel_id, platform_name, channel_type (dm/group/guild/thread), name, raw_data: Optional[dict] | `gateway/shared/model.py` | TASK-003 | ☐ | |
| TASK-005 | Define `UnifiedMessage` dataclass with fields: message_id, user: UnifiedUser, channel: UnifiedChannel, content, timestamp, attachments: list[dict], mentions: list[UnifiedUser], reply_to: Optional[str], extensions: Optional[dict], raw_data: Optional[dict] | `gateway/shared/model.py` | TASK-004 | ☐ | |
| TASK-006 | Define `UnifiedEvent` enum with values: MESSAGE, EDIT, DELETE, REACTION_ADD, REACTION_REMOVE, JOIN, LEAVE, TYPING | `gateway/shared/model.py` | TASK-005 | ☐ | |
| TASK-007 | Define `PlatformAdapter` abstract base class with abstract methods: `connect()`, `disconnect()`, `send_message(msg: UnifiedMessage) -> str`, `is_connected -> bool`, and optional hook methods: `on_message`, `on_edit`, `on_delete` | `gateway/shared/adapter_base.py` | TASK-006 | ☐ | |
| TASK-008 | Define `GatewayHandler` abstract base class with abstract method `handle_message(msg: UnifiedMessage) -> str` and `handle_event(event: UnifiedEvent, msg: UnifiedMessage) -> None` | `gateway/shared/handler_base.py` | TASK-007 | ☐ | |
| TASK-009 | Write unit tests for model creation and serialization | `tests/gateway/test_models.py` | TASK-008 | ☐ | |

### Phase 2: Create Gateway Orchestrator
**Goal**: GOAL-002 Build the core gateway that manages adapter lifecycle, routes messages to handlers, and handles cross-platform message translation

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| TASK-010 | Create `gateway/__init__.py` | `gateway/__init__.py` | TASK-009 | ☐ | |
| TASK-011 | Implement `ChatGateway` class with: `_adapters: dict[str, PlatformAdapter]`, `_handler: GatewayHandler`, register_adapter(name, adapter), unregister_adapter(name), route_message(platform_name, raw_message), start_all(), stop_all() | `gateway/gateway.py` | TASK-010 | ☐ | |
| TASK-012 | Implement per-adapter error isolation: wrap each adapter's send/receive in try/except with logging; log adapter crashes without propagating | `gateway/gateway.py` | TASK-011 | ☐ | |
| TASK-013 | Implement async reconnection loop per adapter: on disconnect, attempt reconnection with exponential backoff (max 5 retries, 2s base) | `gateway/gateway.py` | TASK-012 | ☐ | |
| TASK-014 | Create `gateway/config.py` with `GatewayConfig` dataclass: enabled_platforms: list[str], platform-specific config dicts | `gateway/config.py` | TASK-011 | ☐ | |
| TASK-015 | Create `gateway/__main__.py` entry point: parse config, instantiate gateway, register adapters, call start_all(), handle SIGINT/SIGTERM for graceful shutdown | `gateway/__main__.py` | TASK-013, TASK-014 | ☐ | |
| TASK-016 | Write unit tests for gateway adapter registration and message routing with mock adapters | `tests/gateway/test_gateway.py` | TASK-015 | ☐ | |

### Phase 3: Implement Discord Adapter
**Goal**: GOAL-003 Wrap existing Discord bot (`CoreBot`, cogs, `AppContainer`) as a PlatformAdapter that translates between discord.py objects and UnifiedMessage models

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| TASK-017 | Create `gateway/adapters/__init__.py` | `gateway/adapters/__init__.py` | TASK-009 | ☐ | |
| TASK-018 | Create `gateway/adapters/discord/__init__.py` | `gateway/adapters/discord/__init__.py` | TASK-017 | ☐ | |
| TASK-019 | Implement `DiscordMessageConverter` with static methods: `to_unified(discord_msg: discord.Message) -> UnifiedMessage`, `from_unified(unified_msg: UnifiedMessage) -> dict` (returns kwargs for discord.TextChannel.send) | `gateway/adapters/discord/converter.py` | TASK-018 | ☐ | |
| TASK-020 | Implement `DiscordUserConverter` with static method: `to_unified(user: discord.User) -> UnifiedUser` | `gateway/adapters/discord/converter.py` | TASK-019 | ☐ | |
| TASK-021 | Implement `DiscordChannelConverter` with static method: `to_unified(channel: discord.abc.GuildChannel | discord.DMChannel) -> UnifiedChannel` | `gateway/adapters/discord/converter.py` | TASK-020 | ☐ | |
| TASK-022 | Implement `DiscordPlatformAdapter` extending `PlatformAdapter`: `__init__` accepts existing `CoreBot` instance; `connect()` calls `bot.start(token)`; `disconnect()` calls `bot.close()`; `send_message()` uses converter + channel.send; `is_connected` checks `bot.is_ready()` | `gateway/adapters/discord/adapter.py` | TASK-019, TASK-020, TASK-021 | ☐ | |
| TASK-023 | Wire `DiscordPlatformAdapter.on_message` to receive `discord.Message` events, convert via `DiscordMessageConverter.to_unified`, then call `self._gateway.route_message("discord", unified_msg)` | `gateway/adapters/discord/adapter.py` | TASK-022 | ☐ | |
| TASK-024 | Refactor `src/cogs/chat_gateway.py` `ChatGateway` cog to accept a `UnifiedMessage` from the adapter instead of directly reading `discord.Message`; move message routing logic into a new `DiscordGatewayHandler` class in `gateway/adapters/discord/handler.py` | `gateway/adapters/discord/handler.py`, `src/cogs/chat_gateway.py` | TASK-023 | ☐ | |
| TASK-025 | Create `DiscordGatewayHandler` extending `GatewayHandler`: `handle_message()` calls `AppContainer.get_instance().chat_coordinator.process_message()`, then converts response back to Discord format and sends via adapter | `gateway/adapters/discord/handler.py` | TASK-024 | ☐ | |
| TASK-026 | Ensure backward compatibility: `python3 -m src` still works identically by keeping `src/bot.py` `main()` unchanged; the Discord adapter is an alternative entry point, not a replacement | `src/bot.py` (no changes), verified by test | TASK-025 | ☐ | |
| TASK-027 | Write integration tests: send mock discord.Message through adapter → verify UnifiedMessage produced → verify response sent | `tests/gateway/adapters/test_discord_adapter.py` | TASK-025 | ☐ | |

### Phase 4: Implement Zalo Adapter Scaffold
**Goal**: GOAL-004 Create a functional Zalo adapter scaffold with connection stubs, message converters, and platform-specific extension support

| ID | Task | File(s) | Dependencies | Status | Completed |
| Completed |
| TASK-028 | Create `gateway/adapters/zalo/__init__.py` | `gateway/adapters/zalo/__init__.py` | TASK-017 | ☐ | |
| TASK-029 | Define `ZaloMessageExtension` dataclass for Zalo-specific fields: msg_type (text/photo/sticker/file), sticker_id, photo_url, file_url | `gateway/adapters/zalo/model.py` | TASK-028 | ☐ | |
| TASK-030 | Implement `ZaloMessageConverter` with static methods: `to_unified(zalo_msg: dict) -> UnifiedMessage`, `from_unified(unified_msg: UnifiedMessage) -> dict` (returns Zalo API request body) | `gateway/adapters/zalo/converter.py` | TASK-029 | ☐ | |
| TASK-031 | Implement `ZaloUserConverter` with static method: `to_unified(zalo_user: dict) -> UnifiedUser` | `gateway/adapters/zalo/converter.py` | TASK-030 | ☐ | |
| TASK-032 | Implement `ZaloPlatformAdapter` extending `PlatformAdapter`: `__init__` accepts `access_token`, `app_id`; `connect()` stubs HTTP session creation and logs "Zalo adapter connected (stub)"; `disconnect()` closes session; `send_message()` logs and returns stub response; `is_connected` returns True after connect | `gateway/adapters/zalo/adapter.py` | TASK-030, TASK-031 | ☐ | |
| TASK-033 | Implement `ZaloEventHandler` extending `GatewayHandler`: stub implementation that logs all events and returns placeholder response | `gateway/adapters/zalo/handler.py` | TASK-032 | ☐ | |
| TASK-034 | Add `ZALO_ACCESS_TOKEN`, `ZALO_APP_ID`, `ZALO_ENABLED` to `.env.example` and `GatewayConfig` | `.env.example`, `gateway/config.py` | TASK-032 | ☐ | |
| TASK-035 | Write unit tests for Zalo converter round-trip (dict → UnifiedMessage → dict) | `tests/gateway/adapters/test_zalo_converter.py` | TASK-030 | ☐ | |

### Phase 5: Integration, Testing, and Documentation
**Goal**: GOAL-005 Wire all components together, verify end-to-end message flow, and update documentation

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| TASK-036 | Create `gateway/adapters/factory.py` with `create_adapter(platform: str, config: dict) -> PlatformAdapter` factory function supporting "discord" and "zalo" | `gateway/adapters/factory.py` | TASK-025, TASK-032 | ☐ | |
| TASK-037 | Update `gateway/__main__.py` to use adapter factory and register all enabled adapters from config | `gateway/__main__.py` | TASK-036 | ☐ | |
| TASK-038 | Create end-to-end integration test: mock Discord message → gateway → handler → mock response → verify sent back | `tests/gateway/test_integration.py` | TASK-027, TASK-035 | ☐ | |
| TASK-039 | Add pytest configuration for gateway tests in `pytest.ini` (if not already compatible) | `pytest.ini` | TASK-038 | ☐ | |
| TASK-040 | Update `README.md` with multi-platform gateway architecture section, new entry points, and adapter development guide | `README.md` | TASK-038 | ☐ | |
| TASK-041 | Create `gateway/README.md` with adapter development tutorial, model reference, and extension guide | `gateway/README.md` | TASK-038 | ☐ | |
| TASK-042 | Verify `python3 -m src` still starts Discord bot with identical behavior (manual smoke test) | N/A | TASK-026 | ☐ | |
| TASK-043 | Verify `python3 -m gateway` starts gateway with Discord adapter and processes messages end-to-end (manual smoke test) | N/A | TASK-037, TASK-038 | ☐ | |

## Alternatives Considered

- **ALT-001**: Rewrite the entire bot from scratch with new framework — Rejected because the existing `ChatCoordinator`, memory system, and MCP tools are mature and working. The goal is to refactor only the I/O layer, not the brain.
- **ALT-002**: Use a single monolithic bot class with platform conditionals (`if platform == "discord": ...`) — Rejected because it violates open-closed principle; adding a new platform would require modifying core code. The adapter pattern allows adding platforms without touching existing code.
- **ALT-003**: Use an existing multi-platform bot framework (e.g., BotFramework, Matrix bridge) — Rejected because these frameworks impose their own message models and constraints. The custom adapter pattern gives full control over platform-specific features (Discord embeds, Zalo stickers) while maintaining a clean unified core.

## Dependencies

- **DEP-001**: `discord.py>=2.0` — Already in `requirements.txt`; used by Discord adapter for connection and message handling
- **DEP-002**: `aiohttp` — Already in `requirements.txt`; used by Zalo adapter for HTTP session management
- **DEP-003**: Zalo API Python SDK (TBD) — Not yet available; adapter uses raw HTTP calls via aiohttp as placeholder until SDK is identified
- **DEP-004**: Python 3.10+ — Required for `dataclasses.dataclass(kw_only=True)` if used; verify project's Python version supports it
- **DEP-005**: Existing `AppContainer` singleton in `src/services/dependencies.py` — Used by Discord handler to access `ChatCoordinator`

## Affected Files

- **FILE-001**: `gateway/__init__.py` — create — Package initialization
- **FILE-002**: `gateway/shared/__init__.py` — create — Shared module initialization
- **FILE-003**: `gateway/shared/model.py` — create — Unified message models (UnifiedUser, UnifiedChannel, UnifiedMessage, UnifiedEvent)
- **FILE-004**: `gateway/shared/adapter_base.py` — create — Abstract PlatformAdapter base class
- **FILE-005**: `gateway/shared/handler_base.py` — create — Abstract GatewayHandler base class
- **FILE-006**: `gateway/__init__.py` — create — Gateway package initialization
- **FILE-007**: `gateway/gateway.py` — create — ChatGateway orchestrator class
- **FILE-008**: `gateway/config.py` — create — GatewayConfig dataclass
- **FILE-009**: `gateway/__main__.py` — create — Gateway entry point (`python3 -m gateway`)
- **FILE-010**: `gateway/adapters/__init__.py` — create — Adapters package initialization
- **FILE-011**: `gateway/adapters/factory.py` — create — Adapter factory function
- **FILE-012**: `gateway/adapters/discord/__init__.py` — create — Discord adapter package
- **FILE-013**: `gateway/adapters/discord/converter.py` — create — Discord ↔ Unified converters
- **FILE-014**: `gateway/adapters/discord/adapter.py` — create — DiscordPlatformAdapter implementation
- **FILE-015**: `gateway/adapters/discord/handler.py` — create — DiscordGatewayHandler implementation
- **FILE-016**: `gateway/adapters/zalo/__init__.py` — create — Zalo adapter package
- **FILE-017**: `gateway/adapters/zalo/model.py` — create — Zalo-specific extension models
- **FILE-018**: `gateway/adapters/zalo/converter.py` — create — Zalo ↔ Unified converters
- **FILE-019**: `gateway/adapters/zalo/adapter.py` — create — ZaloPlatformAdapter stub implementation
- **FILE-020**: `gateway/adapters/zalo/handler.py` — create — ZaloEventHandler stub implementation
- **FILE-021**: `gateway/README.md` — create — Adapter development documentation
- **FILE-022**: `.env.example` — modify — Add ZALO_* environment variables
- **FILE-023**: `pytest.ini` — modify — Add gateway test path configuration
- **FILE-024**: `README.md` — modify — Add multi-platform architecture section
- **FILE-025**: `tests/gateway/test_models.py` — create — Unit tests for unified models
- **FILE-026**: `tests/gateway/test_gateway.py` — create — Unit tests for gateway orchestrator
- **FILE-027**: `tests/gateway/adapters/test_discord_adapter.py` — create — Integration tests for Discord adapter
- **FILE-028**: `tests/gateway/adapters/test_zalo_converter.py` — create — Unit tests for Zalo converters
- **FILE-029**: `tests/gateway/test_integration.py` — create — End-to-end integration tests
- **FILE-030**: `src/cogs/chat_gateway.py` — modify — Minor refactor to accept UnifiedMessage from adapter (backward-compatible wrapper added)

## Testing Strategy

- **TEST-001**: Unit tests for unified model creation, serialization, and deserialization — verify all dataclass fields accept valid inputs and `raw_data`/`extensions` accept `None` — `tests/gateway/test_models.py` — pytest — 100% coverage of `gateway/shared/model.py`
- **TEST-002**: Unit tests for `PlatformAdapter` and `GatewayHandler` abstract base classes — verify instantiation fails for unimplemented abstract methods — `tests/gateway/test_gateway.py` — pytest
- **TEST-003**: Unit tests for `ChatGateway` adapter registration, unregistration, and message routing with mock adapters — verify error isolation (mock adapter raising exception does not crash gateway) — `tests/gateway/test_gateway.py` — pytest — 90% coverage of `gateway/gateway.py`
- **TEST-004**: Unit tests for Discord converters: `to_unified` with mock `discord.Message` → verify `UnifiedMessage` fields populated correctly; `from_unified` → verify kwargs dict compatible with `channel.send()` — `tests/gateway/adapters/test_discord_adapter.py` — pytest — 90% coverage of `gateway/adapters/discord/converter.py`
- **TEST-005**: Unit tests for Zalo converters: round-trip `dict → UnifiedMessage → dict` — verify Zalo-specific extensions preserved — `tests/gateway/adapters/test_zalo_converter.py` — pytest — 90% coverage of `gateway/adapters/zalo/converter.py`
- **TEST-006**: Integration test: mock Discord message → `DiscordPlatformAdapter` → `ChatGateway` → `DiscordGatewayHandler` → mock `ChatCoordinator` response → verify message sent back — `tests/gateway/test_integration.py` — pytest-asyncio
- **TEST-007**: Backward compatibility smoke test: run `python3 -m src` → verify bot connects and responds to messages identically to pre-refactor behavior — manual verification + pytest test that imports `src.bot` without side effects

## Risks

- **RISK-001**: discord.py internal APIs may change, breaking converters that rely on specific `discord.Message` attributes — Impact: Medium, Likelihood: Low, Mitigation: Pin `discord.py>=2.0,<3.0` in requirements; use only documented public attributes in converters
- **RISK-002**: Zalo API details are unknown, making the adapter a pure stub — Impact: Low, Likelihood: High, Mitigation: Design converter interface to accept `dict` (raw JSON) rather than a specific Zalo SDK type, allowing easy integration when API details are available
- **RISK-003**: Refactoring `ChatGateway` cog could break existing Discord bot behavior — Impact: High, Likelihood: Medium, Mitigation: Keep `src/bot.py` and `src/cogs/` unchanged for `python3 -m src` entry point; the new adapter is an alternative path, tested side-by-side before any cutover
- **RISK-004**: Circular imports between `gateway/` and `src/` (gateway handler imports AppContainer from src) — Impact: Medium, Likelihood: Medium, Mitigation: Use lazy imports inside handler methods rather than top-level imports; verify with `python -c "import gateway"` import test

## Assumptions

- **ASSUMPTION-001**: The existing `ChatCoordinator.process_message(user_id, content) -> str` signature is sufficient for all platforms; no platform needs additional context (e.g., guild_id, channel_type) in the core processing pipeline
- **ASSUMPTION-002**: Zalo provides a REST API or webhook mechanism for receiving and sending messages; specific API details will be provided in a future iteration
- **ASSUMPTION-003**: The `AppContainer` singleton initialization time (< 10s) is acceptable for the gateway startup sequence
- **ASSUMPTION-004**: No platform requires real-time streaming responses (all platforms use request-response message pattern)
- **ASSUMPTION-005**: The project uses Python 3.10+ (required for modern dataclass features); if not, dataclass fields will use `field(default=None)` pattern instead of `kw_only=True`

## Related Resources

- discord.py documentation: https://discordpy.readthedocs.io/en/stable/
- Zalo API documentation: https://developers.zalo.me/docs/ (pending specific API access details)
- Existing project README: `/home/flowerf/Projects/discord-bot-v1/README.MD`
- Adapter pattern reference: https://refactoring.guru/design-patterns/adapter
- Python ABC module: https://docs.python.org/3/library/abc.html
