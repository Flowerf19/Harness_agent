import logging
import os

import aiohttp

from ...config.settings import Config
from .base_llm_service import BaseLLMService


class GeminiService(BaseLLMService):
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

        # Build system prompt and user message separately
        system_prompt = self._build_system_prompt()
        user_message = self._build_user_message(prompt, user_id, conversation_context)

        # Construct the full API URL for generateContent
        full_url = f"{self.api_url}/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_message}]}],
            "generationConfig": {
                "temperature": Config.LLM_TEMPERATURE,
                "maxOutputTokens": Config.LLM_MAX_TOKENS,
                "topP": Config.LLM_TOP_P,
                "topK": Config.LLM_TOP_K,
            },
        }

        try:
            self.logger.debug(
                f"Sending request to Gemini API with system prompt: {system_prompt[:100]}... and user message: {user_message[:100]}..."
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

    async def close(self):
        if self.session:
            await self.session.close()
