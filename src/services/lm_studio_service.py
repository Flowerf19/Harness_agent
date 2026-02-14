import json
import logging
import os

import aiohttp

from config.settings import Config


class LMStudioService:
    def __init__(self):
        self.api_url = os.getenv("LM_STUDIO_API_URL", "http://localhost:1234")
        self.model = os.getenv("LM_STUDIO_MODEL", "local-model")
        self.session = None
        self.logger = logging.getLogger("discord_bot.LMStudioService")

        # Remove trailing slash from api_url if present
        self.api_url = self.api_url.rstrip("/")

        # Load prompts
        self.personality_prompt = self._load_prompt("personality.txt")
        self.conversation_prompt = self._load_prompt("conversation_prompt.txt")

        self.logger.info(
            f"🎨 LMStudioService initialized with model: {self.model} at {self.api_url}"
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

    async def test_connection(self) -> bool:
        """Test if LM Studio API server is accessible"""
        session = await self._get_session()
        try:
            # Try to reach the base URL
            async with session.get(
                self.api_url, timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status in [
                    200,
                    404,
                ]:  # 404 is OK - means server is up but endpoint might be different
                    self.logger.info(
                        f"✅ LM Studio server is reachable at {self.api_url}"
                    )
                    return True
                else:
                    self.logger.warning(
                        f"⚠️ LM Studio server responded with status {response.status}"
                    )
                    return False
        except aiohttp.ClientError as e:
            self.logger.error(f"❌ Cannot connect to LM Studio at {self.api_url}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"❌ Unexpected error testing LM Studio connection: {e}")
            return False

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

        # Try multiple possible endpoints
        endpoints = [
            f"{self.api_url}/v1/chat/completions",  # Standard OpenAI-compatible endpoint
            f"{self.api_url}/api/generate",  # Alternative LM Studio endpoint
            f"{self.api_url}/chat/completions",  # Another variant
        ]

        for url in endpoints:
            try:
                self.logger.debug(f"Trying endpoint: {url}")

                # Adjust payload format based on endpoint
                if "/api/generate" in url:
                    # LM Studio's /api/generate format
                    payload = {
                        "model": self.model,
                        "prompt": f"{system_prompt}\n\n{full_prompt}",
                        "stream": False,
                    }
                else:
                    # OpenAI-compatible format
                    payload = {
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": full_prompt},
                        ],
                        "temperature": 0.7,
                        "max_tokens": 1000,
                        "top_p": 0.9,
                    }

                async with session.post(
                    url, json=payload, timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    response_text = await response.text()

                    if response.status == 200:
                        try:
                            response_data = json.loads(response_text)

                            # Handle different response formats
                            if (
                                "choices" in response_data
                                and len(response_data["choices"]) > 0
                            ):
                                choice = response_data["choices"][0]
                                if (
                                    "message" in choice
                                    and "content" in choice["message"]
                                ):
                                    return choice["message"]["content"]
                            elif "response" in response_data:
                                # LM Studio /api/generate format
                                return response_data["response"]
                            elif "content" in response_data:
                                # Direct content field
                                return response_data["content"]
                            elif "text" in response_data:
                                # Text field
                                return response_data["text"]
                            else:
                                self.logger.error(
                                    f"Unexpected response format from {url}: {response_data}"
                                )
                                continue  # Try next endpoint

                        except json.JSONDecodeError as e:
                            self.logger.error(f"Failed to parse JSON from {url}: {e}")
                            self.logger.error(f"Response text: {response_text[:200]}")
                            continue  # Try next endpoint
                    else:
                        self.logger.warning(
                            f"Endpoint {url} returned status {response.status}: {response_text[:200]}"
                        )
                        continue  # Try next endpoint

            except aiohttp.ClientError as e:
                self.logger.warning(f"Connection error for {url}: {e}")
                continue  # Try next endpoint
            except Exception as e:
                self.logger.error(f"Unexpected error with {url}: {e}")
                continue  # Try next endpoint

        # All endpoints failed
        self.logger.error(
            f"❌ All LM Studio endpoints failed. Please check:"
            f"\n  1. LM Studio is running at {self.api_url}"
            f"\n  2. The server is configured with OpenAI API compatibility"
            f"\n  3. The model '{self.model}' is loaded"
            f"\n  4. Check LM Studio logs for more details"
        )
        return "Lỗi: Không thể kết nối đến LM Studio. Vui lòng kiểm tra cấu hình API."

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
        """Split response into natural parts for sequential sending"""
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
