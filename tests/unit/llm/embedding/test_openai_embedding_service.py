"""Unit tests for OpenAIEmbeddingService with trace logger integration."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from twin.shared.llm.embedding.embedding_factory import create_embedding_service
from twin.shared.llm.embedding.openai_embedding_service import OpenAIEmbeddingService


def _make_mock_response(json_data: dict) -> MagicMock:
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.text = AsyncMock(return_value="")
    mock_resp.json = AsyncMock(return_value=json_data)

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _make_mock_session(post_return) -> MagicMock:
    mock_session = MagicMock()
    mock_session.closed = False
    mock_session.post = MagicMock(return_value=post_return)
    mock_session.close = AsyncMock()
    return mock_session


@pytest.fixture
def fake_vector() -> list[float]:
    return [0.01] * 1024


class TestOpenAIEmbeddingService:
    async def test_get_embedding_logs_trace(self, tmp_path: Path, fake_vector) -> None:
        from twin.shared.llm.embedding.embedding_trace_logger import EmbeddingTraceLogger

        log_path = tmp_path / "trace.jsonl"
        trace_logger = EmbeddingTraceLogger(log_path=log_path, enabled=True)
        service = OpenAIEmbeddingService(
            model_name="text-embedding-v3",
            api_key="test-key",
            api_url="https://example.com/v1",
            expected_dim=1024,
            trace_logger=trace_logger,
            provider="openai_compat",
        )

        response = _make_mock_response(
            {"data": [{"embedding": fake_vector}]}
        )
        mock_session = _make_mock_session(response)

        with patch.object(service, "_get_session", return_value=mock_session):
            vector = await service.get_embedding("query: hello")

        assert len(vector) == 1024
        assert vector == pytest.approx(fake_vector)

        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event_type"] == "EMBED"
        assert record["model_name"] == "text-embedding-v3"
        assert record["provider"] == "openai_compat"
        assert record["api_url"] == "https://example.com/v1"
        assert record["vector_dim"] == 1024
        assert record["raw_dim"] == 1024
        assert record["cache_hit"] is False
        assert record["input_text"] == "query: hello"
        assert record["latency_ms"] >= 0
        assert record["l2_norm"] > 0

    async def test_cache_hit_logs_trace(self, tmp_path: Path, fake_vector) -> None:
        from twin.shared.llm.embedding.embedding_trace_logger import EmbeddingTraceLogger

        log_path = tmp_path / "trace.jsonl"
        trace_logger = EmbeddingTraceLogger(log_path=log_path, enabled=True)
        service = OpenAIEmbeddingService(
            model_name="text-embedding-v3",
            api_key="test-key",
            api_url="https://example.com/v1",
            expected_dim=1024,
            trace_logger=trace_logger,
            provider="openai_compat",
        )

        response = _make_mock_response(
            {"data": [{"embedding": fake_vector}]}
        )
        mock_session = _make_mock_session(response)

        with patch.object(service, "_get_session", return_value=mock_session):
            await service.get_embedding("query: hello")
            await service.get_embedding("query: hello")

        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        first = json.loads(lines[0])
        second = json.loads(lines[1])
        assert first["cache_hit"] is False
        assert second["cache_hit"] is True
        assert second["latency_ms"] == 0.0

    async def test_trace_logger_none_no_log(self, tmp_path: Path, fake_vector) -> None:
        log_path = tmp_path / "trace.jsonl"
        service = OpenAIEmbeddingService(
            model_name="text-embedding-v3",
            api_key="test-key",
            api_url="https://example.com/v1",
            expected_dim=1024,
            trace_logger=None,
        )

        response = _make_mock_response(
            {"data": [{"embedding": fake_vector}]}
        )
        mock_session = _make_mock_session(response)

        with patch.object(service, "_get_session", return_value=mock_session):
            vector = await service.get_embedding("query: hello")

        assert len(vector) == 1024
        assert not log_path.exists()


class TestEmbeddingFactory:
    def test_factory_creates_trace_logger_when_enabled(self, tmp_path: Path, monkeypatch) -> None:
        from twin.shared.config.settings import Config

        monkeypatch.setattr(Config, "EMBEDDING_TRACE_LOG_ENABLED", True)
        monkeypatch.setattr(Config, "EMBEDDING_TRACE_LOG_PATH", str(tmp_path / "factory.jsonl"))

        service = create_embedding_service(provider="openai")
        assert service.trace_logger is not None
        assert service.trace_logger.enabled is True

    def test_factory_no_trace_logger_when_disabled(self, monkeypatch) -> None:
        from twin.shared.config.settings import Config

        monkeypatch.setattr(Config, "EMBEDDING_TRACE_LOG_ENABLED", False)

        service = create_embedding_service(provider="openai")
        assert service.trace_logger is None
