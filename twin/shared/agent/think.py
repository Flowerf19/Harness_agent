"""Think stage wrapper: the single LLM-facing abstraction for agent phases.

Think(Decide) -> Think(Refine) -> Act -> Think(Decide) -> ...

Think never loads prompt files manually. Decide keeps the conversational
persona; Refine receives only its task context and selected-tool guide.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Optional

from twin.shared.llm.llm_response import LLMResponse
from twin.shared.observability.langsmith import call_with_langsmith_extra, langsmith_extra


class Think:
    """Wrap one LLM call for a named agent stage.

    The provider's ``generate_response`` is already the LLM span, so
    ``Think.run`` is NOT decorated as @traceable. Dynamic metadata is passed
    via ``call_with_langsmith_extra`` so the span is named ``think.{stage}``.
    """

    def __init__(
        self,
        llm: Any,
        logger: logging.Logger | None = None,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.llm = llm
        self.logger = logger or logging.getLogger(__name__)
        self._now = now or datetime.now

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
            stage: One of ``decide`` or ``refine``.
            messages: Conversation messages for this stage. A copied user
                message receives the current server time for this inference.
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
        include_tool_catalog = stage == "decide"
        include_persona = stage == "decide"
        stage_messages = self._with_runtime_context(messages)
        metadata = {
            "workflow_step": f"think.{stage}",
            **(trace_metadata or {}),
        }
        self.logger.debug(
            "Think(%s) calling llm with native_tools=%s "
            "include_tool_catalog=%s include_persona=%s",
            stage,
            use_native_tools,
            include_tool_catalog,
            include_persona,
        )
        return await call_with_langsmith_extra(
            self.llm.generate_response,
            messages=stage_messages,
            system_prompt=system_prompt,
            use_native_tools=use_native_tools,
            include_tool_catalog=include_tool_catalog,
            include_persona=include_persona,
            max_tokens=max_tokens,
            tool_choice=tool_choice,
            langsmith_extra=langsmith_extra(
                name=f"think.{stage}",
                tags=["llm", stage],
                metadata=metadata,
            ),
        )

    def _with_runtime_context(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Attach fresh runtime data without mutating persisted conversation state."""
        staged = [dict(message) for message in messages]
        current_time = self._now().strftime("%Y-%m-%d %H:%M:%S")
        runtime_line = f"Thời gian hiện tại: {current_time}"

        for index in range(len(staged) - 1, -1, -1):
            message = staged[index]
            if message.get("role") != "user" or not isinstance(
                message.get("content"), str
            ):
                continue
            content = message["content"].rstrip()
            message["content"] = f"{content}\n\n{runtime_line}" if content else runtime_line
            return staged

        staged.append({"role": "user", "content": runtime_line})
        return staged
