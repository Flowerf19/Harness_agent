"""Think stage wrapper: the single LLM-facing abstraction for agent phases.

Think(Decide) -> Think(Refine) -> Act -> Think(Decide) -> ... -> Think(Resolve)

Think never loads IDENTITY.md/SOUL.md manually; all stages go through the
existing LLM service prompt builder so the bot keeps its persona.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from twin.shared.llm.llm_response import LLMResponse
from twin.shared.observability.langsmith import call_with_langsmith_extra, langsmith_extra


class Think:
    """Wrap one LLM call for a named agent stage.

    The provider's ``generate_response`` is already the LLM span, so
    ``Think.run`` is NOT decorated as @traceable. Dynamic metadata is passed
    via ``call_with_langsmith_extra`` so the span is named ``think.{stage}``.
    """

    def __init__(self, llm: Any, logger: logging.Logger | None = None) -> None:
        self.llm = llm
        self.logger = logger or logging.getLogger(__name__)

    async def run(
        self,
        *,
        stage: str,
        messages: list[dict[str, Any]],
        system_prompt: str,
        use_native_tools: bool,
        max_tokens: int,
        trace_metadata: dict[str, Any] | None = None,
        tool_choice: Optional[str] = None,
    ) -> str | LLMResponse:
        """Call the LLM for a single Think stage.

        Args:
            stage: One of ``decide``, ``refine``, ``resolve``.
            messages: Conversation messages for this stage.
            system_prompt: Dynamic core memory / context from the caller.
            use_native_tools: Whether native tool schemas are enabled.
            max_tokens: Per-call output token budget.
            trace_metadata: Extra metadata to attach to the LangSmith span.
            tool_choice: Optional OpenAI-style ``tool_choice`` override forwarded
                to the LLM service. Providers that don't understand the field
                accept and ignore it.

        Returns:
            Raw LLM response string or ``LLMResponse``.
        """
        include_tool_catalog = stage in ("decide", "resolve")
        metadata = {
            "workflow_step": f"think.{stage}",
            **(trace_metadata or {}),
        }
        self.logger.debug(
            "Think(%s) calling llm with native_tools=%s include_tool_catalog=%s",
            stage,
            use_native_tools,
            include_tool_catalog,
        )
        return await call_with_langsmith_extra(
            self.llm.generate_response,
            messages=messages,
            system_prompt=system_prompt,
            use_native_tools=use_native_tools,
            include_tool_catalog=include_tool_catalog,
            max_tokens=max_tokens,
            tool_choice=tool_choice,
            langsmith_extra=langsmith_extra(
                name=f"think.{stage}",
                tags=["llm", stage],
                metadata=metadata,
            ),
        )
