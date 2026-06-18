"""Strict lazy tool loop for native tool selection."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

from twin.shared.llm.base_llm_service import LLM_ERROR_RESPONSES
from twin.shared.llm.llm_response import LLMResponse
from twin.shared.observability import call_with_langsmith_extra, langsmith_extra
from twin.shared.observability.langsmith import traceable
from twin.shared.tools.exceptions import BashExecutorUnavailableError


SAFE_REFINE_FAILURE_REPLY = (
    "Xin lỗi, tôi cần bạn nói rõ hơn trước khi dùng công cụ này."
)

# Reasoning models (e.g. gpt-5.x-mini) spend output tokens on internal reasoning
# before emitting tool_calls / structured JSON. The default LLM_MAX_TOKENS (~4000)
# can be exhausted by reasoning alone, starving the actual tool selection/refine
# output. Give the tool-loop path a larger explicit budget so structured output
# survives. Scale matches EXTRACT_MAX_TOKENS / PROFILE_CURATION_MAX_TOKENS (4000).
TOOL_SELECTION_MAX_TOKENS = 8000

_VALID_REFINE_ACTIONS = {"call_tool", "respond"}
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class RefineDecision:
    action: str
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    response: str | None = None


@traceable(name="tool_loop.run", run_type="chain", tags=["tool_loop"])
async def run_strict_tool_loop(
    *,
    llm: Any,
    tool_registry: Any,
    tool_prompt_catalog: Any,
    messages: list[dict[str, Any]],
    system_prompt: str,
    use_native_tools: bool,
    llm_type: str,
    logger: logging.Logger,
    max_iterations: int = 10,
    tool_timeout: int = 60,
    raise_bash_unavailable: bool = False,
    trace_metadata: dict[str, Any] | None = None,
) -> str | LLMResponse:
    """Select one tool, refine with one guide, execute, observe, then continue."""
    llm_response: str | LLMResponse | None = None
    base_metadata = {
        **(trace_metadata or {}),
        "workflow_step": "tool_loop.run",
        "llm_type": llm_type,
        "use_native_tools": use_native_tools,
    }

    for iteration in range(max_iterations):
        llm_response = await call_with_langsmith_extra(
            llm.generate_response,
            messages=messages,
            system_prompt=system_prompt,
            use_native_tools=use_native_tools,
            max_tokens=TOOL_SELECTION_MAX_TOKENS,
            langsmith_extra=langsmith_extra(
                tags=["llm", "tool_selection", llm_type],
                metadata={
                    **base_metadata,
                    "tool_loop_iteration": iteration + 1,
                    "llm_call": "tool_selection",
                },
            ),
        )

        if not isinstance(llm_response, LLMResponse) or not llm_response.has_tool_calls():
            return llm_response

        tool_calls = llm_response.tool_calls or []
        selected = dict(tool_calls[0])
        deferred = max(0, len(tool_calls) - 1)
        logger.info(
            "Strict tool loop selected %s; deferred=%s (iteration %s/%s)",
            selected.get("name"),
            deferred,
            iteration + 1,
            max_iterations,
        )

        if not tool_registry or not tool_prompt_catalog:
            logger.warning("Tool call selected but registry or prompt catalog is missing")
            return LLMResponse(content=SAFE_REFINE_FAILURE_REPLY)

        tool_name = str(selected.get("name") or "")
        try:
            tool_guide = tool_prompt_catalog.render_tool_guide(tool_name)
        except Exception as exc:
            logger.warning("Failed to load tool guide for %s: %s", tool_name, exc)
            return LLMResponse(content=SAFE_REFINE_FAILURE_REPLY)

        # When pass 1 picked a tool but did not supply all of its required args
        # (e.g. manage_user_profile chosen without expected_profile_hash, which
        # only get_profile can produce), refine must be allowed to route to the
        # prerequisite tool named in the guide instead of dead-ending in respond.
        missing_required = _missing_required_args(tool_registry, tool_name, selected.get("arguments"))
        allow_tool_switch = bool(missing_required)
        if allow_tool_switch:
            logger.info(
                "Selected tool '%s' missing required args %s; allowing refine to route to a prerequisite tool",
                tool_name,
                missing_required,
            )

        refine_response = await call_with_langsmith_extra(
            llm.generate_response,
            messages=_build_refine_messages(messages, selected),
            system_prompt=_build_refine_system_prompt(
                system_prompt, tool_guide, selected, missing_required
            ),
            use_native_tools=False,
            max_tokens=TOOL_SELECTION_MAX_TOKENS,
            langsmith_extra=langsmith_extra(
                tags=["llm", "tool_refine", llm_type, tool_name],
                metadata={
                    **base_metadata,
                    "tool_loop_iteration": iteration + 1,
                    "llm_call": "tool_refine",
                    "selected_tool": tool_name,
                    "missing_required": ",".join(missing_required),
                    "allow_tool_switch": allow_tool_switch,
                },
            ),
        )

        if isinstance(refine_response, str):
            if refine_response in LLM_ERROR_RESPONSES:
                return refine_response
            logger.warning("Refine response is not structured: %r", refine_response[:200])
            return LLMResponse(content=SAFE_REFINE_FAILURE_REPLY)

        refine = _parse_refine_decision(
            refine_response.content,
            expected_tool_name=tool_name,
            allow_tool_switch=allow_tool_switch,
            allowed_tool_names=tool_prompt_catalog.allowed_tool_names(),
            logger=logger,
        )
        if refine is None:
            return LLMResponse(content=SAFE_REFINE_FAILURE_REPLY)

        if refine.action == "respond":
            return LLMResponse(content=(refine.response or SAFE_REFINE_FAILURE_REPLY).strip())

        refined_call = {
            "id": selected.get("id") or str(uuid.uuid4()),
            "name": refine.tool_name,
            "arguments": refine.arguments or {},
        }
        messages.append(_format_tool_call_message(refined_call, llm_type))

        try:
            tool_result = await asyncio.wait_for(
                call_with_langsmith_extra(
                    tool_registry.execute_tool,
                    refined_call["name"],
                    refined_call["arguments"],
                    langsmith_extra=langsmith_extra(
                        tags=["tool", refined_call["name"]],
                        metadata={
                            **base_metadata,
                            "tool_loop_iteration": iteration + 1,
                            "tool_name": refined_call["name"],
                            "selected_tool": tool_name,
                            "tool_call_id": refined_call["id"],
                        },
                    ),
                ),
                timeout=tool_timeout,
            )
            logger.info("Tool '%s' executed successfully", refined_call["name"])
        except BashExecutorUnavailableError:
            if raise_bash_unavailable:
                raise
            tool_result = f"Lỗi: Tool '{refined_call['name']}' chưa sẵn sàng."
            logger.warning("Tool '%s' unavailable", refined_call["name"])
        except asyncio.TimeoutError:
            tool_result = f"Lỗi: Tool '{refined_call['name']}' timeout."
            logger.warning("Tool '%s' timed out", refined_call["name"])
        except Exception as tool_err:
            tool_result = f"Lỗi: {tool_err}"
            logger.error("Tool '%s' failed: %s", refined_call["name"], tool_err)

        messages.append(
            _format_tool_result_message(
                refined_call["id"],
                refined_call["name"],
                str(tool_result),
                llm_type,
            )
        )

    logger.warning("Strict tool loop hit max_iterations=%s", max_iterations)
    if isinstance(llm_response, LLMResponse) and not llm_response.content:
        return LLMResponse(content=SAFE_REFINE_FAILURE_REPLY)
    return llm_response or LLMResponse(content=SAFE_REFINE_FAILURE_REPLY)


def _build_refine_system_prompt(
    system_prompt: str,
    tool_guide: str,
    selected: dict[str, Any],
    missing_required: list[str] | None = None,
) -> str:
    selected_json = json.dumps(
        {
            "tool_name": selected.get("name"),
            "arguments": selected.get("arguments") or {},
        },
        ensure_ascii=False,
    )
    if missing_required:
        switch_clause = (
            f"- Tool đã chọn còn THIẾU tham số bắt buộc: {', '.join(missing_required)}.\n"
            "- Nếu dữ liệu thiếu này phải lấy từ một tool khác (xem hướng dẫn, ví dụ "
            "`get_profile` cấp `expected_profile_hash`), hãy call_tool tool tiên quyết đó "
            "trước (đặt tool_name = tên tool tiên quyết) thay vì respond.\n"
            "- Chỉ respond/hỏi lại khi không tool nào lấp được dữ liệu thiếu."
        )
        tool_name_rule = (
            f'- tool_name khi call_tool là "{selected.get("name")}", '
            "HOẶC tool tiên quyết cần để lấy tham số đang thiếu."
        )
    else:
        switch_clause = "- Không thực thi nếu thiếu dữ liệu quan trọng; hãy respond/hỏi lại."
        tool_name_rule = (
            f'- tool_name khi call_tool phải giữ nguyên: "{selected.get("name")}".'
        )
    contract = f"""
=== TINH CHỈNH TOOL ===
Bạn đang ở bước tinh chỉnh/hủy cho đúng một tool đã được chọn.

Tool call đã chọn:
{selected_json}

Đọc hướng dẫn đã nạp rồi chỉ trả về JSON hợp lệ, không Markdown.

Nếu tiếp tục gọi tool:
{{
  "action": "call_tool",
  "tool_name": "{selected.get("name")}",
  "arguments": {{ ... refined arguments ... }}
}}

Nếu hủy tool và trả lời trực tiếp:
{{
  "action": "respond",
  "response": "..."
}}

Ràng buộc:
- action chỉ là "call_tool" hoặc "respond".
{tool_name_rule}
{switch_clause}
""".strip()

    parts = [system_prompt.strip(), "=== HƯỚNG DẪN TOOL ĐÃ CHỌN ===\n" + tool_guide, contract]
    return "\n\n".join(part for part in parts if part)


def _build_refine_messages(
    messages: list[dict[str, Any]],
    selected: dict[str, Any],
) -> list[dict[str, Any]]:
    instruction = (
        "Tinh chỉnh hoặc hủy tool call đã chọn theo system prompt. "
        "Chỉ trả về JSON hợp lệ."
    )
    return list(messages) + [{"role": "user", "content": instruction}]


def _parse_refine_decision(
    raw: str,
    *,
    expected_tool_name: str,
    allow_tool_switch: bool = False,
    allowed_tool_names: set[str] | None = None,
    logger: logging.Logger,
) -> RefineDecision | None:
    text = (raw or "").strip()
    try:
        data = json.loads(_extract_json(text))
    except Exception as exc:
        logger.warning("Invalid refine JSON: %s | raw=%r", exc, text[:200])
        return None

    action = str(data.get("action") or "").strip().lower()
    if action not in _VALID_REFINE_ACTIONS:
        logger.warning("Invalid refine action: %r", action)
        return None

    if action == "respond":
        response = str(data.get("response") or "").strip()
        return RefineDecision(action="respond", response=response or SAFE_REFINE_FAILURE_REPLY)

    tool_name = str(data.get("tool_name") or "").strip()
    if tool_name != expected_tool_name:
        # Tool switching is rejected by default to protect pass-1's single-tool
        # selection. It is only permitted when the selected tool had unmet
        # required args, and only to another registered (prerequisite) tool.
        if not allow_tool_switch:
            logger.warning(
                "Refine attempted to switch tool: expected=%s actual=%s",
                expected_tool_name,
                tool_name,
            )
            return None
        if not tool_name or (allowed_tool_names is not None and tool_name not in allowed_tool_names):
            logger.warning(
                "Refine switched to unknown tool: %r (allowed=%s)",
                tool_name,
                sorted(allowed_tool_names) if allowed_tool_names else None,
            )
            return None
        logger.info(
            "Refine routed to prerequisite tool: expected=%s actual=%s",
            expected_tool_name,
            tool_name,
        )

    arguments = data.get("arguments")
    if arguments is None and isinstance(data.get("tool_input"), dict):
        arguments = data["tool_input"]
    if not isinstance(arguments, dict):
        logger.warning("Refine call_tool missing object arguments")
        return None

    return RefineDecision(action="call_tool", tool_name=tool_name, arguments=arguments)


def _missing_required_args(
    tool_registry: Any,
    tool_name: str,
    arguments: Any,
) -> list[str]:
    """Return required schema args the model did not supply for the selected tool.

    Used to decide whether refine may route to a prerequisite tool. Empty list
    means all required args are present (or the schema is unavailable), keeping
    the strict single-tool refine path for the normal case.
    """
    get_schema = getattr(tool_registry, "get_tool_schema", None)
    if not callable(get_schema):
        return []
    try:
        schema = get_schema(tool_name)
    except Exception:
        return []
    if not isinstance(schema, dict):
        return []
    required = schema.get("function", {}).get("parameters", {}).get("required", [])
    if not isinstance(required, list):
        return []
    provided = arguments if isinstance(arguments, dict) else {}
    missing = []
    for name in required:
        value = provided.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(str(name))
    return missing


def _extract_json(text: str) -> str:
    if not text:
        return "{}"
    fenced = _JSON_FENCE_RE.search(text)
    if fenced:
        return fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _format_tool_call_message(tool_call: dict[str, Any], llm_type: str) -> dict[str, Any]:
    if llm_type == "gemini":
        return {
            "role": "model",
            "parts": [
                {
                    "functionCall": {
                        "name": tool_call["name"],
                        "args": tool_call["arguments"],
                    }
                }
            ],
        }

    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": tool_call["id"],
                "type": "function",
                "function": {
                    "name": tool_call["name"],
                    "arguments": json.dumps(tool_call["arguments"], ensure_ascii=False),
                },
            }
        ],
    }


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
