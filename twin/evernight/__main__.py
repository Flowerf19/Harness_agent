"""Entry point for Evernight Agent."""
import asyncio
import logging
import signal
import sys

from dotenv import load_dotenv

load_dotenv(override=True)

from twin.shared.config.logging_config import setup_logging

setup_logging()

logger = logging.getLogger("evernight.main")


async def main():
    from twin.evernight.config import EvernightConfig
    from twin.evernight.container import EvernightContainer
    from twin.evernight.server.a2a_server import start_server
    from twin.evernight.triggers.inactivity_trigger import InactivityTrigger

    config = EvernightConfig.from_env()
    container = EvernightContainer(config)
    await container.initialize()

    server = start_server(container.agent, port=config.port)
    await server.start()
    logger.info(f"Evernight Agent listening on port {config.port}")

    # Start inactivity trigger if Redis is available
    trigger = None
    if container.redis_client:
        trigger = InactivityTrigger(
            redis_client=container.redis_client,
            evernight_agent=container.agent,
            inactivity_seconds=config.inactivity_seconds,
            poll_interval=config.poll_interval,
        )
        await trigger.start()
    else:
        logger.warning("Redis not available - inactivity trigger disabled")

    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _signal_handler():
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await shutdown_event.wait()

    if trigger:
        await trigger.stop()
    await server.stop()
    await container.shutdown()
    logger.info("Evernight Agent shut down")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        logger.exception("Evernight crashed")
        sys.exit(1)
