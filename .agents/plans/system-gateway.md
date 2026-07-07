---
status: in-progress
created: 2026-06-23
last_updated: 2026-06-25
---

# System Gateway

## Summary

Replace the demo-only `execute_host_bash` host bridge with a proper
cross-platform **System Gateway** subsystem.

The core design is:

```text
March7 / Evernight containers
  -> twin.shared.system_gateway.HostGatewayClient
  -> native system-gateway service on the real host OS
  -> OS adapter: Linux / macOS / Windows
```

Ownership:

- March7 uses the model-facing `host_system` tool for user-requested host
  interactions.
- Evernight owns owner approval, monitoring, install/update orchestration, and
  self-heal integration.
- `system-gateway` runs native on the host and enforces host-local policy,
  authentication, audit, timeouts, and OS-specific execution.

The current Docker `bash-executor` remains as a legacy compatibility path only
while the new client/tool contract lands. It must not be treated as a portable
or secure long-term host gateway.

Success criteria:

- The model-facing tool no longer exposes a Linux-only `execute_host_bash`
  abstraction as the primary host interaction contract.
- March7 and Evernight share one `twin.shared.system_gateway` client/protocol.
- The native gateway reports capabilities before execution, including platform,
  shell, and feature support.
- Linux/macOS/Windows compatibility is handled by host-side adapters, not by
  Docker `nsenter`.
- Owner-approved install/update flow is designed separately from normal tool
  execution.
- Dangerous operations have layered enforcement: owner approval, authenticated
  gateway requests, local policy, audit logs, timeouts, and output bounds.

## Directory Architecture

Shared agent-side protocol/client:

```text
twin/shared/system_gateway/
  __init__.py
  client.py
  types.py
  errors.py
  capabilities.py
  auth.py
  policy.py
  audit.py
```

Model-facing tool:

```text
twin/shared/tools/modules/system/
  __init__.py
  host_system_tool.py

twin/shared/tools/prompts/guides/host_system.md
```

Native host service:

```text
services/system_gateway/
  README.md
  pyproject.toml
  __init__.py
  __main__.py
  server.py
  config.py
  auth.py
  policy.py
  audit.py
  capabilities.py
  adapters/
    __init__.py
    base.py
    linux.py
    macos.py
    windows.py
  actions/
    __init__.py
    docker.py
    services.py
    logs.py
    shell.py
  cli/
    __init__.py
    main.py
  packaging/
    linux/
      system-gateway.service
    macos/
      com.twin.system-gateway.plist
    windows/
      README.md
```

> **Reality check (2026-06-25):** this native-service tree is now largely in place. `auth.py` / `policy.py` / `audit.py` live
> under `twin/shared/system_gateway/` (the agent-side package) and `services/system_gateway/server.py` imports them from
> there — they are **not** under `services/system_gateway/`. `services/system_gateway/` additionally has `state.py`
> (in-memory nonce/approval/audit store) and `cli/` (owner-facing CLI). `adapters/{base,linux,macos,windows}.py` and
> `capabilities.py` exist. `actions/` does not exist (actions are methods on adapters for now). `packaging/{linux,macos,windows}/`
> and `cli/` were added in Phase 4 (2026-06-25).

Evernight monitor/orchestrator:

```text
twin/evernight/system_gateway/
  __init__.py
  monitor.py
  installer.py
```

Legacy compatibility:

```text
scripts/bash_executor_standalone.py
scripts/bash_executor_starter.py
docker/shared/Dockerfile.bash-executor
docker/shared/docker-compose.bash-executor.yml
```

## Tasks

> **Status legend:**
> ✅ done · 🟡 partial / hollow · blank = not started · deferred = intentionally postponed (see the row's date).
> Dates are the verification date, not necessarily the authoring date.
>
> For the live per-area status and known gaps, see **Current State** below the goal tables. For the per-phase
> narrative and the original 2026-06-24 re-sync basis, see
> [`archive/system-gateway-history.md`](./archive/system-gateway-history.md). The two CRITICAL gaps called out in
> the archived re-sync (client signing + approval binding) are closed by **GOAL-009**.

### GOAL-001: Lock The Tool Boundary

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-001 | Add `twin/shared/system_gateway/` package with typed request/response/capability/error models only; no runtime execution yet. | ✅ | 2026-06-23 |
| TASK-002 | Add `HostGatewayClient` with `health()`, `capabilities()`, and placeholder `run_action()` / `run_shell()` methods using explicit HTTP timeouts and bounded response handling. | ✅ | 2026-06-23 |
| TASK-003 | Add model-facing `host_system` tool under `twin/shared/tools/modules/system/host_system_tool.py` that depends on `HostGatewayClient` and `ApprovalGate`. | ✅ | 2026-06-23 |
| TASK-004 | Add `host_system.md` guide that describes host interaction as capability-based, not Linux bash. It must tell the model to prefer structured actions and use raw shell only when explicitly requested. | ✅ | 2026-06-23 |
| TASK-005 | Register `host_system` in `SYSTEM_TOOL_SPECS` while keeping `execute_host_bash` temporarily available as legacy, hidden or deprioritized according to implementation constraints. | ✅ | 2026-06-23 |
| TASK-006 | Add tests proving `host_system` rejects missing gateway/capability states cleanly and does not execute anything without approval. | ✅ | 2026-06-23 |

### GOAL-002: Preserve Runtime While Deprecating Bash Executor

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-007 | Add a legacy adapter in `HostGatewayClient` or a narrow compatibility wrapper that can call existing `BASH_EXECUTOR_URL` for Linux demo commands during migration. | 🟡 | 2026-06-24 |
| TASK-008 | Mark `scripts/bash_executor_*` and Docker bash-executor docs as legacy Linux-only compatibility, not the System Gateway design. | ✅ | 2026-06-24 |
| TASK-009 | Update README/.agents docs to describe System Gateway as the future host boundary and call out that Docker `nsenter` is Linux-only. | ✅ | 2026-06-24 |
| TASK-010 | Ensure Docker compose can keep current `bash-executor` running until System Gateway native service is implemented; do not remove working demo infrastructure in this phase. | ✅ | 2026-06-24 |

### GOAL-003: Define Gateway Protocol And Policy

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-011 | Define `/health` response with service version, status, uptime, and platform. | ✅ | 2026-06-24 |
| TASK-012 | Define `/capabilities` response with `platform`, `shells`, `features`, `raw_shell`, `structured_actions`, and unsupported feature notes. | ✅ | 2026-06-24 |
| TASK-013 | Define structured action request/response schemas for initial safe actions: system status, disk usage, list Docker containers, container logs, service status. | ✅ | 2026-06-25 |
| TASK-014 | Define raw shell request/response schema separately from structured actions, including shell kind, cwd, timeout, max output, and approval id. | ✅ | 2026-06-24 |
| TASK-015 | Define local policy model: deny by default, allow structured read-only actions by capability, require explicit owner approval for mutating actions, and require separate raw-shell permission. | ✅ | 2026-06-24 |
| TASK-016 | Define audit event schema for approval requested/resolved, command/action started, completed, denied, timed out, and failed. | ✅ | 2026-06-25 |

### GOAL-004: Build Native `system-gateway` Skeleton

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-017 | Create native service package under `services/system_gateway/` with `pyproject.toml`, `__main__.py`, config loading, and aiohttp server skeleton. | ✅ | 2026-06-23 |
| TASK-018 | Implement platform detection and adapter selection for Linux, macOS, and Windows. Unsupported platforms must start in read-only/no-shell mode or fail clearly. | ✅ | 2026-06-23 |
| TASK-019 | Implement `BaseSystemAdapter` interface for capabilities and structured actions. | ✅ | 2026-06-23 |
| TASK-020 | Implement Linux adapter for initial read-only structured actions without `nsenter`; assume native service runs on Linux host. | ✅ | 2026-06-25 |
| TASK-021 | Add macOS and Windows adapters as capability stubs with honest unsupported responses before adding OS-specific actions. | ✅ | 2026-06-23 |
| TASK-022 | Add process timeout/output truncation utilities that can later handle process groups per OS. | ✅ | 2026-06-25 |

### GOAL-005: Add Authentication And Approval Binding

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-023 | Replace `Origin` trust with signed requests or bearer/HMAC authentication between container clients and `system-gateway`. | ✅ | 2026-06-25 |
| TASK-024 | Add request nonce/timestamp handling to reduce replay risk for mutating/raw-shell operations. | ✅ | 2026-06-25 |
| TASK-025 | Bind execution to an approval record/id issued by `ApprovalGate`/Evernight for mutating actions and raw shell. | ✅ | 2026-06-25 |
| TASK-026 | Restrict channel approval buttons to authorized users; owner DM approval remains preferred for host gateway administration. | deferred | 2026-06-25 |
| TASK-027 | Add tests for denied auth, stale signatures, missing approval id, unauthorized approver, timeout, and output truncation. | 🟡 | 2026-06-25 |

### GOAL-006: Wire Evernight Monitor And Install Orchestration

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-028 | Add `twin/evernight/system_gateway/monitor.py` to check gateway health/capabilities/version and report degraded/missing state. | ✅ | 2026-06-24 |
| TASK-029 | Add owner-only Evernight commands or internal handlers for gateway status/doctor/update approval. Keep chat-platform specifics in adapters. | ✅ | 2026-06-25 |
| TASK-030 | Define first-run bootstrap flow: if native gateway is absent, Evernight sends an OS-specific one-time installer command for the owner to run manually. | ✅ | 2026-06-24 |
| TASK-031 | Define post-bootstrap update flow: if gateway is present and owner approves, Evernight can ask gateway to update/restart itself through a restricted updater endpoint. | ✅ | 2026-06-25 |
| TASK-032 | Replace Evernight self-heal direct `/execute` restart path with a structured `restart_allowed_container` action or keep it disabled until policy support exists. | ✅ | 2026-06-25 |

### GOAL-007: Packaging And CLI

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-033 | Add CLI entrypoint `system-gateway` with `status`, `doctor`, `capabilities`, `logs`, `pair`, `install`, `update`, and `uninstall` command stubs. | ✅ | 2026-06-25 |
| TASK-034 | Add Linux systemd unit under `services/system_gateway/packaging/linux/system-gateway.service`. | ✅ | 2026-06-25 |
| TASK-035 | Add macOS launchd plist under `services/system_gateway/packaging/macos/`. | ✅ | 2026-06-25 |
| TASK-036 | Add Windows packaging notes/stub under `services/system_gateway/packaging/windows/` before implementing Windows service support. | ✅ | 2026-06-25 |
| TASK-037 | Add `pair` flow for generating/storing shared auth material without printing secrets into logs. | ✅ | 2026-06-25 |

### GOAL-008: Documentation And Migration

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-038 | Update root README host-tool section from `execute_host_bash` to System Gateway architecture. | ✅ | 2026-06-24 |
| TASK-039 | Update `.agents/PROJECT_CONTEXT.md` runtime services and tool boundary after implementation lands. | ✅ | 2026-06-25 |
| TASK-040 | Update `.agents/AGENT_RULES.md` with System Gateway safety invariants: no `Origin` auth, no host-shell execution without approval id, no direct Evernight Redis or host bypass. | ✅ | 2026-06-25 |
| TASK-041 | Add `services/system_gateway/README.md` with threat model, supported OS matrix, bootstrap flow, and admin runbook. | ✅ | 2026-06-25 |
| TASK-042 | Add deprecation note for `execute_host_bash` and a cleanup plan for removing `bash-executor` once System Gateway reaches feature parity. | ✅ | 2026-06-24 |

## GOAL-009: Interactive Install-On-Demand And First-Run Bootstrap

Target flow: a user asks for a host action → if the native gateway is missing, the agent proposes an OS-specific
install to the owner → once installed and approved, every host action is enforced by the layered gates.

**Hard ordering — non-negotiable:** finish the gate fixes (TASK-043/044/045) **before** wiring the interactive
proposal (TASK-047/048/049). Proposing an install while the gates are hollow would invite the owner to install
something that enforces nothing (client doesn't sign, approval isn't bound, nothing executes) — a false sense of
safety. TASK-046 (packaging/CLI) is the only item that can run in parallel with the gate fixes.

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-043 | Close the two CRITICAL gaps. (a) Client signs: `HostGatewayClient.__init__` takes `shared_secret`/`actor`; `_request_json` attaches `sign_request` + `headers_from_signed` for every call (`client.py:61-87`, reusing `auth.py:76,171`). (b) Real approval binding: tool passes the `approval_id` issued by `ApprovalGate` into `GatewayActionRequest` (`host_system_tool.py:155-161`), and the server validates it against an issued-approval registry instead of "non-empty & unconsumed" (`policy.py:84-101`, `state.py:42-43`), consuming atomically (compare-and-set). | ✅ | 2026-06-25 |
| TASK-044 | Implement `run_action` execution for read-only structured actions in `adapters/linux.py`: `system.status` (pure-Python), `system.disk_usage`, `docker.list_containers`, `docker.container_logs`, and `service.status`. All use safe arg-list subprocess (no `shell=True`, no string interpolation) with input validation, timeout, and output truncation. | ✅ | 2026-06-25 |
| TASK-045 | Emit the defined-but-unused audit events `EVENT_APPROVAL_REQUESTED/RESOLVED` and `EVENT_ACTION_COMPLETED/TIMED_OUT/FAILED` (`audit.py:22-28`); the server currently emits only DENIED + STARTED (`server.py:178-203`). | 🟡 | 2026-06-25 |
| TASK-046 | Create `services/system_gateway/{packaging/{linux,macos,windows},cli}/` so `build_bootstrap_hint` is followable: systemd unit, launchd plist, and a CLI that installs `/usr/local/bin/system-gateway` (referenced but absent, `installer.py:96-106`). Can run in parallel with TASK-043/044/045. | ✅ | 2026-06-25 |
| TASK-047 | Start `GatewayMonitor` from `twin/evernight/__main__.py` alongside `SelfHealMonitor`; wire `_maybe_notify_degraded` to DM the owner on MISSING/DEGRADED. | ✅ | 2026-06-25 |
| TASK-048 | Owner-only command via `gateway_admin` tool visible only to Evernight: `status`, `doctor`, `install_hint`, `update`. Verifies caller user_id matches configured owner before acting. | ✅ | 2026-06-25 |
| TASK-049 | `HostSystemTool` absent/unhealthy branch returns a structured `needs_install` payload (platform + bootstrap command from `build_bootstrap_hint`) instead of a static string. | ✅ | 2026-06-25 |

Dependencies: TASK-044 needs TASK-043; TASK-045 needs TASK-043/044; TASK-047 needs TASK-043/044/045 (gates must be
live); TASK-048 needs TASK-046/047; TASK-049 needs TASK-046 + TASK-043/044.

## Current State (2026-06-25)

Single source of truth for the gateway subsystem. Per-phase narrative moved to
[`archive/system-gateway-history.md`](./archive/system-gateway-history.md).

**Live and verified against the working tree:**

- **Tool boundary** — `host_system` tool + `host_system.md` guide registered; `execute_host_bash` hard-hidden (`visible_to`/`allowed_to` empty).
- **Protocol/policy** — `/health`, `/capabilities`, `/actions/run`, `/shell/run`, `/self/update` routed. Policy = default-deny; structured read-only allowed by capability; mutating actions require approval; raw shell requires separate permission.
- **Auth** — client signs every call with HMAC-SHA256 (`shared_secret`); server verifies signature + nonce/timestamp skew. Body serialized manually so the signed bytes match `request.read()`.
- **Approval binding** — server validates `approval_id` against an issued-approval registry (atomic compare-and-set), not "non-empty & unconsumed".
- **Execution** — Linux adapter runs read-only structured actions (`system.status`, `system.disk_usage`, `docker.list_containers`, `docker.container_logs`, `service.status`) via `asyncio.create_subprocess_exec` (no `shell=True`), with input validation, timeout, and output truncation.
- **Evernight** — `GatewayMonitor` started in lifecycle; `SelfHealMonitor` prefers `GatewayRecoveryExecutor` (mints a `container.restart` approval token) over legacy bash executors. `gateway_admin` tool (owner-gated) exposes `status`/`doctor`/`install_hint`/`update`.
- **Packaging/CLI** — systemd unit, launchd plist, Windows notes; `system-gateway` CLI (`status`/`doctor`/`capabilities`/`logs`/`pair`/`install`/`update`/`uninstall`/`run`). `/self/update` returns queued status and does not auto-download.
- **Docs** — root README, `PROJECT_CONTEXT.md`, `AGENT_RULES.md`, `services/system_gateway/README.md` all updated with threat model, OS matrix, bootstrap flow, and safety invariants.

**Partial / known gaps:**

- **TASK-027 (🟡)** — dedicated `tests/unit/system_gateway_adapter_test.py` not created; missing-executable / timeout / truncation / unauthorized-approver cases only partially covered by existing server tests.
- **TASK-045 (🟡)** — `EVENT_APPROVAL_RESOLVED` / `EVENT_ACTION_COMPLETED` / `TIMED_OUT` / `FAILED` emitted; `EVENT_APPROVAL_REQUESTED` defined but **not emitted anywhere**.
- **TASK-007 (🟡)** — `LegacyBashExecutorBridge` exists but is not wired into tool bootstrap.
- **TASK-026 (deferred)** — channel-button approver restriction not implemented; owner-DM approval is the path.

**Repo hygiene risks (block "really done"):**

- The entire subsystem is **uncommitted** since `ab5865f` — status above reflects the working tree, not `main`. Commit by phase before continuing.
- Stray `services/system_gateway2/` (duplicate tree) and a file named `!` at repo root are **not** part of this plan — remove before commit.

## Test Plan

Focused unit tests:

```bash
conda run -n discord_bot python -m pytest tests/unit/tool_bootstrap_test.py tests/unit/tool_prompt_catalog_test.py -q
conda run -n discord_bot python -m pytest tests/unit/approval_gate_test.py -q
```

Agent-side / integration tests (present in the working tree; full sweep as of 2026-06-25: 152 system-gateway tests passing, 420 repo-wide / 6 skipped):

```text
tests/unit/system_gateway_client_test.py
tests/unit/system_gateway_auth_test.py
tests/unit/system_gateway_policy_test.py
tests/unit/system_gateway_audit_test.py
tests/unit/system_gateway_server_test.py
tests/unit/system_gateway_legacy_test.py
tests/unit/evernight_system_gateway_monitor_test.py
tests/services/tools/host_system_tool_test.py
```

Native gateway tests (present):

```text
services/system_gateway/tests/test_capabilities.py
services/system_gateway/tests/test_server.py
services/system_gateway/tests/test_config.py
```

Still to add (TASK-027, 🟡): a dedicated `tests/unit/system_gateway_adapter_test.py` for missing-executable handling
(`docker_not_available`, `systemctl_not_available`), timeout behavior, output truncation at the adapter level, and
unauthorized-approver edge cases. Structured-action server tests already live in
`tests/unit/system_gateway_server_test.py`.

Docker/runtime smoke after compatibility phase:

```bash
docker compose -f docker/docker-compose.yml ps
curl -sf http://localhost:8380/health   # System Gateway (native host service; 8374 is the legacy bash-executor)
```

Manual acceptance when native gateway exists:

- `system-gateway status` reports running service and platform.
- `system-gateway capabilities` reports accurate OS features.
- March7 `host_system` read-only action succeeds after owner approval rules pass.
- Raw shell is denied by default.
- Mutating action without approval id is denied.
- Evernight monitor reports missing/outdated gateway without attempting unsafe
  automatic install.

## Assumptions

- The subsystem name is **System Gateway**.
- The native service command is `system-gateway`.
- The model-facing tool name is `host_system`.
- March7 uses host capabilities; Evernight monitors/administers them.
- First install cannot be fully automatic from Docker on every OS. A one-time
  owner-run bootstrap command is required unless a pre-existing trusted
  bootstrap agent or OS management credential is available.
- macOS/Windows support means native host service adapters, not Docker `nsenter`
  compatibility.
- The current `bash-executor` is legacy Linux-only infrastructure. As of the
  2026-06-24 re-sync, `execute_host_bash` is already hard-hidden (`visible_to`
  and `allowed_to` both empty) — it is no longer a "temporary continuity" path.
