"""Entry point for Evernight Agent."""
import asyncio
import logging
import os
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
    from twin.evernight.consolidation_runner import (
        ConsolidationRunner,
        March7MemoryClient,
    )
    from twin.evernight.triggers.inactivity_trigger import InactivityTrigger
    from twin.evernight.self_heal.monitor import SelfHealMonitor
    from twin.shared.config.settings import Config

    config = EvernightConfig.from_env()
    container = EvernightContainer(config)
    await container.initialize()

    # Start Evernight Discord bot first if token is set (needed for approval DM endpoint)
    evernight_adapter = None
    discord_token = config.discord_evernight_token
    if discord_token:
        from gateway.adapters.discord.evernight_adapter import EvernightDiscordAdapter
        evernight_adapter = EvernightDiscordAdapter(
            token=discord_token,
            agent=container.agent,
        )
        await evernight_adapter.connect()
        logger.info("Evernight Discord bot started")

    # Start A2A server with Discord bot reference for approval DM support
    from twin.evernight.server.a2a_server import start_server
    discord_bot = evernight_adapter.bot if evernight_adapter else None
    server = start_server(container.agent, port=config.port, discord_bot=discord_bot)
    await server.start()
    logger.info(f"Evernight Agent listening on port {config.port}")

    march7_memory = March7MemoryClient(march7_url=config.march7_url)
    consolidation_runner = ConsolidationRunner(
        evernight_agent=container.agent,
        march7_memory=march7_memory,
    )

    # Start self-healing monitor
    self_heal = None
    if config.self_heal_enabled:
        self_heal = SelfHealMonitor(
            march7_url=config.march7_url,
            interval=config.self_heal_interval,
            timeout=config.self_heal_timeout,
            discord_adapter=evernight_adapter,
            bash_executor_url=Config.BASH_EXECUTOR_URL,
        )
        await self_heal.start()
        logger.info(f"Self-heal monitor started (interval={config.self_heal_interval}s)")

    # Start queue worker and inactivity trigger against March7's coordination Redis.
    trigger = None
    memory_worker = None
    coordination_storage = None
    try:
        from twin.evernight.memories.activate_memory.storage.redis_storage import create_redis_storage

        coordination_storage = create_redis_storage(
            redis_url=Config.REDIS_URL,
            redis_password=Config.REDIS_PASSWORD,
            redis_db=int(os.getenv("MARCH7_REDIS_DB", "0")),
        )
        if not await coordination_storage.health_check():
            await coordination_storage.close()
            coordination_storage = None
    except Exception:
        logger.exception("Coordination Redis unavailable - inactivity trigger disabled")

    if coordination_storage:
        from twin.shared.memories.t2 import MemoryJobQueue, MemoryWorker

        memory_worker = MemoryWorker(
            queue=MemoryJobQueue(coordination_storage.redis),
            evernight_agent=container.agent,
            march7_memory=march7_memory,
            poll_interval=2.0,
        )
        await memory_worker.start()

        trigger = InactivityTrigger(
            redis_client=coordination_storage.redis,
            consolidation_runner=consolidation_runner,
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

    # Cleanup in reverse order
    if evernight_adapter:
        await evernight_adapter.disconnect()
    if self_heal:
        await self_heal.stop()
    if trigger:
        await trigger.stop()
    if memory_worker:
        await memory_worker.stop()
    await consolidation_runner.close()
    if coordination_storage:
        await coordination_storage.close()
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
