import logging
import os
from typing import Dict, List, Optional, Union

import aiohttp
from langsmith import traceable

from twin.shared.config.settings import Config
from .base_llm_service import BaseLLMService
from .llm_response import LLMResponse


class GeminiService(BaseLLMService):
    def __init__(self):
        super().__init__()

        self.api_key = os.getenv("GEMINI_API_KEY")
        self.api_url = os.getenv(
            "GEMINI_API_URL", "https://generativelanguage.googleapis.com/v1beta/models"
        )
        self.model = Config.LLM_MODEL
        self.session = None
        self.logger = logging.getLogger("discord_bot.GeminiService")

    async def _get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    def _map_tools_to_gemini_format(self, openai_tools: List[Dict]) -> List[Dict]:
        """
        Map OpenAI tool schemas to Gemini functionDeclarations format.

        OpenAI format:
        {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}

        Gemini format:
        {"functionDeclarations": [{"name": "...", "description": "...", "parameters": {...}}]}
        """
        function_declarations = []
        for tool in openai_tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                function_declarations.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {})
                })
        return function_declarations

    @traceable(name="Gemini_Generate", run_type="llm", tags=["gemini", "generation"])
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        use_native_tools: bool = False
    ) -> Union[str, LLMResponse]:
        """
        Generate response from Gemini API.

        Args:
            messages: Mảng tin nhắn theo chuẩn [{"role": "user/assistant", "content": "..."}]
            system_prompt: Dữ liệu Tiềm thức từ Tầng 3 (Dynamic Core Memory).
            use_native_tools: Nếu True, sử dụng Native Function Calling (API Tool Calling).

        Returns:
            LLMResponse object with content, token metadata, and tool_calls if present.
            Falls back to string for backwards compatibility on errors.
        """
        if not self.api_key:
            self.logger.error("Gemini API key not found")
            return "Error: API key not configured."

        session = await self._get_session()

        # 1. Trộn hệ tư tưởng (System Prompt)
        final_system_prompt = self._build_final_system_prompt(system_prompt)

        # 2. Biên dịch mảng `messages` sang chuẩn Gemini
        gemini_contents = []
        for msg in messages:
            role = "model" if msg["role"] == "assistant" else "user"
            gemini_contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        full_url = f"{self.api_url}/{self.model}:generateContent?key={self.api_key}"

        payload = {
            "system_instruction": {"parts": [{"text": final_system_prompt}]},
            "contents": gemini_contents,
            "generationConfig": {
                "temperature": Config.LLM_TEMPERATURE,
                "maxOutputTokens": Config.LLM_MAX_TOKENS,
                "topP": Config.LLM_TOP_P,
                "topK": Config.LLM_TOP_K,
            },
        }

        # 3. [NATIVE TOOL CALLING] Thêm tools vào payload nếu enabled
        if use_native_tools:
            openai_tools = []
            if self.tool_registry:
                openai_tools = self.tool_registry.get_all_openai_schemas()
            if openai_tools:
                gemini_tools = self._map_tools_to_gemini_format(openai_tools)
                payload["tools"] = [{"functionDeclarations": gemini_tools}]
                self.logger.debug(f"🔧 Native tools enabled: {len(gemini_tools)} tools")

        try:
            async with session.post(
                full_url, json=payload, headers={"Content-Type": "application/json"}
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error(f"Gemini API error: {error_text}")
                    return "Error generating response."

                response_data = await response.json()

                # Extract token usage metadata from Gemini response
                usage_metadata = response_data.get("usageMetadata", {})
                input_tokens = usage_metadata.get("promptTokenCount", 0)
                output_tokens = usage_metadata.get("candidatesTokenCount", 0)
                total_tokens = usage_metadata.get(
                    "totalTokenCount", input_tokens + output_tokens
                )

                if (
                    "candidates" in response_data
                    and len(response_data["candidates"]) > 0
                ):
                    candidate = response_data["candidates"][0]
                    if "content" in candidate and "parts" in candidate["content"]:
                        parts = candidate["content"]["parts"]

                        # [NATIVE TOOL CALLING] Parse functionCall from parts
                        tool_calls = None
                        content = ""

                        for part in parts:
                            if "functionCall" in part:
                                fc = part["functionCall"]
                                if not tool_calls:
                                    tool_calls = []
                                tool_calls.append({
                                    "id": f"gemini_{fc.get('name', '')}",
                                    "name": fc.get("name", ""),
                                    "arguments": fc.get("args", {})
                                })
                            elif "text" in part:
                                content += part["text"]

                        if tool_calls:
                            self.logger.info(f"🛠️ Gemini returned {len(tool_calls)} tool calls: {[tc['name'] for tc in tool_calls]}")

                        self.logger.info(
                            f"Gemini API - Input tokens: {input_tokens}, "
                            f"Output tokens: {output_tokens}, Total: {total_tokens}"
                        )

                        return LLMResponse(
                            content=content,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            total_tokens=total_tokens,
                            model=self.model,
                            finish_reason=candidate.get("finishReason"),
                            raw_response=response_data,
                            tool_calls=tool_calls,
                        )

                return "Error: Unexpected response format."

        except Exception as e:
            self.logger.error(f"Error communicating with Gemini API: {e}")
            return "Error generating response."

    async def close(self):
        if self.session:
            await self.session.close()