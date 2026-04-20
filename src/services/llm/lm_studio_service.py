import logging
import os
import json
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
        super().__init__()

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
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        use_native_tools: bool = False
    ) -> Union[str, LLMResponse]:
        """
        Generate response from LM Studio API (OpenAI-compatible).

        Args:
            messages: Mảng tin nhắn theo chuẩn [{"role": "user/assistant", "content": "..."}]
            system_prompt: Dữ liệu Tiềm thức từ Tầng 3 (Dynamic Core Memory).
            use_native_tools: Nếu True, sử dụng Native Function Calling (API Tool Calling).

        Returns:
            LLMResponse object with content, token metadata, and tool_calls if present.
            Falls back to string for backwards compatibility on errors.
        """
        session = await self._get_session()

        # 1. Trộn Tính cách tĩnh + Tiềm thức User (Tầng 3)
        final_system_prompt = self._build_final_system_prompt(system_prompt)

        # 2. Xếp mảng hội thoại chuẩn OpenAI
        api_messages = [{"role": "system", "content": final_system_prompt}] + messages

        full_url = f"{self.api_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": api_messages,
            "temperature": Config.LLM_TEMPERATURE,
            "max_tokens": Config.LLM_MAX_TOKENS,
            "top_p": Config.LLM_TOP_P,
        }

        # 3. [NATIVE TOOL CALLING] Thêm tools vào payload nếu enabled
        if use_native_tools and self.tool_manager:
            tool_schemas = self.tool_manager.get_native_tool_schemas()
            if tool_schemas:
                payload["tools"] = tool_schemas
                self.logger.debug(f"🔧 Native tools enabled: {len(tool_schemas)} tools")

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

                # [DEBUG] Log raw response
                self.logger.debug(f"📦 Raw response keys: {response_data.keys()}")
                if "choices" in response_data:
                    choice = response_data["choices"][0]
                    self.logger.debug(f"📦 Choice keys: {choice.keys()}")
                    message = choice.get("message", {})
                    self.logger.debug(f"📦 Message keys: {message.keys()}")
                    self.logger.debug(f"📦 Content preview: {str(message.get('content', ''))[:500]}")
                    if "reasoning_content" in message:
                        self.logger.debug(f"📦 reasoning_content preview: {str(message.get('reasoning_content', ''))[:500]}")

                usage = response_data.get("usage", {})
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

                if "choices" in response_data and len(response_data["choices"]) > 0:
                    choice = response_data["choices"][0]
                    message = choice.get("message", {})

                    content = message.get("content", "") or ""

                    # [REASONING MODELS] DeepSeek R1 format
                    if not content:
                        reasoning_content = message.get("reasoning_content", "")
                        if reasoning_content:
                            self.logger.info("🧠 Detected reasoning_content from reasoning model")
                            content = reasoning_content

                    # [NATIVE TOOL CALLING] Parse tool_calls if present
                    tool_calls = None
                    if "tool_calls" in message and message["tool_calls"]:
                        tool_calls = []
                        for tc in message["tool_calls"]:
                            args_str = tc.get("function", {}).get("arguments", "{}")
                            try:
                                args_dict = json.loads(args_str)
                            except json.JSONDecodeError:
                                self.logger.warning(f"⚠️ Failed to parse tool arguments: {args_str}")
                                args_dict = {}

                            tool_calls.append({
                                "id": tc.get("id", ""),
                                "name": tc.get("function", {}).get("name", ""),
                                "arguments": args_dict
                            })

                        self.logger.info(f"🛠️ LM Studio returned {len(tool_calls)} tool calls: {[tc['name'] for tc in tool_calls]}")

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
                        tool_calls=tool_calls,
                    )

                return "Error: Unexpected response format."

        except Exception as e:
            self.logger.error(f"Error communicating with LM Studio API: {e}")
            return "Error generating response."

    async def close(self):
        if self.session:
            await self.session.close()