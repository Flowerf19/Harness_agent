import asyncio
import logging

from dotenv import load_dotenv

load_dotenv(override=True)

import discord
from discord.ext import commands

from twin.shared.config.logging_config import setup_logging
from twin.shared.config.settings import Config

setup_logging()
logger = logging.getLogger("discord_bot.main")


class CoreBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix=getattr(Config, "COMMAND_PREFIX", "!"),
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self):
        logger.info("CoreBot: setup_hook (overridden by gateway adapter)")

    async def on_ready(self):
        logger.info(f"Bot online as {self.user} (ID: {self.user.id})")
        await self.change_presence(
            activity=discord.Game(name="Đang đồng bộ Trí nhớ...")
        )

    async def close(self):
        logger.info("Shutting down bot...")
        await super().close()
