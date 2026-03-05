import asyncio
import logging
import os
import sys

import discord  # type: ignore
from discord.ext import commands  # type: ignore
from dotenv import load_dotenv

# Add project root to path for importing services
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Load environment variables before importing Config
load_dotenv()

# Import Config from settings
from src.config.settings import Config  # noqa: E402

# Phoenix tracing setup
sys.path.insert(0, "/home/flowerf/Projects/Arize_Phoenix_tool_kit")
from phoenix_core import setup_tracking

# Setup Phoenix tracing
setup_tracking(
    project_name="Be_Bay_Bot",
    frameworks=["langchain"],  # Bật LangChain auto-instrumentation
)

# Simplified logging configuration
logging.basicConfig(
    level=getattr(
        logging, Config.LOG_LEVEL.upper(), logging.INFO
    ),  # Use Config.LOG_LEVEL with fallback to INFO
    format="%(asctime)s - %(levelname)s - %(message)s",  # Simplified format
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("discord_bot")

logger.info("🚀 Starting Discord Bot...")

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None,
    case_insensitive=True,
    strip_after_prefix=True,
    max_messages=Config.MAX_MESSAGES,
)


@bot.event
async def on_ready():
    logger.info(f"🚀 Bot started as {bot.user} in {len(bot.guilds)} guilds")

    if os.getenv("SYNC_COMMANDS") == "1":
        try:
            await bot.tree.sync()
            logger.info("✅ Slash commands synced")
        except Exception as e:
            logger.warning(f"⚠️ Slash command sync failed: {e}")


@bot.event
async def on_error(event, *args, **kwargs):
    logger.error(f"❌ Unhandled error in {event}", exc_info=True)


async def load_cogs():
    """Load all cogs from cogs directory"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    cogs_dir = os.path.join(current_dir, "cogs")

    if not os.path.exists(cogs_dir):
        logger.warning(f"⚠️ Cogs directory not found: {cogs_dir}")
        return

    cog_files = [
        f"cogs.{filename[:-3]}"
        for filename in os.listdir(cogs_dir)
        if filename.endswith(".py") and not filename.startswith("__")
    ]

    if not cog_files:
        logger.warning("⚠️ No cog files found")
        return

    loaded = 0
    for cog_name in cog_files:
        try:
            await bot.load_extension(cog_name)
            loaded += 1
            logger.info(f"✅ Loaded {cog_name}")
        except Exception as e:
            logger.error(f"❌ Failed to load {cog_name}: {e}")

    logger.info(f"📦 Loaded {loaded}/{len(cog_files)} cogs")


async def main():
    try:
        async with bot:
            await load_cogs()

            token = os.getenv("DISCORD_LLM_BOT_TOKEN")
            if not token:
                logger.error("❌ No Discord token found in environment")
                return

            await bot.start(token)

    except discord.LoginFailure:
        logger.error("❌ Invalid Discord token")
    except Exception as e:
        logger.error(f"❌ Bot startup failed: {e}")
    finally:
        if not bot.is_closed():
            await bot.close()
        logger.info("🔒 Bot shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
