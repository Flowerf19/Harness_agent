"""Agent loop orchestration: Think(Decide) -> Think(Refine) -> Act -> ...

Think(decide) either answers the user or selects the next tool. Think(refine)
validates one selected tool before Act executes it.
"""
from __future__ import annotations

import logging
from typing import Any

from twin.shared.config.settings import Config
from twin.shared.llm.base_llm_service import LLM_ERROR_RESPONSES
from twin.shared.llm.llm_response import LLMResponse

from .act import Act
from .contract import (
    AgentLoopResult,
    build_refine_messages,
    build_refine_system_prompt,
    format_tool_call_message,
    missing_required_args,
    parse_refine_decision,
    SAFE_REFINE_FAILURE_REPLY,
)
from .think import Think

# Reasoning models (e.g. gpt-5.x-mini) spend output tokens on internal reasoning
# before emitting tool_calls / structured JSON. The default LLM_MAX_TOKENS (~4000)
# can be exhausted by reasoning alone, starving the actual tool selection/refine
# output. Give the tool-loop path a larger explicit budget so structured output
# survives. Scale matches EXTRACT_MAX_TOKENS / PROFILE_CURATION_MAX_TOKENS (4000).
TOOL_SELECTION_MAX_TOKENS = 8000
MAX_ITERATIONS_REPLY = (
    "Xin lỗi, tôi đã đạt giới hạn vòng lặp công cụ nên chưa thể hoàn tất yêu cầu này."
)


class AgentLoop:
    """Owns orchestration only; does not own memory, gateway, or persona loading."""

    def __init__(
        self,
        llm: Any,
        tool_registry: Any,
        tool_prompt_catalog: Any,
        use_native_tools: bool,
        llm_type: str,
        logger: logging.Logger,
        max_iterations: int = 10,
        tool_timeout: int = 60,
        raise_bash_unavailable: bool = False,
    ) -> None:
        self.think = Think(llm, logger)
        self.act = Act(tool_registry, tool_timeout, llm_type, logger)
        self.tool_prompt_catalog = tool_prompt_catalog
        self.use_native_tools = use_native_tools
        self.llm_type = llm_type
        self.logger = logger
        self.max_iterations = max_iterations
        self.raise_bash_unavailable = raise_bash_unavailable

    async def run(
        self,
        *,
        messages: list[dict[str, Any]],
        system_prompt: str,
        trace_metadata: dict[str, Any] | None = None,
    ) -> AgentLoopResult:
        """Run the agent loop and return a normalized result.

        The loop calls Think(Decide) repeatedly. If no tool is selected,
        Decide's content is the final answer. If a tool is selected, the loop
        calls Think(Refine), then Act, appends the observation, and continues.
        """
        tools_executed = 0
        iterations = 0

        for iteration in range(self.max_iterations):
            iterations = iteration + 1

            # ---- Think(Decide) ------------------------------------------------
            decide_response = await self.think.run(
                stage="decide",
                messages=messages,
                system_prompt=system_prompt,
                use_native_tools=self.use_native_tools,
                max_tokens=TOOL_SELECTION_MAX_TOKENS,
                trace_metadata=trace_metadata,
                tool_choice=Config.LLM_TOOL_CHOICE,
            )

            # Keep LLM hard-failure sentinels as failures; let ChatTurnRunner
            # convert them into the existing friendly fallback.
            if isinstance(decide_response, str) and decide_response in LLM_ERROR_RESPONSES:
                return AgentLoopResult(
                    response=decide_response,
                    raw_response=decide_response,
                    messages=messages,
                    tools_executed=tools_executed,
                    iterations=iterations,
                    stopped_by="failure",
                )

            if (
                isinstance(decide_response, LLMResponse)
                and decide_response.content in LLM_ERROR_RESPONSES
            ):
                return AgentLoopResult(
                    response=decide_response.content,
                    raw_response=decide_response,
                    messages=messages,
                    tools_executed=tools_executed,
                    iterations=iterations,
                    stopped_by="failure",
                )

            if not isinstance(decide_response, LLMResponse):
                return AgentLoopResult(
                    response=decide_response,
                    raw_response=decide_response,
                    messages=messages,
                    tools_executed=tools_executed,
                    iterations=iterations,
                    stopped_by="answer",
                )

            if not decide_response.has_tool_calls():
                return AgentLoopResult(
                    response=decide_response.content,
                    raw_response=decide_response,
                    messages=messages,
                    tools_executed=tools_executed,
                    iterations=iterations,
                    stopped_by="answer",
                )

            tool_calls = decide_response.tool_calls or []
            selected = dict(tool_calls[0])
            deferred = max(0, len(tool_calls) - 1)
            self.logger.info(
                "AgentLoop selected %s; deferred=%s (iteration %s/%s)",
                selected.get("name"),
                deferred,
                iteration + 1,
                self.max_iterations,
            )

            if not self.tool_prompt_catalog:
                self.logger.warning("Tool call selected but prompt catalog is missing")
                return await self._answer_with_decide(
                    messages=messages,
                    system_prompt=system_prompt,
                    trace_metadata=trace_metadata,
                    tools_executed=tools_executed,
                    iterations=iterations,
                    stopped_by="error",
                    fallback=SAFE_REFINE_FAILURE_REPLY,
                    context_note=(
                        "[Hệ thống] Không thể nạp hướng dẫn tool đã chọn. "
                        "Hãy trả lời người dùng tự nhiên, hỏi rõ thêm nếu cần, "
                        "không đề cập chi tiết kỹ thuật."
                    ),
                )

            tool_name = str(selected.get("name") or "")
            try:
                tool_guide = self.tool_prompt_catalog.render_tool_guide(tool_name)
            except Exception as exc:
                self.logger.warning("Failed to load tool guide for %s: %s", tool_name, exc)
                return await self._answer_with_decide(
                    messages=messages,
                    system_prompt=system_prompt,
                    trace_metadata=trace_metadata,
                    tools_executed=tools_executed,
                    iterations=iterations,
                    stopped_by="error",
                    fallback=SAFE_REFINE_FAILURE_REPLY,
                    context_note=(
                        f"[Hệ thống] Không thể nạp hướng dẫn cho tool '{tool_name}'. "
                        "Hãy trả lời người dùng tự nhiên, hỏi rõ thêm nếu cần, "
                        "không đề cập chi tiết kỹ thuật."
                    ),
                )

            # ---- Think(Refine) ------------------------------------------------
            missing = missing_required_args(
                self.act.tool_registry, tool_name, selected.get("arguments")
            )
            allow_tool_switch = bool(missing)
            if allow_tool_switch:
                self.logger.info(
                    "Selected tool '%s' missing required args %s; allowing refine to route to a prerequisite tool",
                    tool_name,
                    missing,
                )

            refine_response = await self.think.run(
                stage="refine",
                messages=build_refine_messages(messages, selected),
                system_prompt=build_refine_system_prompt(
                    system_prompt, tool_guide, selected, missing
                ),
                use_native_tools=False,
                max_tokens=TOOL_SELECTION_MAX_TOKENS,
                trace_metadata=trace_metadata,
            )

            if isinstance(refine_response, str) and refine_response in LLM_ERROR_RESPONSES:
                return AgentLoopResult(
                    response=refine_response,
                    raw_response=refine_response,
                    messages=messages,
                    tools_executed=tools_executed,
                    iterations=iterations,
                    stopped_by="failure",
                )

            if isinstance(refine_response, LLMResponse) and refine_response.content in LLM_ERROR_RESPONSES:
                return AgentLoopResult(
                    response=refine_response.content,
                    raw_response=refine_response,
                    messages=messages,
                    tools_executed=tools_executed,
                    iterations=iterations,
                    stopped_by="failure",
                )

            if isinstance(refine_response, str):
                self.logger.warning("Refine response is not structured: %r", refine_response[:200])
                return await self._answer_with_decide(
                    messages=messages,
                    system_prompt=system_prompt,
                    trace_metadata=trace_metadata,
                    tools_executed=tools_executed,
                    iterations=iterations,
                    stopped_by="error",
                    fallback=SAFE_REFINE_FAILURE_REPLY,
                    context_note=(
                        "[Hệ thống] Có lỗi khi tinh chỉnh tool. "
                        "Hãy trả lời người dùng tự nhiên, hỏi rõ thêm nếu cần, "
                        "không đề cập chi tiết kỹ thuật."
                    ),
                )

            refine = parse_refine_decision(
                refine_response.content,
                expected_tool_name=tool_name,
                allow_tool_switch=allow_tool_switch,
                allowed_tool_names=self.tool_prompt_catalog.allowed_tool_names(),
                logger=self.logger,
            )
            if refine is None:
                return await self._answer_with_decide(
                    messages=messages,
                    system_prompt=system_prompt,
                    trace_metadata=trace_metadata,
                    tools_executed=tools_executed,
                    iterations=iterations,
                    stopped_by="error",
                    fallback=SAFE_REFINE_FAILURE_REPLY,
                    context_note=(
                        f"[Hệ thống] Tool '{tool_name}' không vượt qua bước tinh chỉnh. "
                        "Hãy trả lời người dùng tự nhiên, hỏi rõ thêm nếu cần, "
                        "không đề cập chi tiết kỹ thuật."
                    ),
                )

            if refine.action == "respond":
                reason = refine.response or SAFE_REFINE_FAILURE_REPLY
                return await self._answer_with_decide(
                    messages=messages,
                    system_prompt=system_prompt,
                    trace_metadata=trace_metadata,
                    tools_executed=tools_executed,
                    iterations=iterations,
                    stopped_by="respond",
                    fallback=reason,
                    context_note=(
                        f"[Hệ thống] Không thực thi tool '{tool_name}'. "
                        f"Gợi ý nội bộ: {reason} "
                        "Hãy trả lời người dùng tự nhiên theo ngữ cảnh; "
                        "không nói rằng tool bị hủy."
                    ),
                )

            # ---- Act ----------------------------------------------------------
            refined_call = {
                "id": selected.get("id") or "",
                "name": refine.tool_name,
                "arguments": refine.arguments or {},
            }
            messages.append(format_tool_call_message(refined_call, self.llm_type))

            result_message = await self.act.run(
                tool_name=refined_call["name"],
                arguments=refined_call["arguments"],
                tool_call_id=refined_call["id"] or None,
                trace_metadata=trace_metadata,
                raise_bash_unavailable=self.raise_bash_unavailable,
            )
            messages.append(result_message)
            tools_executed += 1
            # Continue to next Think(Decide)

        else:
            # max_iterations reached without break
            self.logger.warning("AgentLoop hit max_iterations=%s", self.max_iterations)
            return await self._answer_with_decide(
                messages=messages,
                system_prompt=system_prompt,
                trace_metadata=trace_metadata,
                tools_executed=tools_executed,
                iterations=iterations,
                stopped_by="max_iterations",
                fallback=MAX_ITERATIONS_REPLY,
                context_note=(
                    "[Hệ thống] Đã đạt giới hạn vòng lặp công cụ. "
                    "Hãy tổng hợp những gì đã có và trả lời người dùng."
                ),
            )

    async def _answer_with_decide(
        self,
        *,
        messages: list[dict[str, Any]],
        system_prompt: str,
        trace_metadata: dict[str, Any] | None,
        tools_executed: int,
        iterations: int,
        stopped_by: str,
        fallback: str,
        context_note: str,
    ) -> AgentLoopResult:
        """Ask Think(decide) for the final answer without allowing more tools."""
        decide_messages = list(messages)
        if context_note:
            decide_messages.append({"role": "user", "content": context_note})

        decide_response = await self.think.run(
            stage="decide",
            messages=decide_messages,
            system_prompt=system_prompt,
            use_native_tools=False,
            max_tokens=TOOL_SELECTION_MAX_TOKENS,
            trace_metadata=trace_metadata,
        )

        if isinstance(decide_response, str) and decide_response in LLM_ERROR_RESPONSES:
            return AgentLoopResult(
                response=decide_response,
                raw_response=decide_response,
                messages=messages,
                tools_executed=tools_executed,
                iterations=iterations,
                stopped_by="failure",
            )

        if (
            isinstance(decide_response, LLMResponse)
            and decide_response.content in LLM_ERROR_RESPONSES
        ):
            return AgentLoopResult(
                response=decide_response.content,
                raw_response=decide_response,
                messages=messages,
                tools_executed=tools_executed,
                iterations=iterations,
                stopped_by="failure",
            )

        if isinstance(decide_response, LLMResponse):
            response_text = (decide_response.content or "").strip() or fallback
        else:
            response_text = (decide_response or "").strip() or fallback

        return AgentLoopResult(
            response=response_text,
            raw_response=decide_response,
            messages=messages,
            tools_executed=tools_executed,
            iterations=iterations,
            stopped_by=stopped_by,
        )
