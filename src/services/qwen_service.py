import logging
import os

import aiohttp

from config.settings import Config


class QwenService:
    def __init__(self):
        self.api_key = os.getenv("QWEN_API_KEY")
        self.api_url = os.getenv(
            "QWEN_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.model = os.getenv("QWEN_MODEL", "qwen-max")
        self.session = None
        self.logger = logging.getLogger("discord_bot.QwenService")

        # Load prompts
        self.personality_prompt = self._load_prompt("personality.txt")
        self.conversation_prompt = self._load_prompt("conversation_prompt.txt")

    def _load_prompt(self, filename):
        """Load prompt from file"""
        try:
            prompts_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "data", "prompts"
            )
            filepath = os.path.join(prompts_dir, filename)
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    self.logger.info(f"✅ Loaded prompt: {filename}")
                    return content
            else:
                self.logger.warning(f"⚠️ Prompt file not found: {filepath}")
                return ""
        except Exception as e:
            self.logger.error(f"❌ Error loading prompt {filename}: {e}")
            return ""

    async def _get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def generate_response(
        self, prompt: str, user_id: str = None, conversation_context: str = ""
    ) -> str:
        if not self.api_key:
            self.logger.error("Qwen API key not found")
            return "Error: Qwen API key not configured."

        session = await self._get_session()

        # Build system prompt and user message separately
        system_prompt = self._build_system_prompt()
        user_message = self._build_user_message(prompt, user_id, conversation_context)

        # Construct the full API URL
        full_url = f"{self.api_url}/chat/completions"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": Config.LLM_TEMPERATURE,
            "max_tokens": Config.LLM_MAX_TOKENS,
            "top_p": Config.LLM_TOP_P,
        }

        try:
            self.logger.debug(
                f"Sending request to Qwen API with system prompt: {system_prompt[:100]}... and user message: {user_message[:100]}..."
            )
            async with session.post(
                full_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"Qwen API error: {error_text}")
                    return "Error generating response."

                response_data = await response.json()

                # Extract the text from the response
                if "choices" in response_data and len(response_data["choices"]) > 0:
                    choice = response_data["choices"][0]
                    if "message" in choice and "content" in choice["message"]:
                        return choice["message"]["content"]

                self.logger.error(f"Unexpected response format: {response_data}")
                return "Error: Unexpected response format."

        except Exception as e:
            self.logger.error(f"Error communicating with Qwen API: {e}")
            return "Error generating response."

    def _build_system_prompt(self) -> str:
        """Build system prompt from personality and guidelines"""
        parts = []

        if self.personality_prompt:
            parts.append(f"=== NHÂN CÁCH ===\n{self.personality_prompt}")

        if self.conversation_prompt:
            parts.append(f"=== HƯỚNG DẪN HỘI THOẠI ===\n{self.conversation_prompt}")

        return "\n\n".join(parts)

    def _build_user_message(
        self, user_message: str, user_id: str = None, conversation_context: str = ""
    ) -> str:
        """Build user message with context"""
        prompt_parts = []

        # Add conversation context if available
        if conversation_context:
            prompt_parts.append(
                f"=== LỊCH SỬ HỘI THOẠI GẦN ĐÂY ===\n{conversation_context}"
            )

        # Add user message
        prompt_parts.append(f"=== TIN NHẮN NGƯỜI DÙNG ===\n{user_message}")

        # Add instructions
        prompt_parts.append(
            "=== NHIỆM VỤ ===\nHãy trả lời tin nhắn người dùng theo đúng nhân cách và hướng dẫn trên. Nếu có lịch sử hội thoại, hãy tham khảo để trả lời phù hợp với ngữ cảnh."
        )

        user_message_content = "\n\n".join(prompt_parts)
        self.logger.debug(
            f"Built user message with context: {len(user_message_content)} chars"
        )
        return user_message_content

    async def close(self):
        if self.session:
            await self.session.close()

    def split_response_into_parts(self, response: str) -> list:
        """Split response into multiple natural parts for sequential sending"""
        import re

        # Remove extra whitespace
        response = response.strip()

        if not response:
            return []

        # Simple approach: split by newlines first to preserve line breaks
        lines = response.split("\n")

        # Then for very long lines, optionally split by sentences
        result = []
        for line in lines:
            if len(line) <= 2000:  # Discord message limit
                if line.strip():  # Only add non-empty lines
                    result.append(line)
            else:
                # For very long lines, split by natural breaks (sentences, questions, exclamations)
                parts = re.split(r"([.!?]+\s*)", line)

                # Combine sentence with its punctuation
                combined_parts = []
                for i in range(0, len(parts), 2):
                    if i + 1 < len(parts):
                        part = (parts[i] + parts[i + 1]).strip()
                    else:
                        part = parts[i].strip()

                    if part:
                        combined_parts.append(part)

                # Add the split parts
                result.extend(combined_parts)

        return result
