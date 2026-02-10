import os
import aiohttp
import logging
from config.settings import Config


class OllamaService:
    def __init__(self):
        self.api_url = Config.OLLAMA_API_URL
        self.model = Config.OLLAMA_MODEL
        self.session = None
        self.logger = logging.getLogger("discord_bot.OllamaService")

        # Load prompts
        self.personality_prompt = self._load_prompt("personality.txt")
        self.conversation_prompt = self._load_prompt("conversation_prompt.txt")

        self.logger.info(
            f"🦙 OllamaService initialized with model: {self.model} at {self.api_url}"
        )

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
        session = await self._get_session()

        # Build system prompt with personality and conversation guidelines
        system_prompt = self._build_system_prompt()

        # Combine context and current prompt
        full_context = ""
        if conversation_context:
            full_context = f"Lịch sử hội thoại:\n{conversation_context}\n\n"

        full_prompt = f"{full_context}Tin nhắn mới:\n{prompt}"

        # API endpoint for chat
        url = f"{self.api_url}/api/chat"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "top_k": 40,
            },
        }

        try:
            self.logger.debug(f"Sending request to Ollama ({self.model})...")
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"Ollama API error: {error_text}")
                    return "Error generating response from Ollama."

                response_data = await response.json()

                if "message" in response_data and "content" in response_data["message"]:
                    return response_data["message"]["content"]

                self.logger.error(f"Unexpected response format: {response_data}")
                return "Error: Unexpected response format."

        except Exception as e:
            self.logger.error(f"Error communicating with Ollama API: {e}")
            return "Error generating response."

    def _build_system_prompt(self) -> str:
        """Build system prompt from personality and guidelines"""
        parts = []

        if self.personality_prompt:
            parts.append(f"=== NHÂN CÁCH ===\n{self.personality_prompt}")

        if self.conversation_prompt:
            parts.append(f"=== HƯỚNG DẪN ===\n{self.conversation_prompt}")

        return "\n\n".join(parts)

    async def close(self):
        if self.session:
            await self.session.close()

    def split_response_into_parts(self, response: str) -> list:
        # Reuse logic from GeminiService or a shared utility
        # Ideally this should be a mixin or utility, but for now I'll duplicate suitable simple logic or refer to GeminiService's if I make it static.
        # For simplicity and speed, I will copy the logic since it's formatting related.
        # Actually, looking at GeminiService, it imports 're'.
        return self._split_response_naturally(response)

    def _split_response_naturally(self, response: str) -> list:
        """
        Split response into natural parts: mỗi câu là một phần, xuống dòng đúng dấu câu.
        """
        import re

        response = response.strip()
        if not response:
            return []

        sentence_end_re = re.compile(r"([^.!?…~]+[.!?…~]+[\s\n]*)", re.UNICODE)
        parts = sentence_end_re.findall(response)

        consumed = "".join(parts)
        if len(consumed) < len(response):
            parts.append(response[len(consumed) :].strip())

        return [p.strip() for p in parts if p.strip()]
