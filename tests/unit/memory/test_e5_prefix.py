"""Unit tests for e5 asymmetric prefix on embedding callers."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from twin.shared.tools.modules.memory.search_memory_tool import SearchMemoryTool
from twin.shared.memory.manager import format_preflight_for_prompt, SharedMemoryManager


class CapturingEmbeddingService:
    """Records all texts passed to get_embedding."""

    def __init__(self, dim: int = 384):
        self.texts: list[str] = []
        self.dim = dim

    async def get_embedding(self, text: str) -> list[float]:
        self.texts.append(text)
        return [0.1] * self.dim


class FakeStore:
    async def search(self, user_id, query_embedding, limit, *, query_text=None, topic_filter=None):
        return []

    async def get_recent(self, user_id, limit):
        return []


@pytest.mark.asyncio
async def test_search_memory_tool_query_prefix():
    """search_memory_tool must prepend 'query: ' before calling embedding."""
    svc = CapturingEmbeddingService()
    store = FakeStore()
    tool = SearchMemoryTool(timeline_summary_store=store, embedding_service=svc)

    await tool.execute(user_id="12345", mode="semantic", query="phim hoạt hình")

    assert len(svc.texts) == 1
    assert svc.texts[0] == "query: phim hoạt hình"


@pytest.mark.asyncio
async def test_preflight_context_query_prefix():
    """manager._preflight_context must prepend 'query: ' before embedding call."""
    svc = CapturingEmbeddingService()
    store = FakeStore()

    active_mock = MagicMock()
    active_mock.get_context = AsyncMock(return_value=[])
    profile_mock = MagicMock()
    profile_mock.get_system_prompt_context = AsyncMock(return_value="")

    manager = SharedMemoryManager(
        active=active_mock,
        profile_store=profile_mock,
        timeline_summary_store=store,
        embedding_service=svc,
    )

    result = await manager._preflight_context("12345", "nhạc jazz")
    assert len(svc.texts) == 1
    assert svc.texts[0] == "query: nhạc jazz"


def test_format_preflight_reads_summary_field():
    summaries = [{"summary": "User thích nhạc jazz.", "summary_id": "s1"}]
    result = format_preflight_for_prompt(summaries)
    assert "User thích nhạc jazz." in result


def test_format_preflight_fallback_content_field():
    """Backward compat: if only 'content' field present, should still render."""
    summaries = [{"content": "Old content field.", "summary_id": "s2"}]
    result = format_preflight_for_prompt(summaries)
    assert "Old content field." in result


def test_format_preflight_summary_wins_over_content():
    """When both fields present, 'summary' takes precedence."""
    summaries = [{"summary": "New summary.", "content": "Old content.", "summary_id": "s3"}]
    result = format_preflight_for_prompt(summaries)
    assert "New summary." in result
    assert "Old content." not in result
