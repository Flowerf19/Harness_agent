"""Models for LLM service responses with metadata."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMResponse:
    """
    Response from LLM with metadata including token usage.

    Attributes:
        content: The generated text content
        input_tokens: Number of input/prompt tokens used
        output_tokens: Number of output/completion tokens used
        total_tokens: Total tokens (input + output)
        model: Model name used for generation
        finish_reason: Reason for completion (e.g., "stop", "length")
        raw_response: Raw response data from API (optional, for debugging)
    """

    content: str
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model: Optional[str] = None
    finish_reason: Optional[str] = None
    raw_response: Optional[dict] = field(default_factory=dict, repr=False)

    def __str__(self) -> str:
        return self.content

    def __bool__(self) -> bool:
        return bool(self.content)
