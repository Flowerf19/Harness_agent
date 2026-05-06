import discord
from discord.ext import commands


class UserCommandsCog(commands.Cog):
    """User-facing commands"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ping")
    async def ping_command(self, ctx):
        """Simple ping command to test if bot is responsive"""
        await ctx.reply("🏓 Pong! Bot đang hoạt động!")

    @commands.command(name="status")
    async def status_command(self, ctx):
        """Check bot status and configuration"""
        llm_cog = self.bot.get_cog("LLMMessageCog")
        if not llm_cog:
            await ctx.reply("❌ LLM service not available")
            return

        embed = discord.Embed(title="🤖 Bot Status", color=discord.Color.green())

        # Basic info
        if ctx.guild:
            admin_cog = self.bot.get_cog("AdminChannels")
            if admin_cog and admin_cog.is_bot_channel(ctx.guild.id, ctx.channel.id):
                embed.add_field(name="Kênh này", value="✅ Bot channel", inline=True)
            else:
                embed.add_field(name="Kênh này", value="⚠️ Cần mention bot", inline=True)
        else:
            embed.add_field(name="Loại kênh", value="📩 DM", inline=True)

        # User stats
        user_id = str(ctx.author.id)
        # TODO: Cần tích hợp lại với memory system mới - hiện tại conversation_manager không còn tồn tại
        # history = llm_cog.conversation_manager.get_persistent_history(user_id)
        history = []  # Tạm thời trả về rỗng cho đến khi tích hợp memory mới
        # Đọc summary từ file trực tiếp
        summary = await self._get_user_summary(llm_cog, user_id)

        embed.add_field(name="Lịch sử", value=f"{len(history)} tin nhắn", inline=True)
        embed.add_field(
            name="Tóm tắt", value="✅ Có" if summary else "❌ Chưa có", inline=True
        )

        await ctx.reply(embed=embed)

    async def _get_user_summary(self, llm_cog, user_id: str) -> str:
        """Get user summary from file asynchronously"""
        import os

        import aiofiles

        base_dir = os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(
                        os.path.dirname(os.path.abspath(__file__))
                    )
                )
            )
        )
        # Đọc từ memories/users/ thay vì data/user_summaries/
        summary_file = os.path.join(
            base_dir, "memories", "users", f"{user_id}.md"
        )

        try:
            async with aiofiles.open(summary_file, "r", encoding="utf-8") as f:
                return await f.read()
        except FileNotFoundError:
            # Return empty string if file doesn't exist
            return ""
        except Exception as e:
            print(f"Error reading user summary for {user_id}: {e}")
            return ""


async def setup(bot):
    await bot.add_cog(UserCommandsCog(bot))
