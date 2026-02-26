import logging
import os

import aiohttp


class GeminiService:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.api_url = os.getenv(
            "GEMINI_API_URL", "https://generativelanguage.googleapis.com/v1beta/models"
        )
        self.model = os.getenv("LLM_MODEL", "gemini-1.5-flash")
        self.session = None
        self.logger = logging.getLogger("discord_bot.GeminiService")

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
            self.logger.error("Gemini API key not found")
            return "Error: API key not configured."

        session = await self._get_session()

        # Build full prompt with personality, conversation guidelines, and context
        full_prompt = self._build_full_prompt(prompt, user_id, conversation_context)

        # Construct the full API URL for generateContent
        full_url = f"{self.api_url}/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 1000,
                "topP": 0.95,
                "topK": 64,
            },
        }

        try:
            self.logger.debug(
                f"Sending request to Gemini API with full prompt: {full_prompt[:100]}..."
            )
            async with session.post(
                full_url, json=payload, headers={"Content-Type": "application/json"}
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"Gemini API error: {error_text}")
                    return "Error generating response."

                response_data = await response.json()

                # Extract the text from the response
                if (
                    "candidates" in response_data
                    and len(response_data["candidates"]) > 0
                ):
                    candidate = response_data["candidates"][0]
                    if "content" in candidate and "parts" in candidate["content"]:
                        parts = candidate["content"]["parts"]
                        if len(parts) > 0 and "text" in parts[0]:
                            return parts[0]["text"]

                self.logger.error(f"Unexpected response format: {response_data}")
                return "Error: Unexpected response format."

        except Exception as e:
            self.logger.error(f"Error communicating with Gemini API: {e}")
            return "Error generating response."

    def _build_full_prompt(
        self, user_message: str, user_id: str = None, conversation_context: str = ""
    ) -> str:
        """Build complete prompt with personality, conversation guidelines, and context"""
        prompt_parts = []

        # Add personality
        if self.personality_prompt:
            prompt_parts.append(f"=== NHÂN CÁCH ===\n{self.personality_prompt}")

        # Add conversation guidelines
        if self.conversation_prompt:
            prompt_parts.append(
                f"=== HƯỚNG DẪN HỘI THOẠI ===\n{self.conversation_prompt}"
            )

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

        full_prompt = "\n\n".join(prompt_parts)
        self.logger.debug(f"Built full prompt with context: {len(full_prompt)} chars")
        return full_prompt

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
