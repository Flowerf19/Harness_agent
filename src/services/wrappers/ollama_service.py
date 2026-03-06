import logging
import os

import aiohttp
from Arize_Phoenix_tool_kit import track_llm_call

from ...config.settings import Config
from .base_llm_service import BaseLLMService


class OllamaService(BaseLLMService):
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

    async def _get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    @track_llm_call(model_name=Config.OLLAMA_MODEL, prompt_arg="prompt")
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
                "temperature": Config.LLM_TEMPERATURE,
                "top_p": Config.LLM_TOP_P,
                "top_k": Config.LLM_TOP_K,
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

    async def close(self):
        if self.session:
            await self.session.close()
