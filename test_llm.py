"""
Test LLM Service - Bypass Discord
File này test trực tiếp QwenService/GeminiService mà không cần import toàn bộ codebase.
"""

import asyncio
import logging
import os
import sys
from typing import Dict, List, Optional

import aiohttp
from dotenv import load_dotenv


# Mock Arize_Phoenix_tool_kit trước khi import
def mock_decorator(*args, **kwargs):
    def decorator(func):
        return func

    return decorator


mock_arize = type(sys)("Arize_Phoenix_tool_kit")
mock_arize.track_llm_call = mock_decorator
mock_arize.track_general_step = mock_decorator
sys.modules["Arize_Phoenix_tool_kit"] = mock_arize

# Mock sentence_transformers
mock_st = type(sys)("sentence_transformers")
mock_st.SentenceTransformer = object
sys.modules["sentence_transformers"] = mock_st

# Load env
load_dotenv()

# Lấy config values trực tiếp từ env
QWEN_API_KEY = os.getenv("QWEN_API_KEY")
QWEN_API_URL = os.getenv(
    "QWEN_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-plus")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2048"))
LLM_TOP_P = float(os.getenv("LLM_TOP_P", "0.9"))


class SimpleQwenService:
    """QwenService đơn giản để test, không phụ thuộc vào BaseLLMService"""

    def __init__(self):
        self.api_key = QWEN_API_KEY
        self.api_url = QWEN_API_URL
        self.model = QWEN_MODEL
        self.session = None
        self.logger = logging.getLogger("QwenService")
        logging.basicConfig(level=logging.INFO)

    async def _get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def generate_response(
        self, messages: List[Dict[str, str]], system_prompt: Optional[str] = None
    ) -> str:
        if not self.api_key:
            self.logger.error("Qwen API key not found")
            return "Error: Qwen API key not configured."

        session = await self._get_session()

        # Build system prompt
        final_system_prompt = system_prompt or "Bạn là trợ lý AI hữu ích."
        api_messages = [{"role": "system", "content": final_system_prompt}] + messages

        full_url = f"{self.api_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": api_messages,
            "temperature": LLM_TEMPERATURE,
            "max_tokens": LLM_MAX_TOKENS,
            "top_p": LLM_TOP_P,
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
                    return f"Error: API returned {response.status}"

                response_data = await response.json()

                if "choices" in response_data and len(response_data["choices"]) > 0:
                    choice = response_data["choices"][0]
                    if "message" in choice and "content" in choice["message"]:
                        return choice["message"]["content"]

                return "Error: Unexpected response format."

        except Exception as e:
            self.logger.error(f"Error communicating with Qwen API: {e}")
            return f"Error: {str(e)}"

    async def close(self):
        if self.session:
            await self.session.close()


async def main():
    print("=" * 50)
    print("TEST LLM SERVICE - QWEN")
    print("=" * 50)

    llm = SimpleQwenService()

    messages = [{"role": "user", "content": "Xin chào, 1 + 1 bằng mấy?"}]

    print(f"\n📝 Câu hỏi: {messages[0]['content']}")
    print("\n⏳ Đang gọi AI...")

    response = await llm.generate_response(
        messages, system_prompt="Bạn là trợ lý toán học. Hãy trả lời ngắn gọn."
    )

    print(f"\n🤖 AI Trả lời: {response}")

    await llm.close()
    print("\n✅ Đã đóng connection.")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
