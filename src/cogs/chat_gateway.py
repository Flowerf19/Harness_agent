import logging

import discord
from discord.ext import commands

from src.services.dependencies import AppContainer

logger = logging.getLogger(__name__)


class ChatGateway(commands.Cog):
    """
    Cửa khẩu giao tiếp duy nhất giữa Discord và hệ thống AI.
    Chịu trách nhiệm Tiền xử lý (Lọc rác) và Hậu xử lý (Cắt chuỗi 2000 ký tự).
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # --- 1. BỘ LỌC RÁC (TIỀN XỬ LÝ) ---

        # Bỏ qua tin nhắn của chính bot hoặc các bot khác
        if message.author.bot:
            return

        # Bỏ qua tin nhắn rỗng hoặc chỉ có ảnh/file mà không có chữ
        content = message.content.strip()
        if not content:
            return

        # Bỏ qua nếu user đang gõ lệnh hệ thống (Ví dụ: !clear, !help)
        # Để sân khấu cho file user_commands.py xử lý
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        # (Tùy chọn) Quy tắc phản hồi: Chỉ rep khi được Tag hoặc chat trong DM (Tin nhắn riêng)
        # Xóa khối IF này nếu bạn muốn bot hóng hớt và rep MỌI tin nhắn trong server.
        is_dm = isinstance(message.channel, discord.DMChannel)
        is_mentioned = self.bot.user in message.mentions

        if not (is_dm or is_mentioned):
            return

        # Dọn dẹp Text: Xóa cái tag <@ID_Của_Bot> ra khỏi chuỗi để LLM không bị đọc vấp
        if is_mentioned:
            content = content.replace(f"<@{self.bot.user.id}>", "").strip()

        # --- 2. ĐIỀU PHỐI LOGIC (GỌI NHẠC TRƯỞNG) ---

        # Lấy instance của Nhạc trưởng từ Trạm Điện (AppContainer)
        coordinator = AppContainer.get_instance().chat_coordinator
        if not coordinator:
            logger.error("❌ ChatGateway: ChatCoordinator chưa được khởi tạo!")
            return

        # Bật hiệu ứng "Bot đang gõ..." để user biết bot không bị sập
        async with message.channel.typing():
            try:
                # Ném đoạn hội thoại vào hệ thống lõi
                bot_response = await coordinator.process_message(
                    user_id=str(message.author.id), content=content
                )

                # --- 3. TRẢ LỜI USER (HẬU XỬ LÝ) ---
                await self._send_response(message, bot_response)

            except Exception as e:
                logger.error(f"❌ Lỗi tại Chat Gateway: {e}")
                await message.reply(
                    "Hệ thống não bộ của tớ đang bị quá tải xíu, cậu thử lại sau vài giây nhé!"
                )

    async def _send_response(
        self, original_message: discord.Message, response_text: str
    ):
        """
        Thuật toán chia nhỏ tin nhắn để lách luật giới hạn 2000 ký tự của Discord.
        """
        if not response_text:
            return

        # Nếu tin nhắn ngắn gọn, Reply thẳng luôn
        if len(response_text) <= 2000:
            await original_message.reply(response_text)
            return

        # Nếu quá dài, dùng thuật toán chặt khúc thân thiện (không chặt đứt ngang chữ)
        chunks = self._chunk_text(response_text, limit=1900)

        # Đoạn đầu tiên thì Reply
        await original_message.reply(chunks[0])

        # Các đoạn sau thì gửi nối tiếp vào channel
        for chunk in chunks[1:]:
            await original_message.channel.send(chunk)

    def _chunk_text(self, text: str, limit: int = 1900) -> list:
        """Cắt chuỗi thông minh theo từng dòng (newline) để không vỡ layout."""
        lines = text.split("\n")
        chunks = []
        current_chunk = ""

        for line in lines:
            # Nếu thêm dòng này vào mà vượt quá limit thì chốt sổ chunk hiện tại
            if len(current_chunk) + len(line) + 1 > limit:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = line + "\n"
            else:
                current_chunk += line + "\n"

        # Nhét nốt phần dư cuối cùng
        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks


# Yêu cầu bắt buộc của file Cog trong Discord.py
async def setup(bot):
    await bot.add_cog(ChatGateway(bot))
