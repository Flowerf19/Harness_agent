# scripts/ — System Gateway bootstrap and operational scripts

This directory holds standalone operational helpers. Most runtime services now
live under `services/` or `twin/`; this directory is for one-off host/bootstrap
tasks only.

## bootstrap_system_gateway.py

- Installs the native System Gateway service on the host (systemd/launchd/Windows
  service packaging) from `services/system_gateway/`.
- Run on the host, not inside a container.

## calibrate_t2.py

- Calibrates T2 memory thresholds (`T2_MIN_COSINE`, merge gate, etc.) against
  the configured embedding model and a sample dataset.

## migrate_t3_5to8.py

- One-off migration helper for T3 markdown profiles. Safe to keep running.
