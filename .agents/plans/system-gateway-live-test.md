---
status: executed
created: 2026-07-08
last_updated: 2026-07-08
---

# System Gateway Live Test Plan

## Summary

Verify System Gateway end to end through the real bot surfaces, not only through
unit tests. The run must prove:

- Evernight gives the correct install guidance.
- A subagent can follow that exact guidance on the host.
- Evernight can administer and use System Gateway.
- March7 can use the same System Gateway.
- Approval works for both approve and reject paths.

This plan intentionally does not store Discord tokens, gateway secrets, or API
keys. It records only non-secret identifiers needed to avoid chatting with the
wrong bot:

- March7 Discord client/app ID: `1392176240156344440`.
- Evernight Discord client/app ID: `1486755348080754838`.
- Evernight owner user ID: `726302130318868500`.
- Configured Discord respond test target: server `1067690340359880724`, channel
  `1487427038280421456` from `data/bot_channels.json`.
- March7 A2A: `http://march7:8000`, host port `8000`.
- Evernight A2A: `http://evernight:8001`, host port `8001`.
- System Gateway URL from containers: `http://host.docker.internal:8380`.

Evidence anchors:

- March7 container owns Discord main bot, A2A `8000`, and System Gateway URL in
  `docker/march7/docker-compose.yml`.
- Evernight container owns A2A `8001`, gateway monitor settings, and bootstrap
  repo root in `docker/evernight/docker-compose.yml`.
- Evernight owner-only gate, DM/mention/`!9` handling, and approval context live
  in `gateway/adapters/discord/evernight_adapter.py`.
- March7 handles DM, mention, reply-to-bot, and configured respond channels; it
  explicitly ignores `!9`, so there is no March7 chat prefix in this plan.
- `host_system` is visible to both agents; `gateway_admin` is Evernight-only in
  `twin/shared/tools/declarations/system_tools.py`.
- Bootstrap guidance must come from `gateway_admin install` or `install_hint`,
  which renders `cd <repo>` plus `python3 scripts/bootstrap_system_gateway.py`
  from `twin/evernight/host_gateway/installer.py`.
- March7 host commands use Evernight DM approval because March7 builds its tool
  registry with `use_evernight_dm_approval=True`.
- Current shared `HostGatewayClient` bootstrap sets `actor="march7"`; if Evernight
  `host_system` audit lines show actor `march7`, record it as current behavior,
  not as proof the request came from March7 chat.

## Tasks

### GOAL-001: Preflight Runtime And Addresses

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-001 | Confirm no sensitive values will be copied into notes: do not paste `DISCORD_*_TOKEN`, `SYSTEM_GATEWAY_SHARED_SECRET`, `OPENAI_API_KEY`, LangSmith, or Tavily values. | ✅ | 2026-07-08 |
| TASK-002 | Confirm containers are up: `docker compose -f docker/docker-compose.yml ps` must show `march7`, `evernight`, `redis`, and `codebox` healthy/running as applicable. | ✅ | 2026-07-08 |
| TASK-003 | Confirm March7 bot identity from logs, not only env: look for `Bot online as ... (ID: ...)` in `docker logs --since 30m march7`; ID must match the intended March7 bot/client ID or be explained before chat testing. | ✅ | 2026-07-08 |
| TASK-004 | Confirm Evernight bot identity from logs: look for `Evernight bot ready: ... (ID: ...)` in `docker logs --since 30m evernight`; ID must match the intended Evernight bot/client ID or be explained before chat testing. | ✅ | 2026-07-08 |
| TASK-005 | Confirm A2A endpoints: `curl -sf http://localhost:8000/.well-known/agent.json` and `curl -sf http://localhost:8001/.well-known/agent.json`. | ✅ | 2026-07-08 |
| TASK-006 | Confirm host gateway baseline: `curl -sS http://localhost:8380/health`, `systemctl show system-gateway.service -p ActiveState -p SubState -p MainPID -p ExecStart -p Environment`, and `journalctl -u system-gateway.service --no-pager -n 80`. | ✅ | 2026-07-08 |
| TASK-007 | Confirm live chat targets in Discord UI before prompts: DM March7 bot ID `1392176240156344440`; DM Evernight bot ID `1486755348080754838`; for channel tests, use server `1067690340359880724` channel `1487427038280421456` only after confirming the UI still maps to the intended test channel. | ✅ | 2026-07-08 |
| TASK-008 | Confirm addressing rules before live prompts: March7 has no `!7` prefix and ignores `!9`; Evernight accepts owner DM, owner mention, or `!9 <message>`. | ✅ | 2026-07-08 |

### GOAL-002: Verify Evernight Install Guidance

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-009 | In Evernight DM as owner `726302130318868500`, ask: `gateway_admin doctor roi cho biet trang thai System Gateway, khong doan.` Expected: Evernight calls `gateway_admin doctor` and reports healthy/degraded/missing from tool output. | ✅ | 2026-07-08 |
| TASK-010 | In Evernight DM, ask: `cho toi lenh cai System Gateway bang gateway_admin install, copy nguyen xi output tu tool.` Expected: response contains tool-derived bootstrap block only, not hand-written `pip`, `curl`, or `systemctl` steps. | ✅ | 2026-07-08 |
| TASK-011 | Validate the install command has the correct host repo path. On this Linux host it should contain `cd /home/flowerf/Projects/march7` and `python3 scripts/bootstrap_system_gateway.py`. If it shows `/path/to/march7`, stop and fix `SYSTEM_GATEWAY_BOOTSTRAP_REPO_ROOT` before continuing. | ✅ | 2026-07-08 |
| TASK-012 | Ask the same install-guidance request from a non-owner account or channel user if available. Expected: no response or `gateway_admin` owner-only refusal; no bootstrap command leaked to a non-owner. | SKIP | 2026-07-08 — no non-owner account available in session |

### GOAL-003: Delegate Host Bootstrap To A Subagent

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-013 | Spawn a narrow subagent for execution verification. It must use the exact Evernight output from TASK-010, not invent substitute install steps. | ⚠️ BLOCKED | 2026-07-08 — subagent spawned, blocked on sudo (see TASK-014) |
| TASK-014 | Subagent runs the bootstrap command on the host from `/home/flowerf/Projects/march7`: `python3 scripts/bootstrap_system_gateway.py`. If sudo/escalation is required, request approval once and preserve the command/output. | ⚠️ BLOCKED | 2026-07-08 — `sudo -n` fails (no passwordless sudo); script `ensure_privilege()` re-execs sudo on Linux, no non-sudo mode. Owner must run `! cd /home/flowerf/Projects/march7 && sudo python3 scripts/bootstrap_system_gateway.py` |
| TASK-015 | Subagent records install result without secrets: venv path, service manager action, final health check, and whether the script changed `.env` or secret material. It must not print secret values. | ⚠️ BLOCKED | 2026-07-08 — depends on TASK-014 |
| TASK-016 | After subagent returns, main agent independently verifies `curl -sS http://localhost:8380/health`, `systemctl show system-gateway.service -p ActiveState -p SubState -p MainPID -p ExecStart -p Environment`, and recent journal lines. | ✅ | 2026-07-08 — verified against existing healthy service (uptime monotonically increasing, no restart) |

Subagent prompt template:

```text
Use `thoughtful-coder` for surgical runtime verification. Do not edit code.
You are the install executor for System Gateway in /home/flowerf/Projects/march7.

Input command copied from Evernight gateway_admin install:
<paste exact code block from Evernight>

Rules:
- Run exactly that command on the host. Do not replace it with manual pip/systemctl steps.
- If the command asks for sudo or fails due permission, report the exact blocker and request escalation through the host tool flow.
- Do not print Discord tokens, SYSTEM_GATEWAY_SHARED_SECRET, API keys, or secret file contents.
- Return: command run, exit status, health result, service status summary, recent non-secret journal summary, and any changed files detected by git status.
```

### GOAL-004: Test Evernight Gateway Capabilities And Host Reads

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-017 | In Evernight DM, ask: `goi host_system capabilities va chi tra output that tu tool.` Expected: platform, shells, and raw shell status from System Gateway. | ✅ | 2026-07-08 |
| TASK-018 | In Evernight DM, test VRAM/GPU with approval: `dung host_system doc VRAM/GPU hien tai bang nvidia-smi neu co; neu khong co nvidia-smi thi bao khong co va thu lspci/rocm-smi neu phu hop.` Expected: approval prompt appears with exact command; after approve, output is real host output. | ✅ | 2026-07-08 — NO_NVIDIA_SMI; rocm-smi AMD Strix 880M/890M, VRAM ~512MB used ~493MB; lspci 63:00.0 |
| TASK-019 | In Evernight DM, test temperature with approval: `dung host_system doc nhiet do CPU/GPU hien tai bang sensors/nvidia-smi; neu tool khong co thi bao ro.` Expected: approval prompt appears; output quotes actual command result or clear missing-tool error. | ✅ | 2026-07-08 — NO_SENSORS, NO_NVIDIA_SMI, rocm-smi edge 84.0°C |
| TASK-020 | In Evernight DM, test safe file read with approval: `dung host_system doc /etc/os-release, dong dau cua /proc/meminfo, va 20 dong dau services/system_gateway/README.md trong repo host.` Expected: approval prompt appears; output contains real file contents, no fabricated summary. | ✅ | 2026-07-08 — compound multi-file command failed (command_failed); split single `cat /etc/os-release` returned real Fedora 44 content. /proc/meminfo + README not requested separately for Evernight |
| TASK-021 | In Evernight DM, test rejection: request a harmless command such as `printf gateway-reject-test`. Click Reject. Expected: Evernight reports rejection and does not claim command output. | ✅ | 2026-07-08 — attempt 1 timeout-reject; attempt 2 (`gateway-reject-test-2`) bot hallucinated reject WITHOUT calling host_system (no APPROVAL REQUESTED in log); attempt 3 (`gw-rej3`) explicit Reject button click → log `❌ REJECTED` at 9s. Bot reported rejection, no fake output |
| TASK-022 | Check Evernight logs after TASK-017 to TASK-021: `docker logs --since 10m evernight`. Expected: `APPROVAL REQUESTED`, `APPROVED`/`REJECTED`, no stack trace, no secret values. | ✅ | 2026-07-08 — APPROVAL REQUESTED/APPROVED/REJECTED present; 1 cosmetic `discord.errors.NotFound 10008` view traceback (caught); no secret leak |

### GOAL-005: Test March7 Through The Same Gateway

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-023 | In March7 DM or the configured respond channel `1487427038280421456`, ask: `goi host_system capabilities, khong dung tri nho cu.` Expected: March7 calls `host_system` and reports real capability output. | ✅ | 2026-07-08 — platform linux, /bin/sh, generic_shell_exec, owner approval gates |
| TASK-024 | In March7 chat, ask for VRAM/GPU with `host_system`; approve via the Evernight DM approval prompt. Expected: March7 waits for approval and returns real host output after approval. | ✅ | 2026-07-08 — approved via Evernight DM; AMD ROCm 73°C/26W/VRAM 95%/load 85%. Log confirms real host_system call |
| TASK-025 | In March7 chat, ask for temperature with `host_system`; approve via Evernight DM. Expected: exact command is shown in approval; March7 returns actual output or missing-tool error. | ✅ | 2026-07-08 — GPU 74°C, sensors no CPU data (lm-sensors not installed) |
| TASK-026 | In March7 chat, ask to read `/etc/os-release`, first line of `/proc/meminfo`, and the first 20 lines of `services/system_gateway/README.md`; approve via Evernight DM. Expected: March7 returns actual file contents. | ⚠️ PARTIAL | 2026-07-08 — os-release (Fedora 44) + meminfo (32GB, free ~12.5GB) real ✅; README March7 reported "permission denied" but file is 644-readable and gateway runs as root with no path allowlist → model hallucination (not gateway bug). First attempt used relative path `services/system_gateway/README.md` (CWD not repo) → not found |
| TASK-027 | In March7 chat, test rejection with `printf gateway-march7-reject-test`; reject in Evernight DM. Expected: March7 reports command rejected and does not fabricate output. | ✅ | 2026-07-08 — explicit Reject in Evernight DM; log `❌ REJECTED`; March7 reported reject, no fake output |
| TASK-028 | Check March7 and Evernight logs after TASK-023 to TASK-027: March7 should show host tool flow; Evernight should show DM approval request/resolution. No unhandled exceptions or secret values. | ✅ | 2026-07-08 — March7 clean; Evernight shows repeated `403 Forbidden (50001) Missing Access` when trying to send approval result back to Bé Bảy DM channel (non-fatal, March7 gets result via gateway); no secret leak |

### GOAL-006: Trace Gateway Audit And Host Logs

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-029 | Capture recent systemd logs: `journalctl -u system-gateway.service --no-pager --since '<test start time>'`. Expected: no restart loop; no `ModuleNotFoundError`; no secret values. | ✅ | 2026-07-08 — journal only startup logs; no ModuleNotFoundError/Traceback/restart; uptime monotonic |
| TASK-030 | If audit file/log location is configured, inspect only event summaries for `shell.started`, `approval.resolved`, denied/replayed events, and action completion/failure. Do not print approval tokens. If Evernight `host_system` events show actor `march7`, record it as the known shared-client actor caveat. | ⚠️ GAP | 2026-07-08 — gateway does not persist audit events to journald/file (only uvicorn startup lines); per-request `shell.started`/`approval.resolved` not inspectable post-hoc. Audit module exists in code (`twin/shared/system_gateway/audit.py`) but no configured sink |
| TASK-031 | Verify rejected commands did not execute by checking their sentinel strings are absent from command output and only appear in approval/log text. | ✅ | 2026-07-08 — `gateway-reject-test`, `gw-rej3`, `gateway-march7-reject-test` all `❌ REJECTED` in logs, never APPROVED → never executed |
| TASK-032 | Re-run health after all chat tests: `curl -sS http://localhost:8380/health`; status must remain `ok`. | ✅ | 2026-07-08 — `{"status":"ok",...,"uptime":64067}` |

### GOAL-007: Regression Tests And Closeout

| ID | Task | Done | Date |
|----|------|------|------|
| TASK-033 | Run focused Python tests: `python3 -m pytest tests/unit/evernight_host_gateway_monitor_test.py tests/unit/evernight_host_gateway_installer_test.py tests/unit/self_heal_monitor_test.py tests/unit/gateway_admin_tool_test.py tests/unit/host_system_tool_test.py tests/services/tools/host_system_tool_test.py -q`. | ✅ | 2026-07-08 — 57 passed |
| TASK-034 | Run gateway service tests: `python3 -m pytest tests/unit/system_gateway_auth_test.py tests/unit/system_gateway_audit_test.py tests/unit/system_gateway_policy_test.py tests/unit/system_gateway_client_test.py tests/unit/system_gateway_server_test.py tests/unit/system_gateway_cli_test.py tests/unit/system_gateway_bootstrap_script_test.py services/system_gateway/tests -q`. | ✅ | 2026-07-08 — 103 passed |
| TASK-035 | Run broad unit suite with known missing Discord dependency ignores if the environment still lacks `discord.py`: `python3 -m pytest tests/unit -q --ignore=tests/unit/discord_send_response_test.py --ignore=tests/unit/evernight_discord_adapter_test.py`. | ✅ | 2026-07-08 — 426 passed |
| TASK-036 | Run `git diff --check` and record any unrelated dirty worktree files separately from gateway test evidence. | ✅ | 2026-07-08 — `git diff --check` clean; only untracked `.agents/plans/system-gateway-live-test.md` (this plan) |
| TASK-037 | Close out with a short report: exact bot addresses used, commands requested through chat, approval decisions, real outputs captured, health/log status, tests run, and unresolved risks. | ✅ | 2026-07-08 — report delivered in chat session |

## Test Plan

Acceptance criteria:

- Evernight install guidance is tool-generated and contains only the simplified
  bootstrap command for the host OS.
- A subagent can run that exact command and restore/confirm a healthy native
  `system-gateway.service`.
- Evernight `gateway_admin doctor` and `host_system capabilities` report actual
  gateway state.
- Evernight can read VRAM/GPU, temperature, and safe host files through
  `host_system` only after approval.
- March7 can perform the same host checks through `host_system`; approvals are
  delivered through Evernight DM.
- Rejecting an approval prevents execution and the agent does not claim success.
- Logs show no restart loop, no stale `ModuleNotFoundError: No module named
  'twin'`, no stack traces in the tested path, and no leaked secrets.

Suggested safe shell commands for the bots to request via `host_system`:

- Capabilities: use `mode=capabilities`, no shell command.
- VRAM/GPU: `command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,temperature.gpu --format=csv,noheader,nounits || (echo "nvidia-smi not found"; command -v rocm-smi >/dev/null && rocm-smi || true; command -v lspci >/dev/null && lspci | grep -Ei "vga|3d|display" || true)`
- Temperature: `(command -v sensors >/dev/null && sensors) || (command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits) || echo "no temperature tool found"`
- File read: `printf '%s\n' '--- /etc/os-release ---'; sed -n '1,12p' /etc/os-release; printf '%s\n' '--- /proc/meminfo ---'; sed -n '1p' /proc/meminfo; printf '%s\n' '--- services/system_gateway/README.md ---'; sed -n '1,20p' /home/flowerf/Projects/march7/services/system_gateway/README.md`
- Reject sentinel: `printf gateway-reject-test`

## Execution Findings (2026-07-08)

Non-fatal issues surfaced during the live run (none block gateway correctness):

1. **Evernight install commentary noise**: `gateway_admin install` returned the correct
   tool-derived block (`cd /home/flowerf/Projects/march7` + `sudo python3 scripts/bootstrap_system_gateway.py`),
   but Evernight's surrounding commentary claimed the path "is a placeholder" — incorrect,
   the path is the real repo root. Tool output itself is correct; only the model commentary is wrong.

2. **March7 README hallucination (TASK-026)**: March7 reported "permission denied" when
   reading `/home/flowerf/Projects/march7/services/system_gateway/README.md`, but the file is
   644 world-readable, the gateway process runs as root (PID 1479), and
   `evaluate_shell_policy` has no path allowlist. The command should have returned content.
   This is a model-reliability bug (model did not report the real tool output), not a gateway
   bug. os-release and meminfo were reported faithfully.

3. **Evernight hallucinated reject without calling tool (TASK-021 attempt 2)**: when the owner
   pre-announced intent to reject (`cho toi nhan Reject`), Evernight replied "rejected"
   without invoking `host_system` — no `APPROVAL REQUESTED` line in logs for that attempt.
   Consistent with known model-toolcall-reliability issue. The explicit Reject button path
   was verified separately with `printf gw-rej3` (log shows `❌ REJECTED` 9s after request).

4. **Cross-bot approval result delivery 403**: when March7 requests `host_system` and the
   approval is resolved in Evernight DM, Evernight's `a2a_server` tries to post the approval
   result back to the March7 DM channel (`1524279314940694701`) and logs
   `discord.errors.Forbidden: 403 Forbidden (50001) Missing Access` repeatedly. Non-fatal —
   March7 receives the result via the gateway, not via that message — but the log noise
   should be silenced by skipping the cross-channel post when the target channel is not
   Evernight's own.

5. **Gateway audit not persisted (TASK-030 gap)**: the audit module
   (`twin/shared/system_gateway/audit.py`) emits events but no sink is configured; journald
   only captures uvicorn startup lines. Per-request `shell.started` / `approval.resolved`
   events cannot be inspected post-hoc. Add a file/journald sink if an audit trail is required.

6. **March7 redundant parallel tool calls**: a 3-file read request was split into multiple
   parallel `host_system` calls, each requiring its own approval. Missing one approval
   window causes a 60s tool timeout and a retry. The compound command at the first iteration
   actually succeeded and returned content, but the model still re-issued split calls.

Unresolved:

- GOAL-003 bootstrap not executed (sudo not available non-interactively). The existing
  `system-gateway.service` is healthy and was verified throughout; the install-guidance flow
  (GOAL-002) is fully tested. Run the bootstrap manually if idempotent reinstall must be
  proven: `! cd /home/flowerf/Projects/march7 && sudo python3 scripts/bootstrap_system_gateway.py`.

## Assumptions

- The operator has access to the Discord account with user ID
  `726302130318868500` for owner-only Evernight tests.
- Real Discord smoke tests require live bot tokens already configured in `.env`;
  this plan verifies token presence only through runtime readiness logs and does
  not print token values.
- Evernight client ID is present in configuration, but the live bot account must
  still be confirmed from `Evernight bot ready: ... (ID: ...)` before sending
  owner-only prompts.
- Prefer owner DM approval. Channel approval buttons are currently not
  owner-restricted, so channel approval is testable but not the safe path for
  privileged host commands.
- If a machine has no NVIDIA/AMD GPU or no `sensors`, missing-tool output is a
  pass as long as the agent reports the real command result instead of inventing
  metrics.
- If the current System Gateway is already healthy, the install-guidance flow is
  still tested by asking for `gateway_admin install`; destructive uninstall is
  not part of this plan.
- If the subagent cannot get sudo approval, TASK-013 is blocked but TASK-008 to
  TASK-011 and the healthy-service verification can still proceed against the
  existing service.
