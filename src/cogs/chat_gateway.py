import asyncio
import logging

import discord
from discord.ext import commands
from underthesea import sent_tokenize

from src.services.dependencies import AppContainer

logger = logging.getLogger(__name__)


class ChatGateway(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Bỏ qua tin nhắn của chính bot hoặc các bot khác
        if message.author.bot:
            return

        # Bỏ qua nếu user đang gõ lệnh hệ thống (Ví dụ: !clear, !addbotchannel)
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        # --- 1. KIỂM TRA QUYỀN PHẢN HỒI ---
        is_dm = isinstance(message.channel, discord.DMChannel)
        is_mentioned = self.bot.user in message.mentions

        # Lấy Cog AdminChannels để kiểm tra danh sách kênh
        is_allowed_channel = False
        if message.guild:  # Nếu không phải là tin nhắn riêng (DM)
            admin_cog = self.bot.get_cog("AdminChannels")
            if admin_cog:
                # Hàm này trả về True nếu kênh đã được set (hoặc nếu chưa set kênh nào)
                is_allowed_channel = admin_cog.is_bot_channel(
                    message.guild.id, message.channel.id
                )
            else:
                # Fallback: Nếu lỗi không load được Cog, mặc định cho phép
                is_allowed_channel = True

        # CHỐT HẠ: Phản hồi nếu (Là tin nhắn riêng) HOẶC (Được Tag) HOẶC (Đang ở trong kênh đã Set)
        if not (is_dm or is_mentioned or is_allowed_channel):
            return

        # --- 2. DỌN DẸP TEXT ---
        content = message.content
        if is_mentioned:
            # Xóa cái tag <@ID_Của_Bot> ra khỏi chuỗi để LLM không bị đọc vấp
            content = content.replace(f"<@{self.bot.user.id}>", "")

        content = content.strip()

        # Kiểm tra lại lần cuối xem sau khi xóa Tag, tin nhắn có bị rỗng không
        if not content:
            return

        # --- 3. ĐIỀU PHỐI LOGIC CHAT ---
        coordinator = AppContainer.get_instance().chat_coordinator
        if not coordinator:
            logger.error("❌ ChatGateway: ChatCoordinator chưa được khởi tạo!")
            return

        # Bật hiệu ứng "Bot đang gõ..."
        async with message.channel.typing():
            try:
                # Ném đoạn hội thoại vào hệ thống lõi
                bot_response = await coordinator.process_message(
                    user_id=str(message.author.id), content=content
                )

                # Trả lời User (Tách theo \n và giới hạn 2000 ký tự)
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
        Xử lý tin nhắn trả về:
        1. Tách các tin nhắn theo chuỗi "\\n" hoặc ký tự xuống dòng "\\n" do LLM sinh ra.
        2. Gửi từng tin nhắn một, chia nhỏ nếu tin nhắn quá 2000 ký tự.
        """
        if not response_text:
            return

        # --- BƯỚC 1: XỬ LÝ LOGIC TÁCH DÒNG \n CỦA LLM ---
        # LLM đôi khi sinh ra chữ "\n" thô, đôi khi sinh ra ký tự xuống dòng thực sự '\n'
        # Ta cần replace chữ "\n" (2 ký tự) thành '\n' (1 ký tự xuống dòng) trước
        clean_text = response_text.replace("\\n", "\n")

        # Tách tin nhắn thành mảng các đoạn chat nhỏ
        # Loại bỏ các chuỗi rỗng sau khi tách
        messages_to_send = [
            msg.strip() for msg in clean_text.split("\n") if msg.strip()
        ]

        # --- BƯỚC 2: GỬI TỪNG ĐOẠN TIN NHẮN ---
        for i, msg in enumerate(messages_to_send):
            # Nếu tin nhắn ngắn gọn, Gửi thẳng vào kênh
            if len(msg) <= 2000:
                await original_message.channel.send(msg)
            else:
                # Nếu 1 đoạn msg (sau khi đã tách \n) vẫn lố 2000 ký tự -> Dùng chunking lai
                chunks = self._chunk_text(msg, limit=1900)
                for chunk in chunks:
                    await original_message.channel.send(chunk)

            # Thêm delay giả lập người dùng gõ tin nhắn tiếp theo và chống Spam (Rate Limit)
            # Không delay nếu đây là tin nhắn cuối cùng
            if i < len(messages_to_send) - 1:
                async with original_message.channel.typing():
                    # Delay 1.5 giây giữa các tin nhắn rời rạc
                    await asyncio.sleep(1.5)

    def _chunk_text(self, text: str, limit: int = 1900) -> list:
        """
        Cắt chuỗi thông minh lai (Hybrid):
        Đã được refactor lại cho an toàn và tránh bug nối chữ lố 2000 ký tự.
        """
        lines = text.split("\n")
        chunks = []
        current_chunk = ""

        for line in lines:
            if len(current_chunk) + len(line) + 1 <= limit:
                current_chunk += line + "\n"
                continue

            if current_chunk.strip():
                chunks.append(current_chunk.strip())
                current_chunk = ""

            if len(line) <= limit:
                current_chunk = line + "\n"
            else:
                sentences = sent_tokenize(line)
                for sentence in sentences:
                    if len(sentence) > limit:
                        if current_chunk.strip():
                            chunks.append(current_chunk.strip())
                            current_chunk = ""
                        for i in range(0, len(sentence), limit):
                            chunks.append(sentence[i : i + limit])
                    elif len(current_chunk) + len(sentence) + 1 > limit:
                        chunks.append(current_chunk.strip())
                        current_chunk = sentence + " "
                    else:
                        current_chunk += sentence + " "

                current_chunk += "\n"

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks


# Yêu cầu bắt buộc của file Cog trong Discord.py
async def setup(bot):
    await bot.add_cog(ChatGateway(bot))
