import logging
import os
from typing import Dict, List, Optional

import aiohttp
from langsmith import traceable

# Chú ý: Đổi đường dẫn import tùy theo kiến trúc thư mục mới của bạn
from ...config.settings import Config
from .base_llm_service import BaseLLMService


class QwenService(BaseLLMService):
    def __init__(self):
        # 🔴 Bắt buộc gọi super() để load tính cách tĩnh từ file
        super().__init__()

        self.api_key = os.getenv("QWEN_API_KEY")
        self.api_url = os.getenv(
            "QWEN_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.model = Config.QWEN_MODEL
        self.session = None
        self.logger = logging.getLogger("discord_bot.QwenService")

    async def _get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    # Đổi prompt_arg thành "messages" cho hợp với tham số mới
    @traceable(name="Qwen_Generate", run_type="llm", tags=["qwen", "generation"])
    async def generate_response(
        self, messages: List[Dict[str, str]], system_prompt: Optional[str] = None
    ) -> str:
        if not self.api_key:
            self.logger.error("Qwen API key not found")
            return "Error: Qwen API key not configured."

        session = await self._get_session()

        # 1. Trộn Tính cách tĩnh + Tiềm thức User (Tầng 3)
        final_system_prompt = self._build_final_system_prompt(system_prompt)

        # 2. Xếp mảng hội thoại chuẩn OpenAI
        # Nhét system_prompt lên đầu, sau đó đến toàn bộ lịch sử hội thoại (T1 + T2)
        api_messages = [{"role": "system", "content": final_system_prompt}] + messages

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
                    self.logger.error(f"Qwen API error: {error_text}")
                    return "Error generating response."

                response_data = await response.json()

                if "choices" in response_data and len(response_data["choices"]) > 0:
                    choice = response_data["choices"][0]
                    if "message" in choice and "content" in choice["message"]:
                        return choice["message"]["content"]

                return "Error: Unexpected response format."

        except Exception as e:
            self.logger.error(f"Error communicating with Qwen API: {e}")
            return "Error generating response."

    async def close(self):
        if self.session:
            await self.session.close()
