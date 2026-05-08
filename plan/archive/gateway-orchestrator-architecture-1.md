---
goal: Refactor Discord bot into a proper Gateway Orchestrator architecture with gateway as the sole entry point
version: "1.0"
date_created: "2026-05-06"
last_updated: "2026-05-06"
owner: flowerf
status: 'In Progress — Phases 1-4 done, Phase 5 (cleanup unused cogs) in progress'
tags: [architecture, refactor, gateway, discord, orchestrator]
---

# Gateway Orchestrator Architecture Refactor

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

## Overview

Refactor the current codebase so that `python3 -m gateway` is the only supported entry point. CoreBot becomes a thin discord.py wrapper inside the Discord adapter. Standalone mode (`python3 -m src`) is deprecated. Cogs remain Discord-specific but are loaded exclusively through the adapter, not CoreBot's `setup_hook`. The shared brain (`src/services/`) remains unchanged.

## Requirements

- **REQ-001**: `python3 -m gateway` must be the sole supported entry point; standalone `python3 -m src` must emit deprecation warnings
- **REQ-002**: CoreBot class must remain functional as a thin discord.py wrapper for the Discord adapter
- **REQ-003**: Only `admin_channels` cog must load through DiscordPlatformAdapter; other cogs (base_cog, chat_gateway, user_commands, server_relationships) removed as unused
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
| ~~TASK-011~~ | ~~Verify `DiscordPlatformAdapter._gateway_setup_hook()` loads all 5 cogs in correct order~~ | `gateway/adapters/discord/adapter.py` | None | ✅ | 2026-05-06 |
| ~~TASK-012~~ | ~~Verify `DiscordGatewayHandler._get_bot().get_cog("AdminChannels")` returns a valid cog instance~~ | `gateway/adapters/discord/handler.py` | ~~TASK-011~~ | ✅ | 2026-05-06 |
| ~~TASK-013~~ | ~~Verify NightlyTrigger starts in `_gateway_setup_hook()` via `container.nightly_trigger.start()`~~ | `gateway/adapters/discord/adapter.py` | None | ✅ | 2026-05-06 |
| ~~TASK-014~~ | ~~Verify AppContainer initializes before cog loading in `_gateway_setup_hook()`~~ | `gateway/adapters/discord/adapter.py` | None | ✅ | 2026-05-06 |
| ~~TASK-015~~ | ~~Verify `DiscordGatewayHandler._bot` class attribute is set by adapter after cog loading~~ | `gateway/adapters/discord/adapter.py`, `gateway/adapters/discord/handler.py` | ~~TASK-011~~ | ✅ | 2026-05-06 |
| ~~TASK-016~~ | ~~Verify `_create_discord_adapter()` in factory.py creates CoreBot and wraps it in DiscordPlatformAdapter~~ | `gateway/adapters/factory.py` | None | ✅ | 2026-05-06 |

**Verification**: ✅ Run `python3 -m gateway` — all checks passed. Docker rebuild successful. Bot online and responding.

### Phase 4: Clean Up Legacy Artifacts
**Goal**: GOAL-004 Remove dead code and clarify moved components

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| ~~TASK-017~~ | ~~Delete `src/cogs/__pycache__/` directory~~ | `src/cogs/__pycache__/` | None | ✅ | 2026-05-06 |
| ~~TASK-018~~ | ~~Add `src/cogs/README.md` explaining cogs moved~~ | `src/cogs/README.md` | ~~TASK-017~~ | ✅ | 2026-05-06 |
| ~~TASK-019~~ | ~~Search for any remaining references to `src/cogs/`~~ | `**/*.py`, `**/*.md`, `**/*.yml` | ~~TASK-018~~ | ✅ | 2026-05-06 |
| ~~TASK-020~~ | ~~Verify no circular imports between `src/` and `gateway/`~~ | Project root | ~~TASK-019~~ | ✅ | 2026-05-06 |

**Verification**: ✅ `src/cogs/` contains only README.md. No Python files reference `src/cogs/`. No import errors.

### Phase 5: Fix Double Response & Remove Unused Cogs
**Goal**: GOAL-005 Remove duplicate message handlers and unused cogs

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| ~~TASK-021~~ | ~~Remove `chat_gateway` from adapter cog loading (causes double response)~~ | `gateway/adapters/discord/adapter.py` | None | ✅ | 2026-05-06 |
| ~~TASK-022~~ | ~~Delete `gateway/adapters/discord/cogs/base_cog.py` (dead code)~~ | `gateway/adapters/discord/cogs/base_cog.py` | None | ✅ | 2026-05-06 |
| ~~TASK-023~~ | ~~Delete `gateway/adapters/discord/cogs/chat_gateway.py` (duplicate of handler)~~ | `gateway/adapters/discord/cogs/chat_gateway.py` | None | ✅ | 2026-05-06 |
| ~~TASK-024~~ | ~~Delete `gateway/adapters/discord/cogs/user_commands.py` (half-broken, low value)~~ | `gateway/adapters/discord/cogs/user_commands.py` | None | ✅ | 2026-05-06 |
| ~~TASK-025~~ | ~~Delete `gateway/adapters/discord/cogs/server_relationships.py` (unused)~~ | `gateway/adapters/discord/cogs/server_relationships.py` | None | ✅ | 2026-05-06 |
| ~~TASK-026~~ | ~~Update `cogs/__init__.py` to only load `admin_channels`~~ | `gateway/adapters/discord/cogs/__init__.py` | ~~TASK-022 to 025~~ | ✅ | 2026-05-06 |
| ~~TASK-027~~ | ~~Rebuild Docker and verify bot starts with only admin_channels cog~~ | Docker, `gateway/adapters/discord/adapter.py` | ~~TASK-021 to 026~~ | ✅ | 2026-05-06 |

**Verification**: ✅ Gateway loads only `admin_channels` cog. No double responses. Bot responds correctly via handler.

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

- **ASSUMPTION-001**: ~~The `src/cogs/` directory contains only `__pycache__/`~~ ✅ Updated: `src/cogs/` now contains only `README.md` (migration note).
- ~~**ASSUMPTION-002**: All 5 cogs are currently loaded~~ **CHANGED**: Only `admin_channels` cog is loaded after cleanup (Phase 5).
- **ASSUMPTION-003**: The handler's `DiscordGatewayHandler._bot` class attribute is set by the adapter after cog loading (verified).
- **ASSUMPTION-004**: AppContainer is a singleton — calling `initialize()` multiple times is safe.
- **ASSUMPTION-005**: No external scripts or CI/CD pipelines depend on `python3 -m src`.

## Changelog

| Date | Version | Change | Author |
|------|---------|--------|--------|
| 2026-05-06 | 1.0 | Initial plan created | flowerf |
| 2026-05-06 | 1.1 | Phases 1-4 completed (deprecate standalone, docs, verify integrity, cleanup) | flowerf |
| 2026-05-06 | 1.2 | Phase 5 completed (fix double response, remove 4 unused cogs, Docker rebuild) | flowerf |

## Remaining Work

- [ ] User tests bot on Discord to verify single response
- [ ] Archive plan to `plan/archive/` when fully complete
