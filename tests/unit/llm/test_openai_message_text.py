"""Coerce OpenAI-compat content/reasoning fields to a string."""

from twin.shared.llm.base_llm_service import (
    LLM_ERROR_RESPONSE,
    is_llm_error_response,
)
from twin.shared.llm.openai_service import _coerce_message_text


def test_coerce_message_text_string_and_empty():
    assert _coerce_message_text("hello") == "hello"
    assert _coerce_message_text("") == ""
    assert _coerce_message_text(None) == ""


def test_coerce_message_text_list_of_parts():
    assert _coerce_message_text(
        [
            {"type": "text", "text": "line one"},
            {"type": "reasoning.text", "text": "line two"},
        ]
    ) == "line one\nline two"


def test_coerce_message_text_reasoning_details_summary():
    assert (
        _coerce_message_text([{"type": "reasoning.summary", "summary": "why"}])
        == "why"
    )


def test_coerce_message_text_list_of_strings():
    assert _coerce_message_text(["a", "b"]) == "a\nb"


def test_is_llm_error_response_rejects_list():
    assert is_llm_error_response(LLM_ERROR_RESPONSE) is True
    assert is_llm_error_response([{"type": "text", "text": "x"}]) is False
    assert is_llm_error_response(None) is False
