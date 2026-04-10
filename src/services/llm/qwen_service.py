import logging
import os
import json
from typing import Dict, List, Optional, Union

import aiohttp
from langsmith import traceable

from ...config.settings import Config
from .base_llm_service import BaseLLMService
from .llm_response import LLMResponse


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
        self, 
        messages: List[Dict[str, str]], 
        system_prompt: Optional[str] = None, 
        skip_tools_prompt: bool = False,
        use_native_tools: bool = False
    ) -> Union[str, LLMResponse]:
        """
        Generate response from Qwen API (OpenAI-compatible).

        Args:
            messages: Mảng tin nhắn theo chuẩn [{"role": "user/assistant", "content": "..."}]
            system_prompt: Dữ liệu Tiềm thức từ Tầng 3 (Dynamic Core Memory).
            skip_tools_prompt: Nếu True, không inject TOOLS.md vào system prompt.
            use_native_tools: Nếu True, sử dụng Native Function Calling (API Tool Calling).

        Returns:
            LLMResponse object with content, token metadata, and tool_calls if present.
            Falls back to string for backwards compatibility on errors.
        """
        if not self.api_key:
            self.logger.error("Qwen API key not found")
            return "Error: Qwen API key not configured."

        session = await self._get_session()

        # 1. Trộn Tính cách tĩnh + Tiềm thức User (Tầng 3)
        # Nếu dùng native tools, skip TOOLS.md prompt
        final_system_prompt = self._build_final_system_prompt(
            system_prompt, 
            skip_tools_prompt=skip_tools_prompt or use_native_tools
        )

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
                    self.logger.error(f"Qwen API error: {error_text}")
                    return "Error generating response."

                response_data = await response.json()

                # Extract token usage metadata from OpenAI-compatible response
                usage = response_data.get("usage", {})
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

                if "choices" in response_data and len(response_data["choices"]) > 0:
                    choice = response_data["choices"][0]
                    message = choice.get("message", {})
                    
                    # Extract content (may be empty if tool_calls present)
                    content = message.get("content", "") or ""
                    
                    # [NATIVE TOOL CALLING] Parse tool_calls if present
                    tool_calls = None
                    if "tool_calls" in message and message["tool_calls"]:
                        tool_calls = []
                        for tc in message["tool_calls"]:
                            # Parse arguments from JSON string to dict
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
                        
                        self.logger.info(f"🛠️ Qwen returned {len(tool_calls)} tool calls: {[tc['name'] for tc in tool_calls]}")

                    # Log token usage for debugging
                    self.logger.info(
                        f"Qwen API - Input tokens: {input_tokens}, "
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
            self.logger.error(f"Error communicating with Qwen API: {e}")
            return "Error generating response."

    async def close(self):
        if self.session:
            await self.session.close()
