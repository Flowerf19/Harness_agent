from discord.ext import commands
import os

class ServerRelationshipsCog(commands.Cog):
    """
    Cog to provide commands for querying server-wide relationship summary.
    """
    def __init__(self, bot):
        self.bot = bot
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.server_summary_path = os.path.join(base_dir, 'data', 'server_relationships.txt')

    @commands.command(name='server_relationships')
    async def server_relationships_command(self, ctx):
        """Show the server-wide relationship summary (AI-generated)"""
        if not os.path.exists(self.server_summary_path):
            await ctx.reply("Chưa có tổng kết mối quan hệ server.")
            return
        with open(self.server_summary_path, 'r', encoding='utf-8') as f:
            summary = f.read()
        # Discord message limit
        if len(summary) <= 2000:
            await ctx.reply(summary)
        else:
            # Split and send in parts
            parts = [summary[i:i+2000] for i in range(0, len(summary), 2000)]
            for i, part in enumerate(parts):
                if i == 0:
                    await ctx.reply(part)
                else:
                    await ctx.send(part)

async def setup(bot):
    await bot.add_cog(ServerRelationshipsCog(bot))
