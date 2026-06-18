"""Shared chat-turn mechanics for Twin agents.

This module intentionally stays below agent behavior. It runs the LLM/tool loop
and normalizes the result; callers still decide memory scope, silence policy,
exception handling, and persistence.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from twin.shared.llm.base_llm_service import LLM_ERROR_RESPONSES
from twin.shared.llm.llm_response import LLMResponse
from twin.shared.observability import langsmith_extra
from twin.shared.observability.langsmith import traceable
from twin.shared.llm.tool_loop import run_strict_tool_loop


@dataclass(frozen=True, slots=True)
class ChatTurnResult:
    """Normalized output from one LLM/tool-loop turn."""

    content: str
    raw_response: str | LLMResponse
    is_failure: bool = False
    reasoning_only: bool = False
    is_structured: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class ChatTurnRunner:
    """Run common chat-turn mechanics without owning agent behavior."""

    def __init__(
        self,
        *,
        llm: Any,
        tool_registry: Any = None,
        use_native_tools: bool = True,
        logger: logging.Logger | None = None,
    ) -> None:
        self.llm = llm
        self.tool_registry = tool_registry
        self.use_native_tools = use_native_tools
        self.logger = logger or logging.getLogger(__name__)
        self.llm_type = self.detect_llm_type(llm)

    @staticmethod
    def detect_llm_type(llm: Any) -> str:
        if llm is None:
            return "openai"
        class_name = llm.__class__.__name__
        if "Gemini" in class_name:
            return "gemini"
        return "openai"

    @traceable(name="chat_turn.run", run_type="chain", tags=["chat_turn"])
    async def run(
        self,
        *,
        messages: list[dict[str, Any]],
        system_prompt: str,
        max_iterations: int = 10,
        tool_timeout: int = 60,
        raise_bash_unavailable: bool = False,
        trace_metadata: dict[str, Any] | None = None,
    ) -> ChatTurnResult:
        metadata = {
            **(trace_metadata or {}),
            "workflow_step": "chat_turn.run",
            "llm_type": self.llm_type,
            "use_native_tools": self.use_native_tools,
            "max_iterations": max_iterations,
            "tool_timeout": tool_timeout,
        }
        raw_response = await run_strict_tool_loop(
            llm=self.llm,
            tool_registry=self.tool_registry,
            tool_prompt_catalog=getattr(self.llm, "tool_prompt_catalog", None),
            messages=messages,
            system_prompt=system_prompt,
            use_native_tools=self.use_native_tools,
            llm_type=self.llm_type,
            logger=self.logger,
            max_iterations=max_iterations,
            tool_timeout=tool_timeout,
            raise_bash_unavailable=raise_bash_unavailable,
            trace_metadata=metadata,
            langsmith_extra=langsmith_extra(
                tags=["tool_loop", self.llm_type],
                metadata=metadata,
            ),
        )

        if isinstance(raw_response, LLMResponse):
            content = raw_response.content
            result = ChatTurnResult(
                content=content,
                raw_response=raw_response,
                is_failure=content in LLM_ERROR_RESPONSES,
                reasoning_only=raw_response.reasoning_only,
                is_structured=True,
                input_tokens=raw_response.input_tokens,
                output_tokens=raw_response.output_tokens,
                total_tokens=raw_response.total_tokens,
            )
        else:
            content = raw_response
            result = ChatTurnResult(
                content=content,
                raw_response=raw_response,
                is_failure=content in LLM_ERROR_RESPONSES,
            )

        return result
