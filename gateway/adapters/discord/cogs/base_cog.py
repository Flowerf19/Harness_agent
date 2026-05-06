from discord.ext import commands

class BaseCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{self.__class__.__name__} is ready.")

    @commands.Cog.listener()
    async def on_error(self, event, *args, **kwargs):
        print(f"An error occurred in {event}: {args}, {kwargs}")

    # Add more common methods for cogs here as needed.

async def setup(bot):
    await bot.add_cog(BaseCog(bot))
