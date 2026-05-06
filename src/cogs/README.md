# Legacy Cogs Directory

This directory previously contained Discord cogs for the standalone bot mode
(`python3 -m src`). All cogs have been moved to:

```
gateway/adapters/discord/cogs/
```

## Migrated Cogs

| Original | New Location |
|----------|-------------|
| `src/cogs/chat_gateway.py` | `gateway/adapters/discord/cogs/chat_gateway.py` |
| `src/cogs/user_commands.py` | `gateway/adapters/discord/cogs/user_commands.py` |
| `src/cogs/admin_channels.py` | `gateway/adapters/discord/cogs/admin_channels.py` |
| `src/cogs/base_cog.py` | `gateway/adapters/discord/cogs/base_cog.py` |
| `src/cogs/server_relationships.py` | `gateway/adapters/discord/cogs/server_relationships.py` |

## Why?

The bot has transitioned to a **Gateway Orchestrator** architecture where
`python3 -m gateway` is the sole entry point. Cogs are now loaded through
`DiscordPlatformAdapter._gateway_setup_hook()` instead of `CoreBot.setup_hook()`.

## Cleanup

The `__pycache__/` subdirectory contains stale `.pyc` files from the old
location. It is safe to delete manually:

```bash
sudo rm -rf src/cogs/__pycache__
```

This directory exists for historical reference only. No source files should
be placed here.
