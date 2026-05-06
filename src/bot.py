import asyncio
import logging
import warnings

from dotenv import load_dotenv

# Load .env TRƯỚC khi import các module khác
load_dotenv()

import discord  # noqa: E402
from discord.ext import commands  # noqa: E402

from src.config.logging_config import setup_logging  # noqa: E402
from src.config.settings import Config  # noqa: E402
from src.services.dependencies import AppContainer  # noqa: E402

# Thiết lập Logging hệ thống
setup_logging()
logger = logging.getLogger("discord_bot.main")


class CoreBot(commands.Bot):
    def __init__(self):
        warnings.warn(
            "⚠️ Standalone mode is deprecated. Use 'python3 -m gateway' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        logger.warning("⚠️ Standalone mode is deprecated. Use 'python3 -m gateway' instead.")

        # Bật Intents để đọc được nội dung tin nhắn
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True  # Nếu bot cần chào người mới

        super().__init__(
            command_prefix=getattr(Config, "COMMAND_PREFIX", "!"),
            intents=intents,
            help_command=None,  # Tắt help mặc định nếu muốn tự custom
        )

    async def setup_hook(self):
        """Hàm này chạy 1 lần duy nhất trước khi bot on_ready.

        NOTE: Cog loading has been moved to gateway/adapters/discord/adapter.py.
        When running in gateway mode (python3 -m gateway), cogs are loaded by
        the DiscordPlatformAdapter._gateway_setup_hook().
        This method only initializes the AppContainer and NightlyTrigger for
        standalone fallback mode (python3 -m src), which is deprecated.
        """
        logger.info("⚙️ Đang mồi nổ hệ thống (Setup Hook)...")

        # 1. Kích hoạt Trạm Điện: Khởi tạo toàn bộ LLM và Memory 3 Tầng
        container = AppContainer.get_instance()
        await container.initialize()

        # 2. Khởi động NightlyTrigger (background task)
        if container.nightly_trigger:
            asyncio.create_task(container.nightly_trigger.start())
            logger.info("🌙 NightlyTrigger: Đã khởi động scheduled task (2 AM)")

        logger.warning("⚠️ Standalone mode is deprecated. Use 'python3 -m gateway' instead.")

    async def on_ready(self):
        logger.info(f"🚀 Bot đã online với tư cách: {self.user} (ID: {self.user.id})")
        # Đổi status của bot cho ngầu
        await self.change_presence(
            activity=discord.Game(name="Đang đồng bộ Trí nhớ...")
        )

    async def close(self):
        """Dọn dẹp tài nguyên trước khi tắt bot."""
        logger.info("🛑 Đang tắt bot và ngắt kết nối an toàn...")
        await AppContainer.get_instance().shutdown()
        await super().close()


def main():
    logger.warning("⚠️ Standalone mode is deprecated. Use 'python3 -m gateway' instead.")
    if not Config.DISCORD_BOT_TOKEN:
        logger.critical("❌ Không tìm thấy DISCORD_BOT_TOKEN trong file .env!")
        return

    logger.info(f"🔧 LLM_PROVIDER: {Config.LLM_PROVIDER}")
    bot = CoreBot()
    bot.run(Config.DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
