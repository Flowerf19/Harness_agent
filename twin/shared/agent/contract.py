"""Agent-loop contract: stages, results, and shared helpers.

Invariant: every user-visible answer goes through Think(resolve).
Decide and Refine may produce candidates or cancellation reasons, but they
must never become chat output directly.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

ThinkStage = Literal["decide", "refine", "resolve"]


@dataclass(frozen=True, slots=True)
class AgentLoopResult:
    """Normalized output from one agent loop turn.

    Attributes:
        response: The user-facing text answer (from Think(resolve)).
        raw_response: The raw LLM response (string or LLMResponse) from
            Think(resolve), preserved for token accounting and downstream
            normalization.
        messages: The conversation message list after the loop (mutated in place).
        tools_executed: Number of tool calls that were successfully executed.
        iterations: Number of loop iterations (Decide attempts) performed.
        stopped_by: Why the loop ended: 'no_tool', 'max_iterations', 'respond',
            'failure', or 'error'.
    """

    response: str
    raw_response: str | LLMResponse = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    tools_executed: int = 0
    iterations: int = 0
    stopped_by: str = "no_tool"


@dataclass(frozen=True, slots=True)
class RefineDecision:
    """Structured decision produced by Think(refine)."""

    action: str
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    response: str | None = None


_VALID_REFINE_ACTIONS = {"call_tool", "respond"}
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)

SAFE_REFINE_FAILURE_REPLY = (
    "Xin lỗi, tôi cần bạn nói rõ hơn trước khi dùng công cụ này."
)


def extract_json(text: str) -> str:
    """Extract a JSON object from markdown fences or raw text."""
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


def parse_refine_decision(
    raw: str,
    *,
    expected_tool_name: str,
    allow_tool_switch: bool = False,
    allowed_tool_names: set[str] | None = None,
    logger: logging.Logger | None = None,
) -> RefineDecision | None:
    """Parse a JSON refine decision and validate tool-switch rules."""
    text = (raw or "").strip()
    log = logger or logging.getLogger(__name__)
    try:
        data = json.loads(extract_json(text))
    except Exception as exc:
        log.warning("Invalid refine JSON: %s | raw=%r", exc, text[:200])
        return None

    action = str(data.get("action") or "").strip().lower()
    if action not in _VALID_REFINE_ACTIONS:
        log.warning("Invalid refine action: %r", action)
        return None

    if action == "respond":
        response = str(data.get("response") or "").strip()
        return RefineDecision(
            action="respond", response=response or SAFE_REFINE_FAILURE_REPLY
        )

    tool_name = str(data.get("tool_name") or "").strip()
    if tool_name != expected_tool_name:
        if not allow_tool_switch:
            log.warning(
                "Refine attempted to switch tool: expected=%s actual=%s",
                expected_tool_name,
                tool_name,
            )
            return None
        if not tool_name or (
            allowed_tool_names is not None and tool_name not in allowed_tool_names
        ):
            log.warning(
                "Refine switched to unknown tool: %r (allowed=%s)",
                tool_name,
                sorted(allowed_tool_names) if allowed_tool_names else None,
            )
            return None
        log.info(
            "Refine routed to prerequisite tool: expected=%s actual=%s",
            expected_tool_name,
            tool_name,
        )

    arguments = data.get("arguments")
    if arguments is None and isinstance(data.get("tool_input"), dict):
        arguments = data["tool_input"]
    if not isinstance(arguments, dict):
        log.warning("Refine call_tool missing object arguments")
        return None

    return RefineDecision(action="call_tool", tool_name=tool_name, arguments=arguments)


def format_tool_call_message(tool_call: dict[str, Any], llm_type: str) -> dict[str, Any]:
    """Format a tool call as an assistant/model message for the conversation."""
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


def format_tool_result_message(
    tool_call_id: str, tool_name: str, result: str, llm_type: str
) -> dict[str, Any]:
    """Format a tool execution result as a user/tool message for the conversation."""
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


def build_refine_system_prompt(
    system_prompt: str,
    tool_guide: str,
    selected: dict[str, Any],
    missing_required: list[str] | None = None,
) -> str:
    """Build the system prompt for Think(refine) with the selected tool guide."""
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
        switch_clause = (
            "- Không thực thi nếu thiếu dữ liệu quan trọng; hãy respond/hỏi lại."
        )
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

    parts = [
        system_prompt.strip(),
        "=== HƯỚNG DẪN TOOL ĐÃ CHỌN ===\n" + tool_guide,
        contract,
    ]
    return "\n\n".join(part for part in parts if part)


def build_refine_messages(
    messages: list[dict[str, Any]], selected: dict[str, Any]
) -> list[dict[str, Any]]:
    """Append the refine instruction to the conversation."""
    instruction = (
        "Tinh chỉnh hoặc hủy tool call đã chọn theo system prompt. "
        "Chỉ trả về JSON hợp lệ."
    )
    return list(messages) + [{"role": "user", "content": instruction}]


def missing_required_args(
    tool_registry: Any, tool_name: str, arguments: Any
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
