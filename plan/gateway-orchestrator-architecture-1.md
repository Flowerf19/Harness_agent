---
goal: Refactor Discord bot into a proper Gateway Orchestrator architecture with gateway as the sole entry point
version: "1.0"
date_created: "2026-05-06"
last_updated: "2026-05-06"
owner: flowerf
status: 'Planned'
tags: [architecture, refactor, gateway, discord, orchestrator]
---

# Gateway Orchestrator Architecture Refactor

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

## Overview

Refactor the current codebase so that `python3 -m gateway` is the only supported entry point. CoreBot becomes a thin discord.py wrapper inside the Discord adapter. Standalone mode (`python3 -m src`) is deprecated. Cogs remain Discord-specific but are loaded exclusively through the adapter, not CoreBot's `setup_hook`. The shared brain (`src/services/`) remains unchanged.

## Requirements

- **REQ-001**: `python3 -m gateway` must be the sole supported entry point; standalone `python3 -m src` must emit deprecation warnings
- **REQ-002**: CoreBot class must remain functional as a thin discord.py wrapper for the Discord adapter
- **REQ-003**: All 5 cogs (chat_gateway, user_commands, admin_channels, base_cog, server_relationships) must load through DiscordPlatformAdapter, not CoreBot.setup_hook
- **REQ-004**: DiscordGatewayHandler must access AdminChannels cog via `get_cog("AdminChannels")` without breaking
- **REQ-005**: NightlyTrigger (2 AM consolidation) must start in gateway mode and stop on adapter disconnect
- **REQ-006**: AppContainer must initialize before cogs load in gateway mode
- **REQ-007**: Gateway mode must produce identical behavior to the old standalone mode (same features, same responses)
- **REQ-008**: README.MD must document gateway as the primary entry point and mark standalone mode as deprecated
- **REQ-009**: Docker Compose must default to gateway mode without ambiguity

## Constraints & Guidelines

- **CON-001**: DO NOT modify any file under `src/services/` — the shared brain stays as-is
- **CON-002**: DO NOT remove CoreBot entirely — the Discord adapter requires it
- **CON-003**: DO NOT change cog functionality — only modify where/how they load
- **CON-004**: Keep all Vietnamese logging messages unchanged
- **GUD-001**: Use lazy imports in adapter.py to avoid circular dependencies between src/ and gateway/
- **GUD-002**: Maintain backward compatibility: standalone mode should still work but warn, not break
- **PAT-001**: Adapter pattern — DiscordPlatformAdapter wraps CoreBot and overrides setup_hook to prevent double initialization
- **PAT-002**: Gateway pattern — ChatGateway orchestrates adapters and routes messages to a handler

## Implementation Phases

### Phase 1: Deprecate Standalone Mode
**Goal**: GOAL-001 CoreBot becomes a thin wrapper; standalone mode emits deprecation warnings

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| TASK-001 | Remove cog loading from `CoreBot.setup_hook()` — keep only AppContainer init and NightlyTrigger start for standalone fallback | `src/bot.py` | None | ☐ | |
| TASK-002 | Add deprecation warning to `CoreBot.__init__()` logging `"⚠️ Standalone mode is deprecated. Use 'python3 -m gateway' instead."` | `src/bot.py` | TASK-001 | ☐ | |
| TASK-003 | Add deprecation warning to `main()` function in bot.py before bot instantiation | `src/bot.py` | TASK-002 | ☐ | |
| TASK-004 | Update `src/__main__.py` to emit deprecation warning before calling `main()` | `src/__main__.py` | TASK-003 | ☐ | |

**Verification**: Run `python3 -m src` — bot starts but prints deprecation warnings. Run `python3 -m gateway` — no deprecation warnings appear.

### Phase 2: Clarify Gateway as Primary Entry Point
**Goal**: GOAL-002 All documentation and Docker configuration point to gateway as the sole entry point

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| TASK-005 | Update README.MD Quick Start: change `python -m src.bot` to `python3 -m gateway` | `README.MD` | None | ☐ | |
| TASK-006 | Add "Architecture Evolution" section to README.MD explaining the gateway pattern, with mermaid diagram showing Gateway → Adapters → Shared Brain | `README.MD` | TASK-005 | ☐ | |
| TASK-007 | Mark standalone mode as deprecated in README.MD with a callout box | `README.MD` | TASK-006 | ☐ | |
| TASK-008 | Update project structure tree in README.MD to show cogs under `gateway/adapters/discord/cogs/` instead of `src/cogs/` | `README.MD` | TASK-005 | ☐ | |
| TASK-009 | Update `docker/docker-compose.bot.yml` default: set `ENTRYPOINT_CMD=gateway` as the only documented path, remove the `else` branch referencing `python src/bot.py` | `docker/docker-compose.bot.yml` | None | ☐ | |
| TASK-010 | Update `docker/Dockerfile` CMD to default to `python -m gateway` only, remove the `else` branch for `python src/bot.py` | `docker/Dockerfile` | TASK-009 | ☐ | |

**Verification**: README.MD Quick Start instructions reference `python3 -m gateway` only. Docker Compose and Dockerfile both default to gateway mode.

### Phase 3: Verify Gateway Adapter Integrity
**Goal**: GOAL-003 Confirm all gateway components wire together correctly and produce identical behavior to standalone mode

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| TASK-011 | Verify `DiscordPlatformAdapter._gateway_setup_hook()` loads all 5 cogs in correct order: admin_channels, base_cog, chat_gateway, user_commands, server_relationships | `gateway/adapters/discord/adapter.py` | None | ☐ | |
| TASK-012 | Verify `DiscordGatewayHandler._get_bot().get_cog("AdminChannels")` returns a valid cog instance after adapter setup | `gateway/adapters/discord/handler.py` | TASK-011 | ☐ | |
| TASK-013 | Verify NightlyTrigger starts in `_gateway_setup_hook()` via `container.nightly_trigger.start()` and stops in `adapter.disconnect()` | `gateway/adapters/discord/adapter.py` | None | ☐ | |
| TASK-014 | Verify AppContainer initializes before cog loading in `_gateway_setup_hook()` (container.initialize() called before any `load_extension()`) | `gateway/adapters/discord/adapter.py` | None | ☐ | |
| TASK-015 | Verify `DiscordGatewayHandler._bot` class attribute is set by adapter after cog loading completes | `gateway/adapters/discord/adapter.py`, `gateway/adapters/discord/handler.py` | TASK-011 | ☐ | |
| TASK-016 | Verify `_create_discord_adapter()` in factory.py creates CoreBot and wraps it in DiscordPlatformAdapter with gateway reference | `gateway/adapters/factory.py` | None | ☐ | |

**Verification**: Start gateway with `python3 -m gateway`. Check logs for: (1) AppContainer initialized, (2) all 5 cogs loaded, (3) NightlyTrigger started, (4) handler bot reference set. Send a test message — bot responds identically to standalone mode.

### Phase 4: Clean Up Legacy Artifacts
**Goal**: GOAL-004 Remove dead code and clarify moved components

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| TASK-017 | Delete `src/cogs/__pycache__/` directory (already empty of source files) | `src/cogs/__pycache__/` | None | ☐ | |
| TASK-018 | Add `src/cogs/README.md` explaining cogs moved to `gateway/adapters/discord/cogs/` and this directory is legacy | `src/cogs/README.md` | TASK-017 | ☐ | |
| TASK-019 | Search for any remaining references to `src/cogs/` in code and documentation; update or remove them | `**/*.py`, `**/*.md`, `**/*.yml` | TASK-018 | ☐ | |
| TASK-020 | Verify no circular imports between `src/` and `gateway/` by running `python3 -c "import gateway; import src"` and checking for ImportError | Project root | TASK-019 | ☐ | |

**Verification**: `src/cogs/` contains only a README.md explaining the move. No Python files reference `src/cogs/`. `python3 -m gateway` starts without import errors.

## Alternatives Considered

- **ALT-001**: Remove CoreBot entirely and rewrite Discord adapter without discord.py Bot subclass.
  - **Why rejected**: CoreBot encapsulates discord.py intents, command_prefix, and close() lifecycle. Rewriting would duplicate logic and risk breaking the Discord connection. CoreBot as a thin wrapper is simpler and safer.
  - **Trade-off**: Retains a small amount of legacy coupling, but avoids a risky rewrite.

- **ALT-002**: Move cogs out of gateway/ into a shared `cogs/` directory at project root.
  - **Why rejected**: Cogs are inherently Discord-specific (they use `discord.ext.commands.Cog`, `discord.Message`, etc.). Placing them at the root would imply they are platform-agnostic, which is misleading.
  - **Trade-off**: Cogs stay under gateway/adapters/discord/, which correctly signals their platform-specific nature.

- **ALT-003**: Keep standalone mode as a first-class entry point alongside gateway.
  - **Why rejected**: Dual entry points create confusion, duplicate initialization logic, and make testing harder. The gateway pattern is the intended architecture.
  - **Trade-off**: Standalone mode is deprecated but still works for emergency debugging; users are guided toward gateway.

## Dependencies

- **DEP-001**: `discord.py` >= 2.0 — required for `commands.Bot`, `Intents`, `ExtensionAlreadyLoaded` exception
- **DEP-002**: `python-dotenv` — required for `.env` loading in both gateway and standalone modes
- **DEP-003**: `src/services/` modules (AppContainer, ChatCoordinator, NightlyTrigger, Memory system) — must remain unchanged per CON-001
- **DEP-004**: `gateway/shared/` base classes (PlatformAdapter, GatewayHandler, UnifiedMessage) — must remain unchanged as the adapter/handler contract

## Affected Files

- **FILE-001**: `src/bot.py` — modify — Remove cog loading from setup_hook, add deprecation warnings to __init__ and main()
- **FILE-002**: `src/__main__.py` — modify — Add deprecation warning before calling main()
- **FILE-003**: `README.MD` — modify — Update Quick Start, add Architecture Evolution section, deprecate standalone mode, update project structure
- **FILE-004**: `docker/docker-compose.bot.yml` — modify — Remove standalone mode reference, default to gateway
- **FILE-005**: `docker/Dockerfile` — modify — Remove standalone mode from CMD, default to gateway
- **FILE-006**: `src/cogs/__pycache__/` — delete — Remove empty pycache directory
- **FILE-007**: `src/cogs/README.md` — create — Explain cogs moved to gateway/adapters/discord/cogs/

## Testing Strategy

- **TEST-001**: Run `python3 -m src` and verify deprecation warnings appear in logs (check for "⚠️ Standalone mode is deprecated") — manual smoke test
- **TEST-002**: Run `python3 -m gateway` and verify NO deprecation warnings appear — manual smoke test
- **TEST-003**: Verify gateway logs show all 5 cogs loaded: "Loaded cog: gateway.adapters.discord.cogs.*" for each cog — manual smoke test
- **TEST-004**: Verify gateway logs show AppContainer initialized before cog loading — manual smoke test
- **TEST-005**: Verify gateway logs show NightlyTrigger started — manual smoke test
- **TEST-006**: Send a Discord message to the bot in gateway mode; verify response matches standalone mode behavior — manual E2E test
- **TEST-007**: Verify `python3 -c "import gateway; import src"` produces no ImportError — import validation
- **TEST-008**: Run existing test suite: `pytest tests/ -v` — regression test to ensure no breaking changes

## Risks

- **RISK-001**: Cog loading order change breaks AdminChannels cog availability for handler.
  - **Impact**: High, **Likelihood**: Low
  - **Mitigation**: Verify cog load order in adapter.py matches the order in original CoreBot.setup_hook(). AdminChannels loads first in both paths.

- **RISK-002**: AppContainer double-initialization in gateway mode (once in adapter, once in CoreBot).
  - **Impact**: High, **Likelihood**: Low
  - **Mitigation**: CoreBot.setup_hook is overridden by adapter's `_gateway_setup_hook` which sets `_setup_done` flag. AppContainer.get_instance() is a singleton — calling initialize() twice is safe but redundant. TASK-001 removes CoreBot's cog loading but keeps AppContainer init for standalone fallback only.

- **RISK-003**: Docker Compose environment variable `ENTRYPOINT_CMD` still references standalone mode as a valid option.
  - **Impact**: Medium, **Likelihood**: Medium
  - **Mitigation**: TASK-009 and TASK-010 remove the standalone branch from docker-compose.bot.yml and Dockerfile. Document that `ENTRYPOINT_CMD=gateway` is the only supported value.

- **RISK-004**: Handler's `_bot` class attribute remains `None` if adapter.connect() fails before setup completes.
  - **Impact**: Medium, **Likelihood**: Low
  - **Mitigation**: Handler checks `if self._get_bot() is None` implicitly via `admin_cog = self._get_bot().get_cog(...)`. The handler already has a fallback: if cog is None, `is_allowed_channel = True`. Add a None check before calling `get_cog()` to prevent AttributeError.

- **RISK-005**: Existing users running `python3 -m src` in production scripts may miss the deprecation warning.
  - **Impact**: Low, **Likelihood**: Medium
  - **Mitigation**: Deprecation warning is logged at WARNING level. Standalone mode still works. README explicitly marks it as deprecated. Future release can remove standalone mode entirely.

## Assumptions

- **ASSUMPTION-001**: The `src/cogs/` directory contains only `__pycache__/` and no source files (verified via list_directory).
- **ASSUMPTION-002**: All 5 cogs are currently loaded in gateway mode via `_gateway_setup_hook()` in adapter.py (verified via read_file).
- **ASSUMPTION-003**: The handler's `DiscordGatewayHandler._bot` class attribute is set by the adapter after cog loading (verified in adapter.py line: `DiscordGatewayHandler._bot = self._bot`).
- **ASSUMPTION-004**: AppContainer is a singleton — calling `initialize()` multiple times is safe (standard singleton pattern with `get_instance()`).
- **ASSUMPTION-005**: No external scripts or CI/CD pipelines depend on `python3 -m src` as the entry point.

## Related Resources

- `gateway/gateway.py` — ChatGateway orchestrator implementation
- `gateway/shared/adapter_base.py` — PlatformAdapter abstract base class
- `gateway/shared/handler_base.py` — GatewayHandler abstract base class
- `gateway/adapters/discord/adapter.py` — DiscordPlatformAdapter implementation
- `gateway/adapters/discord/handler.py` — DiscordGatewayHandler implementation
- `gateway/adapters/factory.py` — Adapter factory function
- `src/bot.py` — CoreBot class (legacy, to become thin wrapper)
- `src/services/dependencies.py` — AppContainer (shared brain, DO NOT modify)
