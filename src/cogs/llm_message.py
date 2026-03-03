import logging
import os

import discord  # type: ignore
from discord.ext import commands  # type: ignore

from config.settings import Config
from services.anti_spam_service import AntiSpamService
from services.conversation_manager import ConversationManager
from services.gemini_service import GeminiService
from services.lm_studio_service import LMStudioService
from services.message_processor import MessageProcessor
from services.ollama_service import OllamaService
from services.qwen_service import QwenService
from services.relationship_service import RelationshipService
from services.summary_service import SummaryService

logger = logging.getLogger("discord_bot.LLMMessageCog")


class LLMMessageCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Initialize LLM Service based on config
        if Config.LLM_PROVIDER == "ollama":
            self.llm_service = OllamaService()
            logger.info(f"🤖 initialized with Ollama ({Config.OLLAMA_MODEL})")
        elif Config.LLM_PROVIDER == "lm_studio":
            self.llm_service = LMStudioService()
            logger.info("🤖 initialized with LM Studio")
        elif Config.LLM_PROVIDER == "qwen":
            self.llm_service = QwenService()
            logger.info("🤖 initialized with Qwen")
        else:
            self.llm_service = GeminiService()
            logger.info("🤖 initialized with Gemini")

        # Initialize SummaryService
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        prompts_dir = os.path.join(base_dir, "data", "prompts")
        config_dir = os.path.join(base_dir, "data", "config")
        data_dir = os.path.join(base_dir, "data")
        self.summary_service = SummaryService(self.llm_service, prompts_dir, config_dir)

        # Initialize RelationshipService
        self.relationship_service = RelationshipService(self.llm_service, data_dir)

        # Initialize modular services
        self.message_processor = MessageProcessor()
        self.anti_spam = AntiSpamService()
        self.conversation_manager = ConversationManager()

        logger.info(
            "🤖 LLMMessageCog initialized with modular services including RelationshipService"
        )

    @commands.Cog.listener()
    async def on_message(self, message):
        """Main message handler - only one listener!"""
        # Ignore messages from the bot itself
        if message.author == self.bot.user:
            return

        # Check if should process (anti-duplicate)
        if not await self.message_processor.should_process_message(message):
            return

        # Process with lock protection
        await self.message_processor.process_with_lock(message, self._handle_message)

    async def _handle_message(self, message):
        """Internal message handling logic"""
        # Ignore commands
        if message.content.startswith("!") or message.content.startswith("/"):
            return

        # Check if should respond
        if not self._should_respond_to_message(message):
            return

        # Clean content
        content = self._clean_message_content(message)
        if not content.strip():
            return

        user_id = str(message.author.id)

        # Process relationship data (always, regardless of response)
        # Semantic understanding like real name extraction is handled by LLM
        await self._process_relationship_data(message, content, user_id)

        # Anti-spam check
        is_spam, cooldown_remaining = self.anti_spam.check_spam(user_id)
        if is_spam:
            spam_msg = f"🚫 **Anti-Spam**: Bạn đang gửi tin nhắn quá nhanh! Vui lòng đợi {cooldown_remaining}s."
            await message.reply(spam_msg)
            return

        # Conversation lock check
        if self.conversation_manager.is_conversation_locked(user_id):
            duration = self.conversation_manager.get_lock_duration()
            busy_msg = (
                f"⏳ Tôi đang trả lời người khác ({duration}s). Xin đợi một chút nhé!"
            )
            await message.reply(busy_msg)
            self.conversation_manager.add_to_pending_queue(message, content)
            return

        # Process AI response
        await self._process_ai_response(message, content, user_id)

    async def _process_ai_response(self, message, content: str, user_id: str):
        """Process AI response"""
        try:
            # Lock conversation
            self.conversation_manager.set_conversation_lock(user_id)

            # Build context
            context = self.conversation_manager.get_conversation_context(user_id)
            user_summary = self.summary_service.get_user_summary(user_id)
            mentioned_users_info = self.get_mentioned_users_info(content, message)

            enhanced_context = self._build_enhanced_context(
                user_id, user_summary, mentioned_users_info, context
            )

            # Generate and send response
            async with message.channel.typing():
                response = await self.llm_service.generate_response(
                    content, user_id, enhanced_context
                )
                if response and len(response.strip()) > 0:
                    await self.send_response_in_parts(message, response, user_id)

                    # Save to history (both in-memory and persistent)
                    self.conversation_manager.add_to_history(user_id, content, response)
                    self.conversation_manager.save_to_persistent_history(
                        user_id, content, response
                    )

                    # Update summary if needed
                    if self.summary_service.should_update_summary(
                        user_id, content, user_summary
                    ):
                        try:
                            await self.summary_service.update_summary_smart(user_id)
                        except Exception as e:
                            logger.error(
                                f"❌ Error updating summary for {user_id}: {e}"
                            )
                else:
                    await message.reply(
                        "Xin lỗi, tôi không thể tạo phản hồi cho tin nhắn này."
                    )

        except Exception as e:
            logger.error(f"❌ Error processing AI response: {e}")
            await message.reply("Xin lỗi, đã có lỗi xảy ra khi tạo phản hồi.")

        finally:
            # Always release lock
            self.conversation_manager.release_conversation_lock()

    def _should_respond_to_message(self, message) -> bool:
        """Determine if bot should respond to message"""
        # Always respond in DMs
        if isinstance(message.channel, discord.DMChannel):
            return True

        # In guild channels
        if hasattr(message, "guild") and message.guild:
            is_mentioned = self.bot.user.mentioned_in(message)

            # Check admin cog for channel configuration
            admin_cog = self.bot.get_cog("AdminChannels")
            is_bot_channel = (
                admin_cog.is_bot_channel(message.guild.id, message.channel.id)
                if admin_cog
                else True
            )

            # Respond if: in bot channel OR mentioned
            return is_bot_channel or is_mentioned

        return False

    def _clean_message_content(self, message) -> str:
        """Remove bot mentions from message content"""
        content = message.content
        if self.bot.user.mentioned_in(message):
            content = content.replace(f"<@{self.bot.user.id}>", "").strip()
            content = content.replace(f"<@!{self.bot.user.id}>", "").strip()
        return content

    def _build_enhanced_context(
        self, user_id: str, user_summary: str, mentioned_users_info: str, context: str
    ) -> str:
        """Build enhanced context for AI"""
        enhanced_context = ""
        if user_summary:
            enhanced_context += f"=== NGƯỜI ĐANG NÓI CHUYỆN (USER ID: {user_id}) ===\n{user_summary}\n\n"

        # Add relationship information
        try:
            user_display_name = self.relationship_service.get_user_display_name(user_id)
            user_relationships = self.relationship_service.get_user_relationships(
                user_id
            )
            interaction_stats = self.relationship_service.get_interaction_stats(user_id)

            if user_relationships or interaction_stats.get("total_interactions", 0) > 0:
                enhanced_context += (
                    f"=== MỐI QUAN HỆ VÀ TƯƠNG TÁC CỦA {user_display_name} ===\n"
                )

                if user_relationships:
                    enhanced_context += "Mối quan hệ:\n"
                    for rel in user_relationships[:5]:  # Top 5 relationships
                        enhanced_context += (
                            f"- {rel['other_person']}: {rel['relationship_type']}\n"
                        )

                if interaction_stats.get("top_contacts"):
                    enhanced_context += "\nNgười liên lạc thường xuyên:\n"
                    for contact in interaction_stats["top_contacts"][
                        :3
                    ]:  # Top 3 contacts
                        enhanced_context += f"- {contact['name']}: {contact['interaction_count']} lần tương tác\n"

                enhanced_context += "\n"
        except Exception as e:
            logger.error(f"Error getting relationship context: {e}")

        if mentioned_users_info:
            enhanced_context += (
                f"=== THÔNG TIN VỀ NGƯỜI ĐƯỢC NHẮC ĐẾN ===\n{mentioned_users_info}\n\n"
            )
        if context:
            enhanced_context += (
                f"=== LỊCH SỬ HỘI THOẠI CỦA NGƯỜI HIỆN TẠI ===\n{context}\n\n"
            )

        enhanced_context += f"=== QUAN TRỌNG ===\nBạn đang nói chuyện với USER ID {user_id}. Đừng nhầm lẫn với những người khác được nhắc đến trong tin nhắn."
        return enhanced_context

    def get_mentioned_users_info(self, content: str, message=None) -> str:
        """Get information about mentioned users, prefer display name/nickname over ID"""
        import re

        user_mentions = re.findall(r"<@!?(\d+)>", content)
        if not user_mentions:
            return ""
        mentioned_info_parts = []
        # Build a mapping from user_id to display name if message.mentions is available
        mention_name_map = {}
        if message and hasattr(message, "mentions"):
            for m in message.mentions:
                # Prefer: global_name > display_name > name > id
                display = (
                    getattr(m, "global_name", None)
                    or getattr(m, "display_name", None)
                    or getattr(m, "name", None)
                    or str(m.id)
                )
                mention_name_map[str(m.id)] = display
        for mentioned_user_id in user_mentions:
            # Try to get display name from message.mentions
            display_name = mention_name_map.get(mentioned_user_id)
            # If not found, try from relationship service
            if not display_name and hasattr(self, "relationship_service"):
                display_name = self.relationship_service.get_user_display_name(
                    mentioned_user_id
                )
            # Fallback to ID
            if not display_name:
                display_name = mentioned_user_id
            try:
                mentioned_user_summary = self.summary_service.get_user_summary(
                    mentioned_user_id
                )
                if mentioned_user_summary:
                    mentioned_info_parts.append(
                        f"{display_name} (ID: {mentioned_user_id}):\n{mentioned_user_summary}"
                    )
                else:
                    mentioned_info_parts.append(
                        f"{display_name} (ID: {mentioned_user_id}): Chưa có thông tin"
                    )
            except Exception as e:
                logger.error(
                    f"Error getting info for mentioned user {mentioned_user_id}: {e}"
                )
        return "\n\n".join(mentioned_info_parts) if mentioned_info_parts else ""

    async def send_response_in_parts(self, message, response: str, user_id: str):
        """Send response with realistic typing simulation"""
        import asyncio
        import random

        # Xoá các khoảng trắng và dấu xuống dòng thừa
        clean_response = response.strip()
        if not clean_response:
            return

        # Nếu không bật giả lập gõ chữ, gửi luôn 1 lần
        if not Config.ENABLE_TYPING_SIMULATION:
            await message.reply(clean_response)
            return

        # Giả lập gõ chữ và gửi 1 lần duy nhất thay vì tách dòng
        async with message.channel.typing():
            # Tính thời gian gõ chữ cho toàn bộ đoạn text
            typing_delay = self._calculate_typing_delay(clean_response)
            await asyncio.sleep(typing_delay)

            await message.reply(clean_response)

    def _split_response_naturally(self, response: str) -> list:
        """
        Split response into natural parts: mỗi câu là một phần.
        Hỗ trợ các dấu: . ! ? … ~ (và các dấu kết câu tiếng Việt phổ biến)
        Cải tiến: Giữ các emoji liền kề với văn bản không bị tách riêng lẻ
        """
        import re

        response = response.strip()
        if not response:
            return []

        # Tách theo dấu kết câu nhưng cố gắng giữ các emoji liền kề
        # Regex: tách theo dấu câu nhưng không tách nếu sau đó là emoji
        # Trước tiên tìm các vị trí có dấu câu kết thúc câu
        sentence_end_re = re.compile(r"([^.!?…~]+[.!?…~]+)(\s*)", re.UNICODE)
        matches = sentence_end_re.finditer(response)

        # Lấy các phần đã tách
        parts = []
        last_end = 0
        for match in matches:
            sentence = match.group(0)  # Toàn bộ câu bao gồm dấu câu và khoảng trắng
            start, end = match.span()

            # Kiểm tra nếu sau khoảng trắng có emoji hoặc ký tự đặc biệt
            remaining = response[end:]
            # Tìm các emoji shortcode (dạng :emoji:), teencode (dạng :3, :D, :v, :)), hoặc emoji unicode theo sau
            emoji_pattern = r"^(:[a-z0-9_+-]+:|:[3DPpSDd\)\(Oo]+|;\)|\^\^|<3|xD?|v\.v|>\.<|=\.\.=|\s*[^\w\s]{1,2}\s*|[^\x00-\x7F]{1,4})"
            emoji_match = re.match(emoji_pattern, remaining.lstrip())

            if emoji_match:
                # Nếu có emoji theo sau, thêm cả emoji vào phần hiện tại
                emoji_end = emoji_match.end()
                # Kết hợp câu với emoji theo sau
                combined_part = sentence + remaining[:emoji_end].strip()
                parts.append(combined_part)
                last_end = end + emoji_end
            else:
                # Không có emoji đặc biệt theo sau, chỉ thêm câu hiện tại
                parts.append(sentence)
                last_end = end

        # Nếu còn phần dư (không kết thúc bằng dấu câu), thêm vào cuối
        if last_end < len(response):
            remaining = response[last_end:].strip()
            if remaining:
                # Kiểm tra xem phần còn lại có bắt đầu bằng emoji không
                if parts:
                    # Nếu có phần cuối cùng, thêm phần còn lại vào đó
                    parts[-1] = (parts[-1] + " " + remaining).strip()
                else:
                    parts.append(remaining)

        # Loại bỏ phần rỗng và strip từng phần
        return [p.strip() for p in parts if p.strip()]

    def _calculate_typing_delay(self, text: str) -> float:
        """Calculate realistic typing delay based on text length and complexity"""
        import random

        # Convert WPM to characters per second (average 5 chars per word)
        chars_per_second = (Config.TYPING_SPEED_WPM * 5) / 60

        # Add some variation for realistic feel
        chars_per_second *= random.uniform(0.8, 1.2)

        # Adjust for text complexity
        complexity_factors = {
            "emoji": len([c for c in text if ord(c) > 127])
            * 0.2,  # Emoji/unicode slow down
            "punctuation": len([c for c in text if c in ".,!?;:"])
            * 0.1,  # Punctuation pause
            "spaces": text.count(" ") * 0.05,  # Word boundaries
            "thinking": 0.5
            if any(word in text.lower() for word in ["hmm", "ờm", "à", "ủa"])
            else 0,
        }

        # Calculate base delay
        text_length = len(text)
        base_delay = text_length / chars_per_second

        # Add complexity delays
        complexity_delay = sum(complexity_factors.values())

        # Add some randomness for natural feel
        random_factor = random.uniform(0.8, 1.3)

        # Final delay with reasonable bounds
        total_delay = (base_delay + complexity_delay) * random_factor

        # Ensure delay is within configured bounds
        return max(Config.MIN_TYPING_DELAY, min(Config.MAX_TYPING_DELAY, total_delay))

    async def _process_relationship_data(self, message, content: str, user_id: str):
        """Process relationship data from message"""
        try:
            # Get author info
            author_username = message.author.display_name or message.author.name

            # Extract mentioned users
            mentioned_user_ids = []
            for mention in message.mentions:
                mentioned_user_ids.append(str(mention.id))
                # Update mentioned user's name info too
                self.relationship_service.update_user_name(
                    str(mention.id),
                    mention.display_name or mention.name,
                    mention.display_name
                    if mention.display_name != mention.name
                    else None,
                    mention.global_name if hasattr(mention, "global_name") else None,
                )

            # Process the message through relationship service
            # Note: Real name extraction and other semantic understanding is handled by LLM
            await self.relationship_service.process_message(
                user_id,
                author_username,
                content,
                mentioned_user_ids,
                str(message.channel.id) if message.channel else None,
            )

            logger.debug(
                f"🔗 Processed relationship data for {author_username} (ID: {user_id})"
            )

        except Exception as e:
            logger.error(f"❌ Error processing relationship data: {e}")


async def setup(bot):
    await bot.add_cog(LLMMessageCog(bot))
