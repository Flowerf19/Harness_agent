---
archived: 2026-06-25
parent: ../system-gateway.md
---

# System Gateway — History

Verbatim record of the per-phase completion notes and the 2026-06-24 status
re-sync. Moved out of the live plan so the plan's task tables + "Current State"
section are the single source of truth. Kept intact for traceability; some of
this text describes gaps that were **closed later** by GOAL-009 / phases 2-6
and is therefore superseded — read with that in mind.

## Status Re-sync Notes (2026-06-24)

Corrected from a code review of the (mostly uncommitted) working tree. Basis is `file:line`.

- **Done but were left unchecked** → now ✅: TASK-008/009/010 (legacy banners, README, compose still runs);
  TASK-011/012/014/015 (`twin/shared/system_gateway/types.py`, `policy.py`); TASK-028/030
  (`twin/evernight/system_gateway/monitor.py`, `installer.py`); TASK-038/042 (README + deprecation note).
- **Overclaimed** → downgraded to 🟡: TASK-020 was ✅ but `run_action` returns HTTP 501
  `action_execution_not_implemented` (`services/system_gateway/server.py:205-215`); the Linux adapter only reports
  capability metadata (`adapters/linux.py:14-48`). No structured action executes yet.
- **Partial (🟡):** TASK-007 `LegacyBashExecutorBridge` exists (`twin/shared/system_gateway/legacy.py`) but is not
  wired into tool bootstrap; TASK-013 only a generic action envelope + `system.status` metadata, no per-action
  schema; TASK-016 audit schema defined but `EVENT_APPROVAL_*` / `EVENT_ACTION_COMPLETED/...` are never emitted;
  TASK-023/024 server-side HMAC + nonce/skew land, but the **client never signs** (`client.py:53-87`) so real calls
  401; TASK-027 missing unauthorized-approver / timeout / truncation tests; TASK-029 handlers exist without an owner
  gate; TASK-031 client posts to `/self/update` which the server does not route (`server.py:325-328`); TASK-041
  services README is still a "read-only metadata only" skeleton that contradicts shipped code.
- **Looks implemented but is hollow / unsafe** → kept blank deliberately: TASK-025 (an `approval_id` is accepted as
  any non-empty, non-replayed string — not bound to an issued approval record; `policy.py:84-101`,
  `state.py:42-43`) and TASK-032 (legacy `/execute` Origin path is still the only active self-heal route;
  `twin/evernight/__main__.py:54-66`). These are the two CRITICAL gaps closed by GOAL-009.

## Phase 2 Completion Notes (2026-06-25)

- Implemented structured action execution in `services/system_gateway/adapters/linux.py`:
  - `system.status` (pure-Python, no shell)
  - `system.disk_usage` (`df` with path validation)
  - `docker.list_containers` (`docker ps --format=json`)
  - `docker.container_logs` (`docker logs --tail N` with name validation)
  - `service.status` (`systemctl status` with service-name validation)
- Security: all subprocess calls use `asyncio.create_subprocess_exec` with explicit arg-lists, no `shell=True`, and
  user inputs are validated before reaching subprocess. Missing executables are surfaced as returncode 127 and mapped
  to `docker_not_available` / `systemctl_not_available` instead of raising through the request handler.
- Added 6 focused tests in `tests/unit/system_gateway_server_test.py` covering success paths, input validation
  rejection, and approval-token replay for the new actions.
- Marked TASK-013/020/022/044 complete. TASK-027 now partially covered by the new adapter tests; the remaining
  unauthorized-approver / timeout cases are still pending a dedicated adapter test file.

## Phase 3 Completion Notes (2026-06-25)

- Wired `GatewayMonitor` into Evernight lifecycle:
  - `twin/evernight/container.py` creates/starts the monitor during initialization and stops it on shutdown.
  - `twin/evernight/__main__.py` passes the monitor to `SelfHealMonitor` so recovery can use the gateway path.
- Added `gateway_admin` tool (`twin/shared/tools/modules/system/gateway_admin_tool.py`) visible/allowed only to Evernight.
  Commands: `status`, `doctor`, `install_hint`, `update`. Owner gate enforced via `get_current_approval_context().user_id`.
- `HostSystemTool` now returns a structured JSON `needs_install` payload when the gateway client is missing or
  unavailable, using `build_bootstrap_hint()` for the platform-specific bootstrap command.
- Replaced the legacy self-heal `/execute` Origin path with `GatewayRecoveryExecutor` in
  `twin/evernight/self_heal/monitor.py`. It mints an action-bound approval token for `container.restart` and routes
  through `GatewayMonitor.request_container_restart`. `SelfHealMonitor` prefers it when `SYSTEM_GATEWAY_URL` is set
  or a `gateway_monitor` is injected, falling back to `BashExecutorRecoveryExecutor` / `DockerCommandRecoveryExecutor`
  otherwise.
- Added focused tests:
  - `tests/unit/gateway_admin_tool_test.py` (owner gate + command routing)
  - `tests/unit/self_heal_monitor_test.py` (recovery executor preference + token minting)
  - Updated `tests/services/tools/host_system_tool_test.py` for `needs_install` JSON.
- Marked TASK-029/031/032/047/048/049 complete.

## Phase 4 Completion Notes (2026-06-25)

- Added CLI package `services/system_gateway/cli/`:
  - `system-gateway status/doctor/capabilities/logs` query the running service.
  - `system-gateway pair` generates a 256-bit urlsafe-base64 secret, writes it to a platform config dir with owner-only
    permissions, and prints env-var/file setup instructions (never logs the secret).
  - `system-gateway install/uninstall` deploy the systemd/launchd unit on Linux/macOS and generate a secret first if
    missing.
  - `system-gateway update` mints an owner-approval token for `self.update` and calls `POST /self/update`.
  - `system-gateway run` (default) starts the aiohttp foreground service.
- Added packaging artifacts:
  - `services/system_gateway/packaging/linux/system-gateway.service` with hardening (NoNewPrivileges, ProtectSystem,
    ProtectHome, restricted syscall filter) and `SYSTEM_GATEWAY_SHARED_SECRET_FILE=/etc/system-gateway/secret`.
  - `services/system_gateway/packaging/macos/com.twin.system-gateway.plist` for user launchd.
  - `services/system_gateway/packaging/windows/README.md` with manual setup and service-wrapper guidance.
- Added server-side `POST /self/update` endpoint that validates the owner approval token, records audit events, checks
  version match, and returns a queued status (the service does not auto-download or restart itself).
- `GatewayConfig.from_env()` now supports `SYSTEM_GATEWAY_SHARED_SECRET_FILE` in addition to the env var.
- `pyproject.toml` now packages `system_gateway.cli` and includes `packaging/**/*` as package data.
- Added tests:
  - `tests/unit/system_gateway_cli_test.py` (parser, pair, status, doctor, update, run dispatch)
  - `services/system_gateway/tests/test_config.py` (secret file loading, env overrides, port validation)
  - Updated `services/system_gateway/tests/test_server.py` for the new `/self/update` route.
- Marked TASK-033/034/035/036/037 complete.

## Phase 5 Completion Notes (2026-06-25)

- Updated `.agents/PROJECT_CONTEXT.md`:
  - Listed `system-gateway` as a primary service and `bash-executor` as legacy.
  - Added port `8380` to expected local endpoints.
  - Documented the System Gateway tool/runtime boundary, HMAC signing,
    approval-token binding, structured actions, raw-shell policy, Evernight
    monitor/self-heal integration, and first-install bootstrap flow.
  - Added `SYSTEM_GATEWAY_URL` and `SYSTEM_GATEWAY_SHARED_SECRET` to key env vars.
- Updated `.agents/AGENT_RULES.md`:
  - Added System Gateway safety invariants (HMAC signatures, action-bound
    approval tokens, no container-side host shell, no side-channel bypass,
    default-deny raw shell, no secret logging).
  - Added gotcha: `execute_host_bash` is legacy/hidden; gateway runs on the
    host and is reached via `SYSTEM_GATEWAY_URL`.
- Rewrote `services/system_gateway/README.md` with threat model, supported OS
  matrix, quick-start (`pair` + `install`), admin runbook (status, logs,
  update, secret rotation, uninstall), env var table, API endpoint table, and
  migration note from `execute_host_bash`.
- Marked TASK-039/040/041 complete.

## Phase 6 Completion Notes (2026-06-25)

- Full test sweep:
  - `services/system_gateway/tests/`: 15 passed
  - All system-gateway unit/integration tests: 152 passed
  - Full repo unit tests (excluding Discord-dependent files): **420 passed, 6 skipped**
- Security review and hardening fixes:
  - CLI `update` now signs `POST /self/update` with HMAC-SHA256 and an
    action-bound approval token (was sending an unsigned request).
  - macOS `install` customizes the launchd plist so `/Users/me` is replaced with
    the actual home directory before loading.
  - Added server-side tests for `/self/update`: valid owner request, unsigned
    rejection, version mismatch, and replayed approval token.
  - Verified no shared secret or approval tokens are logged by the service or
    CLI (except `pair` intentionally prints the secret once to the terminal for
    owner setup, with a "do not commit" warning).
  - Verified all subprocess calls in adapters use `asyncio.create_subprocess_exec`
    with explicit arg-lists and no `shell=True`.
  - Verified input validation rejects shell metacharacters in paths, container
    names, and service names before reaching the OS.
- Marked TASK-043/045 complete (client signing + approval-token binding + audit
  event emission).