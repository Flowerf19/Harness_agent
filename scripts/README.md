# scripts/ — utility entry points

This directory holds standalone helper scripts. Most runtime services now
live under `services/` or `twin/`; this directory is for one-off operational
helpers only. Host interaction belongs in `services/system_gateway/`.

## migrate_t3_5to8.py

- One-off migration helper for T3 markdown profiles. Safe to keep running.
