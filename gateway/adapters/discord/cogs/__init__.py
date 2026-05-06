"""Discord cogs for the gateway adapter."""
from discord.ext import commands


async def setup(bot: commands.Bot):
    await bot.load_extension("gateway.adapters.discord.cogs.chat_gateway")
    await bot.load_extension("gateway.adapters.discord.cogs.admin_channels")
    await bot.load_extension("gateway.adapters.discord.cogs.user_commands")
    await bot.load_extension("gateway.adapters.discord.cogs.base_cog")
    await bot.load_extension("gateway.adapters.discord.cogs.server_relationships")
