"""Entry point for March7 Agent."""
import asyncio
import logging
import signal
import sys

from dotenv import load_dotenv

load_dotenv(override=True)

from twin.shared.config.logging_config import setup_logging

setup_logging()

logger = logging.getLogger("march7.main")


async def main():
    from twin.march7.config import March7Config
    from twin.march7.container import March7Container
    from twin.march7.a2a.server import start_server
    from twin.evernight.triggers.inactivity_trigger import InactivityTrigger

    config = March7Config.from_env()
    container = March7Container(config)
    await container.initialize()

    server = start_server(container.agent, port=config.port)
    await server.start()

    logger.info(f"March7 Agent listening on port {config.port}")

    # Background poller that drives SummaryPolicy for both user and channel scopes
    trigger = None
    if container.state_repo is not None and container.summary_policy is not None:
        poll_interval = int(getattr(config, "poll_interval", 60))
        trigger = InactivityTrigger(
            state_repo=container.state_repo,
            summary_policy=container.summary_policy,
            scopes=("user", "channel"),
            poll_interval=poll_interval,
        )
        await trigger.start()
        logger.info("March7 InactivityTrigger started (poll=%ss)", poll_interval)

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
    logger.info("March7 Agent shut down")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        logger.exception("March7 crashed")
        sys.exit(1)
