# scripts/ — utility entry points

This directory holds standalone helper scripts. Most runtime services now
live under `services/` or `twin/`; the entries here are kept for back-compat
and operational tooling.

## bash_executor_standalone.py — **LEGACY / DEPRECATED**

- Linux-only HTTP endpoint that runs `bash -c` on the host.
- Trusts caller identity via the `Origin` header against
  `BASH_EXECUTOR_ALLOWED_ORIGINS`.
- Container-side callers should migrate to the native
  `system-gateway` service (`services/system_gateway/`) which uses HMAC
  request signing, nonce + timestamp replay protection, and per-request
  approval binding.
- The `twin.shared.system_gateway.legacy.LegacyBashExecutorBridge` adapter
  bridges a small read-only subset of actions through this script while the
  native gateway is being rolled out.
- **Do not add new functionality here.** New host interactions belong in
  the native gateway plus its platform adapters.

## bash_executor_starter.py — **LEGACY**

- Helper that the Docker container calls to start/stop the bash-executor
  service on the host. Becomes unnecessary once the native gateway is
  managed by systemd/launchd on the host OS.

## migrate_t3_5to8.py

- One-off migration helper for T3 markdown profiles. Safe to keep running.
