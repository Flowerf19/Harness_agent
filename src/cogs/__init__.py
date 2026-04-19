# filepath: discord-bot-gemini/src/cogs/__init__.py
from discord.ext import commands

async def setup(bot: commands.Bot):
    await bot.load_extension("cogs.admin_channels")
    await bot.load_extension("cogs.base_cog")
    await bot.load_extension("cogs.llm_message")
    await bot.load_extension("cogs.server_relationships")