"""Discord cogs for the gateway adapter."""
from discord.ext import commands


async def setup(bot: commands.Bot):
    await bot.load_extension("gateway.adapters.discord.cogs.admin_channels")
