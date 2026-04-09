import logging
import os
from typing import Dict, List, Optional, Union

import aiohttp
from langsmith import traceable

from ...config.settings import Config
from .base_llm_service import BaseLLMService
from .llm_response import LLMResponse


class LMStudioService(BaseLLMService):
    """
    LLM Service cho LM Studio (Local Model Server).
    Sử dụng OpenAI-compatible API.
    """

    def __init__(self):
        # 🔴 Bắt buộc gọi super() để load tính cách tĩnh từ file
        super().__init__()

        # LM Studio không cần API key thực, dùng dummy key
        self.api_key = os.getenv("LM_STUDIO_API_KEY", "dummy-key")
        self.api_url = os.getenv(
            "LM_STUDIO_API_URL", "http://localhost:1234/v1"
        )
        self.model = Config.LM_STUDIO_MODEL
        self.session = None
        self.logger = logging.getLogger("discord_bot.LMStudioService")

    async def _get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    @traceable(name="LMStudio_Generate", run_type="llm", tags=["lm_studio", "generation"])
    async def generate_response(
        self, messages: List[Dict[str, str]], system_prompt: Optional[str] = None, skip_tools_prompt: bool = False
    ) -> Union[str, LLMResponse]:
        """
        Generate response from LM Studio API (OpenAI-compatible).

        Args:
            messages: Mảng tin nhắn theo chuẩn [{"role": "user/assistant", "content": "..."}]
            system_prompt: Dữ liệu Tiềm thức từ Tầng 3 (Dynamic Core Memory).
            skip_tools_prompt: Nếu True, không inject TOOLS.md vào system prompt.

        Returns:
            LLMResponse object with content and token metadata.
            Falls back to string for backwards compatibility on errors.
        """
        session = await self._get_session()

        # 1. Trộn Tính cách tĩnh + Tiềm thức User (Tầng 3)
        final_system_prompt = self._build_final_system_prompt(system_prompt, skip_tools_prompt=skip_tools_prompt)

        # 2. Xếp mảng hội thoại chuẩn OpenAI
        # Nhét system_prompt lên đầu, sau đó đến toàn bộ lịch sử hội thoại (T1 + T2)
        api_messages = [{"role": "system", "content": final_system_prompt}] + messages

        # LM Studio sử dụng endpoint /chat/completions giống OpenAI
        full_url = f"{self.api_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": api_messages,
            "temperature": Config.LLM_TEMPERATURE,
            "max_tokens": Config.LLM_MAX_TOKENS,
            "top_p": Config.LLM_TOP_P,
        }

        try:
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
                    self.logger.error(f"LM Studio API error: {error_text}")
                    return "Error generating response."

                response_data = await response.json()

                # Extract token usage metadata from OpenAI-compatible response
                usage = response_data.get("usage", {})
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

                if "choices" in response_data and len(response_data["choices"]) > 0:
                    choice = response_data["choices"][0]
                    if "message" in choice and "content" in choice["message"]:
                        content = choice["message"]["content"]

                        # Log token usage for debugging
                        self.logger.info(
                            f"LM Studio API - Input tokens: {input_tokens}, "
                            f"Output tokens: {output_tokens}, Total: {total_tokens}"
                        )

                        return LLMResponse(
                            content=content,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            total_tokens=total_tokens,
                            model=response_data.get("model", self.model),
                            finish_reason=choice.get("finish_reason"),
                            raw_response=response_data,
                        )

                return "Error: Unexpected response format."

        except Exception as e:
            self.logger.error(f"Error communicating with LM Studio API: {e}")
            return "Error generating response."

    async def close(self):
        if self.session:
            await self.session.close()