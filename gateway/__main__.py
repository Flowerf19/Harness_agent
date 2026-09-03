"""Entry point for ``python -m gateway``.

Loads configuration from environment variables, initialises the gateway
orchestrator and all configured platform adapters, then runs until
SIGINT / SIGTERM.

NOTE: This gateway ONLY boots the March7 agent. Evernight runs in its
own container and is reached via A2A HTTP.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from dotenv import load_dotenv

load_dotenv(override=True)

from twin.shared.config.logging_config import setup_logging

setup_logging()

_discord_client_logger = logging.getLogger("discord.client")
_discord_client_logger.addFilter(lambda record: "Attempting a reconnect" not in record.getMessage())

logger = logging.getLogger("gateway.main")


async def _run_gateway() -> None:
    from gateway.config import GatewayConfig
    from gateway.gateway import ChatGateway
    from gateway.core.agent_router import AgentRouter
    from gateway.core.handler import GatewayChatHandler
    from gateway.adapters.factory import create_adapters
    from twin.march7.container import March7Container
    from twin.march7.config import March7Config

    config = GatewayConfig.from_env()
    logger.info("Gateway configuration: enabled_platforms=%s", config.enabled_platforms)

    # Initialise March7 agent in-process (Evernight is in separate container)
    march7_container = March7Container.get_instance(config=March7Config.from_env())
    await march7_container.initialize()

    # Evernight A2A client (HTTP to evernight container)
    evernight_client = None
    from twin.shared.config.settings import Config
    evernight_url = getattr(Config, "EVERNIGHT_A2A_URL", None)
    if evernight_url:
        from gateway.core.evernight_client import EvernightClient
        evernight_client = EvernightClient(base_url=evernight_url)
        logger.info("Evernight A2A client configured: %s", evernight_url)

    agent_router = AgentRouter(
        march7=march7_container.agent,
        evernight_client=evernight_client,
    )

    handler = GatewayChatHandler(agent_router=agent_router)
    gateway = ChatGateway(handler)

    # Create and register adapters
    adapters = create_adapters(config, gateway)
    for name, adapter in adapters.items():
        gateway.register_adapter(name, adapter)

    # March7 A2A server (port 8000) — for Evernight and external callers.
    # Health reflects the platform links, not just this HTTP server: the process
    # stays reachable while a disconnected bot makes it useless.
    from twin.march7.server.a2a_server import start_server
    a2a_server = start_server(
        march7_container.agent,
        port=march7_container.config.port,
        health_probe=lambda: gateway.is_healthy,
    )
    await a2a_server.start()
    logger.info(f"March7 A2A server listening on port {march7_container.config.port}")

    if not gateway.adapter_names:
        logger.warning("No platform adapters registered")
        return

    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("Received shutdown signal …")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await gateway.start_all()
    await shutdown_event.wait()

    await gateway.stop_all()
    await agent_router.close()

    await a2a_server.stop()
    await march7_container.shutdown()
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
