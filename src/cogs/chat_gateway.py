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

                # Trả lời User (Có cắt chuỗi 2000 ký tự)
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
        Gửi tin nhắn thông thường (Không Reply) và tự động chia nhỏ nếu quá 2000 ký tự.
        """
        if not response_text:
            return

        # Nếu tin nhắn ngắn gọn, Gửi thẳng vào kênh (Dùng .channel.send thay vì .reply)
        if len(response_text) <= 2000:
            await original_message.channel.send(response_text)
            return

        # Nếu quá dài, dùng thuật toán chặt khúc lai (Hybrid)
        chunks = self._chunk_text(response_text, limit=1900)

        # Gửi nối tiếp toàn bộ các đoạn văn bản vào channel
        for chunk in chunks:
            await original_message.channel.send(chunk)

    def _chunk_text(self, text: str, limit: int = 1900) -> list:
        """
        Cắt chuỗi thông minh lai (Hybrid):
        1. Ưu tiên gộp theo dòng (\n) để giữ nguyên layout Markdown/Code.
        2. Nếu một dòng quá dài (> limit), dùng Underthesea cắt chuẩn theo câu Tiếng Việt.
        """
        lines = text.split("\n")
        chunks = []
        current_chunk = ""

        for line in lines:
            # TRƯỜNG HỢP 1: Dòng văn bản siêu dài (Không có \n mà dài hơn 1900 chữ)
            if len(line) > limit:
                # Chốt sổ chunk hiện tại trước
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""

                # Dùng Underthesea cắt dòng dài này thành các câu trọn vẹn
                sentences = sent_tokenize(line)

                for sentence in sentences:
                    # Rất hiếm: 1 câu đơn dài hơn 1900 ký tự -> Chặt bạo lực theo số lượng
                    if len(sentence) > limit:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                            current_chunk = ""
                        for i in range(0, len(sentence), limit):
                            chunks.append(sentence[i : i + limit].strip())

                    # Nếu nhét câu này vào bị lố limit -> Chốt sổ
                    elif len(current_chunk) + len(sentence) + 1 > limit:
                        chunks.append(current_chunk.strip())
                        current_chunk = sentence + " "

                    # Ngược lại thì gộp câu vào chunk hiện tại
                    else:
                        current_chunk += sentence + " "

                current_chunk += "\n"  # Phục hồi lại dấu xuống dòng của paragraph gốc

            # TRƯỜNG HỢP 2: Dòng bình thường (Duy trì Layout Markdown)
            else:
                if len(current_chunk) + len(line) + 1 > limit:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = line + "\n"
                else:
                    current_chunk += line + "\n"

        # Nhét nốt phần dư cuối cùng
        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks


# Yêu cầu bắt buộc của file Cog trong Discord.py
async def setup(bot):
    await bot.add_cog(ChatGateway(bot))
