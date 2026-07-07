"""Pure tool execution for the agent loop.

Act has no LLM access, no persona loading, and no prompt logic.
It validates and runs tools through the registry, then formats the
observation for the provider that will carry it forward.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from twin.shared.observability import call_with_langsmith_extra, langsmith_extra
from twin.shared.tools.exceptions import BashExecutorUnavailableError


class Act:
    """Execute a single tool call and format the result for the LLM context."""

    def __init__(
        self,
        tool_registry: Any,
        tool_timeout: int,
        llm_type: str,
        logger: logging.Logger,
    ) -> None:
        self.tool_registry = tool_registry
        self.tool_timeout = tool_timeout
        self.llm_type = llm_type
        self.logger = logger

    async def run(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        tool_call_id: str | None = None,
        *,
        trace_metadata: dict[str, Any] | None = None,
        raise_bash_unavailable: bool = False,
    ) -> dict[str, Any]:
        """Execute *tool_name* with *arguments* and return a formatted result message.

        The returned dict is a provider-specific message ready to append to the
        conversation history (OpenAI ``tool`` message or Gemini
        ``functionResponse`` part).

        Args:
            tool_name: Name of the tool to execute.
            arguments: Arguments to pass to the tool.
            tool_call_id: Optional ID for the tool call; generated if omitted.
            trace_metadata: Optional metadata for tracing.
            raise_bash_unavailable: If True, propagate BashExecutorUnavailableError
                instead of converting it to a string error result.

        Returns:
            A dict representing the tool result message for the LLM.
        """
        call_id = tool_call_id or str(uuid.uuid4())
        base_metadata = {
            **(trace_metadata or {}),
            "workflow_step": "act.run",
            "llm_type": self.llm_type,
            "tool_name": tool_name,
            "tool_call_id": call_id,
        }

        try:
            tool_result = await asyncio.wait_for(
                call_with_langsmith_extra(
                    self.tool_registry.execute_tool,
                    tool_name,
                    arguments,
                    langsmith_extra=langsmith_extra(
                        tags=["tool", tool_name],
                        metadata=base_metadata,
                    ),
                ),
                timeout=self.tool_timeout,
            )
            self.logger.info("Tool '%s' executed successfully", tool_name)
        except BashExecutorUnavailableError:
            if raise_bash_unavailable:
                raise
            tool_result = f"Lỗi: Tool '{tool_name}' chưa sẵn sàng."
            self.logger.warning("Tool '%s' unavailable", tool_name)
        except asyncio.TimeoutError:
            tool_result = f"Lỗi: Tool '{tool_name}' timeout."
            self.logger.warning("Tool '%s' timed out", tool_name)
        except Exception as tool_err:
            tool_result = f"Lỗi: {tool_err}"
            self.logger.error("Tool '%s' failed: %s", tool_name, tool_err)

        return _format_tool_result_message(call_id, tool_name, str(tool_result), self.llm_type)


def _format_tool_result_message(
    tool_call_id: str,
    tool_name: str,
    result: str,
    llm_type: str,
) -> dict[str, Any]:
    if llm_type == "gemini":
        return {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": tool_name,
                        "response": {"result": result},
                    }
                }
            ],
        }

    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": result,
    }
