"""Models for LLM service responses with metadata."""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class LLMResponse:
    """
    Response from LLM with metadata including token usage and tool calls.

    Attributes:
        content: The generated text content (empty if tool_calls present)
        input_tokens: Number of input/prompt tokens used
        output_tokens: Number of output/completion tokens used
        total_tokens: Total tokens (input + output)
        model: Model name used for generation
        finish_reason: Reason for completion (e.g., "stop", "length", "tool_calls")
        raw_response: Raw response data from API (optional, for debugging)
        tool_calls: List of tool calls requested by LLM (for native function calling)
            Each tool_call dict has: {"id": "...", "name": "...", "arguments": {...}}
    """

    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model: Optional[str] = None
    finish_reason: Optional[str] = None
    raw_response: Optional[dict] = field(default_factory=dict, repr=False)
    tool_calls: Optional[List[Dict[str, Any]]] = None

    def __str__(self) -> str:
        return self.content

    def __bool__(self) -> bool:
        return bool(self.content) or bool(self.tool_calls)

    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls."""
        return bool(self.tool_calls)
