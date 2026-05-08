"""Entry point for ``python3 -m gateway``.

Loads configuration from environment variables, initialises the shared
``AppContainer`` (the platform-agnostic brain), instantiates the gateway
orchestrator and all configured platform adapters, then runs until
SIGINT / SIGTERM.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

# Load .env before anything else.
from dotenv import load_dotenv

load_dotenv(override=True)

from src.config.logging_config import setup_logging  # noqa: E402

setup_logging()

# Suppress discord.py internal reconnect stack traces.
# discord.client logs verbose tracebacks on every network hiccup.
# Our adapter already classifies errors cleanly — we don't need the dump.
_discord_client_logger = logging.getLogger("discord.client")
_discord_client_logger.addFilter(lambda record: "Attempting a reconnect" not in record.getMessage())

logger = logging.getLogger("gateway.main")


async def _run_gateway() -> None:
    from gateway.config import GatewayConfig  # noqa: E402
    from gateway.gateway import ChatGateway  # noqa: E402
    from gateway.adapters.factory import create_adapter  # noqa: E402

    config = GatewayConfig.from_env()
    logger.info("Gateway configuration: enabled_platforms=%s", config.enabled_platforms)

    # Lazy import of handler — avoids circular imports with src/.
    from gateway.adapters.discord.handler import DiscordGatewayHandler  # noqa: E402

    handler = DiscordGatewayHandler()
    gateway = ChatGateway(handler)

    # Create and register adapters based on config.
    for platform_name in config.enabled_platforms:
        if not config.platform_enabled(platform_name):
            logger.info("Platform %s is disabled in config — skipping", platform_name)
            continue
        try:
            adapter = create_adapter(platform_name, config, gateway=gateway)
            gateway.register_adapter(platform_name, adapter)
        except Exception:
            logger.exception("Failed to create adapter for %s — skipping", platform_name)

    if not gateway.adapter_names:
        logger.warning("No platform adapters registered — gateway will do nothing.")
        return

    # Set up graceful shutdown on SIGINT / SIGTERM.
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Received shutdown signal …")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    # Start all adapters.
    await gateway.start_all()

    # Wait until shutdown signal.
    await shutdown_event.wait()

    # Stop everything gracefully.
    await gateway.stop_all()
    logger.info("Gateway shut down cleanly.")


def main() -> None:
    try:
        asyncio.run(_run_gateway())
    except KeyboardInterrupt:
        pass
    except Exception:
        logger.exception("Gateway crashed")
        sys.exit(1)


if __name__ == "__main__":
    main()
