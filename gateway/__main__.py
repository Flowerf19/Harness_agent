"""Entry point for ``python3 -m gateway``.

Loads configuration from environment variables, initialises the gateway
orchestrator and all configured platform adapters, then runs until
SIGINT / SIGTERM.
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
    from gateway.adapters.discord.agent_router import AgentRouter
    from gateway.adapters.discord.handler import DiscordGatewayHandler
    from gateway.adapters.factory import create_adapters
    from twin.march7.container import March7Container
    from twin.march7.config import March7Config
    from twin.evernight.container import EvernightContainer
    from twin.evernight.config import EvernightConfig

    config = GatewayConfig.from_env()
    logger.info("Gateway configuration: enabled_platforms=%s", config.enabled_platforms)

    # Initialise agent containers in-process
    march7_container = March7Container.get_instance(config=March7Config.from_env())
    await march7_container.initialize()

    evernight_container = EvernightContainer.get_instance(config=EvernightConfig.from_env())
    await evernight_container.initialize()

    agent_router = AgentRouter(
        march7=march7_container.agent,
        evernight=evernight_container.agent,
    )

    handler = DiscordGatewayHandler(agent_router=agent_router)
    gateway = ChatGateway(handler)

    # Create and register adapters
    adapters = create_adapters(config, gateway)
    for name, adapter in adapters.items():
        gateway.register_adapter(name, adapter)

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
    await march7_container.shutdown()
    await evernight_container.shutdown()
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
