---
goal: Refactor Discord cog loading so all cogs load exclusively via gateway adapter; CoreBot becomes thin (AppContainer init + NightlyTrigger only); standalone mode deprecated
version: "1.0"
date_created: 2026-05-06
last_updated: 2026-05-06
owner: flowerf
status: 'Planned'
tags:
  - refactor
  - discord
  - gateway
  - cogs
  - architecture
---

# Refactor Discord Cog Loading — Gateway-Only Mode

![Status: Planned](https://img.shields.io/badge/status-Planned-blue)

## Overview

Consolidate all Discord cog loading into the gateway adapter (`python3 -m gateway`) exclusively. The `CoreBot` class in `src/bot.py` becomes a thin shell that only initializes `AppContainer` and starts `NightlyTrigger`. Standalone mode (`python3 -m src`) is deprecated in favor of gateway mode. The handler (`handler.py`) depends on the `AdminChannels` cog being loaded, which the gateway adapter already handles correctly.

## Requirements

- **REQ-001**: All 5 cogs (`admin_channels`, `base_cog`, `chat_gateway`, `user_commands`, `server_relationships`) must load ONLY via `gateway/adapters/discord/adapter.py` — nowhere else
- **REQ-002**: `src/bot.py` `CoreBot.setup_hook()` must NOT load any cogs — it only initializes `AppContainer` and starts `NightlyTrigger`
- **REQ-003**: `src/bot.py` must emit a deprecation warning when run in standalone mode (`python3 -m src`)
- **REQ-004**: Gateway mode must load ALL 5 cogs before any message handling begins (already implemented — verify)
- **REQ-005**: `handler.py` must be able to access `AdminChannels` cog via `self._get_bot().get_cog("AdminChannels")` after gateway setup
- **REQ-006**: `NightlyTrigger` must start in both gateway mode and standalone mode (where applicable)
- **REQ-007**: The `_setup_done` flag in adapter must prevent double-initialization across reconnects

## Constraints & Guidelines

- **CON-001**: Do NOT change the cog loading order in `adapter.py` — it already works correctly
- **CON-002**: Do NOT remove `src/bot.py` entirely — it may still be used by existing Docker/dev setups during transition
- **CON-003**: The `setup_hook` override in `adapter.py` (`self._bot.setup_hook = self._gateway_setup_hook`) prevents `CoreBot.setup_hook` from running in gateway mode — this is intentional and must remain
- **GUD-001**: Use `logging.warning()` for deprecation notices, not `print()`
- **GUD-002**: Keep Vietnamese logging messages in `src/bot.py` for consistency with existing code style
- **GUD-003**: Use present tense, imperative mood in all task descriptions

## Implementation Phases

### Phase 1: Verify Gateway Adapter Cog Loading
**Goal**: GOAL-001 Confirm adapter.py loads all 5 cogs in correct order with proper error handling

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| TASK-001 | Verify all 5 cog paths are present in `_gateway_setup_hook()` loop | `gateway/adapters/discord/adapter.py` | None | ☐ | |
| TASK-002 | Verify `_setup_done` guard prevents double-loading on reconnect | `gateway/adapters/discord/adapter.py` | None | ☐ | |
| TASK-003 | Verify `DiscordGatewayHandler._bot` is assigned after cog loading (line: `DiscordGatewayHandler._bot = self._bot`) | `gateway/adapters/discord/adapter.py` | None | ☐ | |
| TASK-004 | Verify `NightlyTrigger` is started via `asyncio.create_task()` in `_gateway_setup_hook()` | `gateway/adapters/discord/adapter.py` | None | ☐ | |
| TASK-005 | Verify `AppContainer.get_instance().initialize()` is called before cog loading | `gateway/adapters/discord/adapter.py` | None | ☐ | |

### Phase 2: Strip Cog Loading from CoreBot
**Goal**: GOAL-002 Remove cog loading from `src/bot.py` `setup_hook()` — keep only AppContainer init + NightlyTrigger

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| TASK-006 | Remove any cog-loading code from `CoreBot.setup_hook()` (currently there is none — verify comment is accurate and remove stale comments about gateway loading) | `src/bot.py` | None | ☐ | |
| TASK-007 | Update `CoreBot.setup_hook()` docstring to reflect it no longer loads cogs — clarify it is for standalone mode only | `src/bot.py` | None | ☐ | |
| TASK-008 | Add deprecation warning at top of `main()` function: `logger.warning("⚠️ Standalone mode (python3 -m src) is deprecated. Use 'python3 -m gateway' instead.")` | `src/bot.py` | TASK-006 | ☐ | |
| TASK-009 | Update `CoreBot.close()` to keep existing cleanup (AppContainer shutdown) — verify no cog-related cleanup exists | `src/bot.py` | None | ☐ | |

### Phase 3: Update Entry Points and Documentation
**Goal**: GOAL-003 Deprecate standalone entry point; update README to reflect gateway-only operation

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| TASK-010 | Update `src/__main__.py` — add deprecation warning comment above the `main()` import | `src/__main__.py` | TASK-008 | ☐ | |
| TASK-011 | Update `README.MD` "Local Development" section — replace `python -m src.bot` with `python3 -m gateway` as primary command | `README.MD` | None | ☐ | |
| TASK-012 | Update `README.MD` — add "Deprecated: Standalone Mode" callout explaining `python3 -m src` is no longer supported and why | `README.MD` | TASK-011 | ☐ | |
| TASK-013 | Update `README.MD` project structure — mark `src/cogs/` as legacy/removed if applicable, confirm cogs live at `gateway/adapters/discord/cogs/` | `README.MD` | None | ☐ | |
| TASK-014 | Update `README.MD` Quick Start Docker section if it references standalone mode | `README.MD` | TASK-011 | ☐ | |

### Phase 4: Validate Handler Dependency on AdminChannels Cog
**Goal**: GOAL-004 Ensure handler.py can reliably access AdminChannels cog after gateway setup

| ID | Task | File(s) | Dependencies | Status | Completed |
|----|------|---------|--------------|--------|-----------|
| TASK-015 | Verify `handler.py` `_get_bot()` returns non-None after adapter sets `DiscordGatewayHandler._bot` | `gateway/adapters/discord/handler.py` | TASK-003 | ☐ | |
| TASK-016 | Verify `admin_cog = self._get_bot().get_cog("AdminChannels")` returns the loaded cog instance (cog class name must match `"AdminChannels"` exactly) | `gateway/adapters/discord/handler.py` | TASK-015 | ☐ | |
| TASK-017 | Confirm `gateway/adapters/discord/cogs/admin_channels.py` defines a class named `AdminChannels` (matching the string used in `get_cog()`) | `gateway/adapters/discord/cogs/admin_channels.py` | None | ☐ | |
| TASK-018 | Verify fallback behavior in handler.py when cog is None (`is_allowed_channel = True`) — this is safe as a fallback but should never trigger in gateway mode | `gateway/adapters/discord/handler.py` | TASK-016 | ☐ | |

## Alternatives Considered

- **ALT-001**: Remove `src/bot.py` entirely and force gateway-only — rejected because existing Docker/dev setups may still reference `python -m src.bot` during transition period. Keep as thin shell with deprecation warning instead.
- **ALT-002**: Keep cog loading in both CoreBot and adapter with a flag to toggle — rejected because dual loading creates ambiguity, risk of double-initialization, and maintenance burden. Single source of truth (adapter) is cleaner.
- **ALT-003**: Move cogs to `src/cogs/` and have both gateway and standalone load from there — rejected because cogs are gateway-specific adapters; keeping them under `gateway/` reflects their architectural role correctly.

## Dependencies

- **DEP-001**: `discord.py` (via `discord.ext.commands`) — cog loading uses `bot.load_extension()`, `ExtensionAlreadyLoaded` exception
- **DEP-002**: `src.services.dependencies.AppContainer` — shared DI container, must be initialized before cog loading
- **DEP-003**: `src.tasks.nightly_trigger.NightlyTrigger` — background task, started via `asyncio.create_task()`
- **DEP-004**: `gateway.adapters.discord.handler.DiscordGatewayHandler` — class-level `_bot` attribute set by adapter after cog loading

## Affected Files

- **FILE-001**: `src/bot.py` — modify — Remove stale cog-loading comments, add deprecation warning in `main()`, clarify `setup_hook()` docstring
- **FILE-002**: `src/__main__.py` — modify — Add deprecation comment
- **FILE-003**: `gateway/adapters/discord/adapter.py` — verify only — Confirm all 5 cogs load, `_setup_done` guard, `_bot` assignment, NightlyTrigger start
- **FILE-004**: `gateway/adapters/discord/handler.py` — verify only — Confirm `AdminChannels` cog access works after gateway setup
- **FILE-005**: `gateway/adapters/discord/cogs/admin_channels.py` — verify only — Confirm class name is `AdminChannels`
- **FILE-006**: `README.MD` — modify — Update Quick Start, deprecate standalone mode, update project structure

## Testing Strategy

- **TEST-001**: Manual test — Run `python3 -m gateway` and verify all 5 cogs load (check log output for "Loaded cog:" messages)
- **TEST-002**: Manual test — Run `python3 -m src` and verify deprecation warning appears in logs
- **TEST-003**: Manual test — Send a message in a non-allowed channel (not DM, not mentioned) and verify handler correctly filters it via `AdminChannels.is_bot_channel()`
- **TEST-004**: Manual test — Trigger a Discord reconnect (simulated) and verify `_setup_done` prevents double-loading (check for "Gateway setup already done" debug log)
- **TEST-005**: Manual test — Verify `NightlyTrigger` starts in gateway mode (check for "NightlyTrigger: started scheduled task" log)
- **TEST-006**: Manual test — Verify handler's `_get_bot()` returns non-None after gateway setup (can add temporary debug log if needed)

## Risks

- **RISK-001**: Existing users/devs still run `python3 -m src` and encounter unexpected behavior — Impact: Medium, Likelihood: Medium, Mitigation: Clear deprecation warning in logs; update README prominently
- **RISK-002**: `AdminChannels` cog fails to load silently, causing handler fallback to `is_allowed_channel = True` (allowing all channels) — Impact: High, Likelihood: Low, Mitigation: Adapter already logs exceptions on cog load failure; handler has explicit fallback; TEST-003 validates
- **RISK-003**: `_setup_done` flag not reset properly across reconnects, causing cogs to not reload — Impact: High, Likelihood: Low, Mitigation: Flag is set to `True` after first successful setup; `ExtensionAlreadyLoaded` exception handles reconnection; TASK-002 verifies
- **RISK-004**: Docker deployment still references standalone mode in compose files — Impact: Medium, Likelihood: Low, Mitigation: Check `docker/docker-compose.bot.yml` for entry point references (separate verification, not in scope of this plan)

## Assumptions

- **ASSUMPTION-001**: The 5 cogs in `gateway/adapters/discord/cogs/` are the only cogs that need loading — no other cogs exist elsewhere
- **ASSUMPTION-002**: `AdminChannels` cog class name is exactly `"AdminChannels"` (matching `get_cog("AdminChannels")` in handler.py)
- **ASSUMPTION-003**: Docker deployment already uses gateway entry point (`python3 -m gateway`) — not standalone mode
- **ASSUMPTION-004**: No external services or tests depend on `python3 -m src` as an entry point
- **ASSUMPTION-005**: `_gateway_setup_hook` override pattern (`self._bot.setup_hook = self._gateway_setup_hook`) correctly prevents `CoreBot.setup_hook` from running in gateway mode

## Related Resources

- Discord.py cog loading docs: https://discordpy.readthedocs.io/en/stable/ext/commands/api.html#discord.ext.commands.Bot.load_extension
- Gateway architecture overview: `README.MD` (architecture diagrams section)
- Existing plan directory: `/home/flowerf/Projects/march7/plan/`
