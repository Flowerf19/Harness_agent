import logging

from dotenv import load_dotenv

# Load .env TRƯỚC khi import các module khác
load_dotenv()

import discord
from discord.ext import commands

from src.config.logging_config import setup_logging
from src.config.settings import Config
from src.services.dependencies import AppContainer

# Thiết lập Logging hệ thống
setup_logging()
logger = logging.getLogger("discord_bot.main")


class CoreBot(commands.Bot):
    def __init__(self):
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
        """Hàm này chạy 1 lần duy nhất trước khi bot on_ready."""
        logger.info("⚙️ Đang mồi nổ hệ thống (Setup Hook)...")

        # 1. Kích hoạt Trạm Điện: Khởi tạo toàn bộ LLM và Memory 3 Tầng
        await AppContainer.get_instance().initialize()

        # 2. Load các Trạm kiểm soát Discord (Cogs)
        try:
            # Load file giao tiếp chính (Ta sẽ viết file này thay cho llm_message cũ)
            await self.load_extension("src.cogs.chat_gateway")

            # Load các cogs phụ trợ khác nếu bạn vẫn xài (admin, commands...)
            await self.load_extension("src.cogs.user_commands")
            await self.load_extension("src.cogs.admin_channels")

            logger.info("✅ Đã nạp thành công các Cogs!")
        except Exception as e:
            logger.error(f"❌ Lỗi khi nạp Cogs: {e}")

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
    if not Config.DISCORD_BOT_TOKEN:
        logger.critical("❌ Không tìm thấy DISCORD_BOT_TOKEN trong file .env!")
        return

    bot = CoreBot()
    bot.run(Config.DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
