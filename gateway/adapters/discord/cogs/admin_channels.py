# filepath: discord-bot-gemini/src/cogs/admin_channels.py

import json
import logging
import os
from enum import Enum

import discord  # type: ignore
from discord import app_commands  # type: ignore
from discord.ext import commands  # type: ignore

logger = logging.getLogger("discord_bot.AdminChannels")


class ChannelMode(str, Enum):
    OBSERVE_ONLY = "observe"
    RESPOND_ALLOWED = "respond"


class AdminChannels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_file = os.path.join(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(
                        os.path.dirname(
                            os.path.dirname(__file__)
                        )
                    )
                )
            ),
            "data",
            "bot_channels.json",
        )
        self.bot_channels = self.load_bot_channels()

    def load_bot_channels(self):
        """Load bot channels from file"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return self._normalize_channels(data)
            return {}
        except Exception as e:
            logger.error(f"Error loading bot channels: {e}")
            return {}

    def _normalize_channels(self, data):
        """Migrate old list storage to {channel_id: mode}."""
        normalized = {}
        for guild_id, channels in (data or {}).items():
            if isinstance(channels, list):
                normalized[guild_id] = {
                    str(channel_id): ChannelMode.RESPOND_ALLOWED.value
                    for channel_id in channels
                }
            elif isinstance(channels, dict):
                normalized[guild_id] = {
                    str(channel_id): (
                        mode
                        if mode in {ChannelMode.OBSERVE_ONLY.value, ChannelMode.RESPOND_ALLOWED.value}
                        else ChannelMode.RESPOND_ALLOWED.value
                    )
                    for channel_id, mode in channels.items()
                }
        return normalized

    def save_bot_channels(self):
        """Save bot channels to file"""
        try:
            os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self.bot_channels, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving bot channels: {e}")

    def is_bot_channel(self, guild_id: int, channel_id: int) -> bool:
        """Backward-compatible helper: true if channel has any configured mode."""
        return self.get_mode(guild_id, channel_id) is not None

    def get_mode(self, guild_id: int, channel_id: int) -> ChannelMode | None:
        """Return configured channel mode, or None when channel is not enabled."""
        guild_str = str(guild_id)
        if guild_str not in self.bot_channels:
            return None
        mode = self.bot_channels[guild_str].get(str(channel_id))
        return ChannelMode(mode) if mode else None

    def _set_channel_mode(self, guild_id: int, channel_id: int, mode: ChannelMode) -> bool:
        guild_str = str(guild_id)
        self.bot_channels.setdefault(guild_str, {})
        channel_str = str(channel_id)
        changed = self.bot_channels[guild_str].get(channel_str) != mode.value
        self.bot_channels[guild_str][channel_str] = mode.value
        self.save_bot_channels()
        return changed

    def _remove_channel(self, guild_id: int, channel_id: int) -> bool:
        guild_str = str(guild_id)
        channel_str = str(channel_id)
        if guild_str not in self.bot_channels or channel_str not in self.bot_channels[guild_str]:
            return False
        del self.bot_channels[guild_str][channel_str]
        if not self.bot_channels[guild_str]:
            del self.bot_channels[guild_str]
        self.save_bot_channels()
        return True

    # Slash Commands
    @app_commands.command(
        name="addbotchannel", description="Thêm kênh cho bot hoạt động"
    )
    @app_commands.describe(channel="Kênh muốn thêm bot", mode="observe hoặc respond")
    @commands.has_permissions(manage_channels=True)
    async def add_bot_channel_slash(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        mode: str = ChannelMode.RESPOND_ALLOWED.value,
    ):
        """Add a channel where bot can operate"""
        mode_enum = ChannelMode(mode) if mode in {m.value for m in ChannelMode} else ChannelMode.RESPOND_ALLOWED
        changed = self._set_channel_mode(interaction.guild.id, channel.id, mode_enum)

        if changed:
            embed = discord.Embed(
                title="✅ Đã thêm kênh bot",
                description=f"{channel.mention}: `{mode_enum.value}`",
                color=discord.Color.green(),
            )
            await interaction.response.send_message(embed=embed)
        else:
            embed = discord.Embed(
                title="⚠️ Kênh đã tồn tại",
                description=f"{channel.mention} đã được thêm trước đó",
                color=discord.Color.yellow(),
            )
            await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="removebotchannel", description="Xóa kênh khỏi danh sách bot"
    )
    @app_commands.describe(channel="Kênh muốn xóa bot")
    @commands.has_permissions(manage_channels=True)
    async def remove_bot_channel_slash(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        """Remove a channel from bot operation"""
        if self._remove_channel(interaction.guild.id, channel.id):
            embed = discord.Embed(
                title="✅ Đã xóa kênh bot",
                description=f"Bot không còn hoạt động trong {channel.mention}",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed)
        else:
            embed = discord.Embed(
                title="⚠️ Kênh không tồn tại",
                description=f"{channel.mention} không có trong danh sách bot channels",
                color=discord.Color.yellow(),
            )
            await interaction.response.send_message(embed=embed)

    @app_commands.command(name="listbotchannels", description="Xem danh sách kênh bot")
    async def list_bot_channels_slash(self, interaction: discord.Interaction):
        """List all bot channels for this guild"""
        guild_id = str(interaction.guild.id)

        embed = discord.Embed(title="📋 Danh sách kênh bot", color=discord.Color.blue())

        if guild_id not in self.bot_channels or not self.bot_channels[guild_id]:
            embed.description = (
                "Bot có thể hoạt động ở tất cả các kênh (chưa có hạn chế)"
            )
        else:
            channels = []
            for channel_id, mode in self.bot_channels[guild_id].items():
                channel = interaction.guild.get_channel(int(channel_id))
                if channel:
                    channels.append(f"• {channel.mention} `{mode}`")
                else:
                    channels.append(f"• Kênh đã bị xóa (ID: {channel_id})")

            embed.description = "\n".join(channels) if channels else "Không có kênh nào"

        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="clearbotchannels",
        description="Xóa tất cả kênh bot (bot hoạt động ở mọi nơi)",
    )
    @commands.has_permissions(manage_channels=True)
    async def clear_bot_channels_slash(self, interaction: discord.Interaction):
        """Clear all bot channels for this guild"""
        guild_id = str(interaction.guild.id)

        if guild_id in self.bot_channels:
            del self.bot_channels[guild_id]
            self.save_bot_channels()

        embed = discord.Embed(
            title="✅ Đã xóa tất cả kênh bot",
            description="Bot bây giờ có thể hoạt động ở tất cả các kênh",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)

    # Prefix Commands (for backward compatibility)
    @commands.command(name="addbotchannel")
    @commands.has_permissions(manage_channels=True)
    async def add_bot_channel(
        self,
        ctx,
        channel: discord.TextChannel = None,
        mode: str = ChannelMode.RESPOND_ALLOWED.value,
    ):
        """Add a channel where bot can operate"""
        if channel is None:
            channel = ctx.channel

        mode_enum = ChannelMode(mode) if mode in {m.value for m in ChannelMode} else ChannelMode.RESPOND_ALLOWED
        if self._set_channel_mode(ctx.guild.id, channel.id, mode_enum):
            await ctx.send(f"✅ Đã thêm {channel.mention} vào danh sách kênh bot (`{mode_enum.value}`)")
        else:
            await ctx.send(f"⚠️ {channel.mention} đã có trong danh sách")

    @commands.command(name="removebotchannel")
    @commands.has_permissions(manage_channels=True)
    async def remove_bot_channel(self, ctx, channel: discord.TextChannel = None):
        """Remove a channel from bot operation"""
        if channel is None:
            channel = ctx.channel

        if self._remove_channel(ctx.guild.id, channel.id):
            await ctx.send(f"✅ Đã xóa {channel.mention} khỏi danh sách kênh bot")
        else:
            await ctx.send(f"⚠️ {channel.mention} không có trong danh sách")

    @commands.command(name="listbotchannels")
    async def list_bot_channels(self, ctx):
        """List all bot channels for this guild"""
        guild_id = str(ctx.guild.id)

        if guild_id not in self.bot_channels or not self.bot_channels[guild_id]:
            await ctx.send("📋 Bot có thể hoạt động ở tất cả các kênh")
        else:
            channels = []
            for channel_id, mode in self.bot_channels[guild_id].items():
                channel = ctx.guild.get_channel(int(channel_id))
                if channel:
                    channels.append(f"• {channel.mention} `{mode}`")

            if channels:
                await ctx.send("📋 **Danh sách kênh bot:**\n" + "\n".join(channels))
            else:
                await ctx.send("📋 Không có kênh bot nào")

    @commands.command(name="clearbotchannels")
    @commands.has_permissions(manage_channels=True)
    async def clear_bot_channels(self, ctx):
        """Clear all bot channels for this guild"""
        guild_id = str(ctx.guild.id)

        if guild_id in self.bot_channels:
            del self.bot_channels[guild_id]
            self.save_bot_channels()

        await ctx.send("✅ Đã xóa tất cả kênh bot. Bot bây giờ hoạt động ở mọi kênh.")

    # Error handlers
    @add_bot_channel_slash.error
    @remove_bot_channel_slash.error
    @clear_bot_channels_slash.error
    async def slash_command_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(
                title="❌ Không có quyền",
                description="Bạn cần quyền **Manage Channels** để sử dụng lệnh này",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AdminChannels(bot))
