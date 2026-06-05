import json
import logging
from typing import Dict, List, Optional, Union

import aiohttp
from langsmith import traceable

from twin.shared.config.settings import Config
from .base_llm_service import (
    BaseLLMService,
    LLM_ERROR_BAD_FORMAT,
    LLM_ERROR_RESPONSE,
)
from .llm_response import LLMResponse


class OpenAIService(BaseLLMService):
    """
    Generic OpenAI-compatible chat completions service.

    Works with OpenAI and compatible routers/endpoints such as 9Router,
    OpenRouter, LM Studio, and other /v1/chat/completions providers.
    """

    def __init__(self, persona_path: str = "memories"):
        super().__init__(persona_path=persona_path)

        self.api_key = Config.OPENAI_API_KEY
        self.api_url = Config.OPENAI_API_URL.rstrip("/")
        self.model = Config.OPENAI_MODEL
        self.session = None
        self.logger = logging.getLogger("discord_bot.OpenAIService")

    async def _get_session(self):
        if self.session is None:
            timeout = aiohttp.ClientTimeout(
                total=Config.LLM_REQUEST_TIMEOUT,
                connect=Config.LLM_CONNECT_TIMEOUT,
            )
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    @traceable(name="OpenAI_Generate", run_type="llm", tags=["openai", "generation"])
    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        use_native_tools: bool = False,
        max_tokens: Optional[int] = None,
    ) -> Union[str, LLMResponse]:
        session = await self._get_session()
        final_system_prompt = self._build_final_system_prompt(system_prompt)

        # Strict chat templates (Qwen-derived, e.g. LM Studio) raise
        # "No user query found in messages" when the first non-system message
        # is an assistant turn. A channel's active-context window can start
        # with a "Bot:" turn, so drop any leading assistant messages. Lenient
        # providers (9Router, OpenRouter) are unaffected by the trim.
        first_user = next(
            (i for i, m in enumerate(messages) if m.get("role") == "user"), None
        )
        convo = messages[first_user:] if first_user is not None else messages
        api_messages = [{"role": "system", "content": final_system_prompt}] + convo

        payload = {
            "model": self.model,
            "messages": api_messages,
            "temperature": Config.LLM_TEMPERATURE,
            "max_tokens": max_tokens or Config.LLM_MAX_TOKENS,
            "top_p": Config.LLM_TOP_P,
            "frequency_penalty": Config.LLM_FREQUENCY_PENALTY,
            "presence_penalty": Config.LLM_PRESENCE_PENALTY,
        }

        if use_native_tools:
            tool_schemas = []
            if self.tool_registry:
                tool_schemas = self.tool_registry.get_all_openai_schemas()
            if tool_schemas:
                payload["tools"] = tool_schemas
                self.logger.debug("Native tools enabled: %s tools", len(tool_schemas))

        try:
            async with session.post(
                f"{self.api_url}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    self.logger.error("OpenAI-compatible API error: %s", error_text)
                    return LLM_ERROR_RESPONSE

                # Some OpenAI-compatible gateways return valid JSON without
                # a proper JSON content-type header. Keep parsing tolerant so
                # existing providers continue to work unchanged.
                response_data = await response.json(content_type=None)
                usage = response_data.get("usage", {})
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

                if "choices" not in response_data or not response_data["choices"]:
                    return LLM_ERROR_BAD_FORMAT

                choice = response_data["choices"][0]
                message = choice.get("message", {})
                content = message.get("content", "") or ""
                reasoning_content = message.get("reasoning_content", "") or None
                reasoning_only = False

                if not content and reasoning_content:
                    content = reasoning_content
                    reasoning_only = True

                tool_calls = None
                if message.get("tool_calls"):
                    tool_calls = []
                    for tc in message["tool_calls"]:
                        args_str = tc.get("function", {}).get("arguments", "{}")
                        try:
                            args_dict = json.loads(args_str)
                        except json.JSONDecodeError:
                            self.logger.warning("Failed to parse tool arguments: %s", args_str)
                            args_dict = {}

                        tool_calls.append({
                            "id": tc.get("id", ""),
                            "name": tc.get("function", {}).get("name", ""),
                            "arguments": args_dict,
                        })

                    self.logger.info(
                        "OpenAI-compatible endpoint returned %s tool calls: %s",
                        len(tool_calls),
                        [tc["name"] for tc in tool_calls],
                    )

                self.logger.info(
                    "OpenAI-compatible API - Input tokens: %s, Output tokens: %s, Total: %s",
                    input_tokens,
                    output_tokens,
                    total_tokens,
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
                    reasoning_content=reasoning_content,
                    reasoning_only=reasoning_only,
                )

        except Exception as e:
            self.logger.error("Error communicating with OpenAI-compatible API: %s", e)
            return LLM_ERROR_RESPONSE

    async def close(self):
        if self.session:
            await self.session.close()
