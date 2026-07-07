"""Unit tests for the embedding trace logger and math utilities."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from twin.shared.llm.embedding.embedding_trace_logger import (
    EmbeddingTraceLogger,
    cosine_similarity,
    token_overlap,
)


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        vec = [1.0, 2.0, 3.0]
        assert cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_zero_vector(self) -> None:
        assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0
        assert cosine_similarity([1.0, 2.0], [0.0, 0.0]) == 0.0

    def test_known_value(self) -> None:
        a = [1.0, 0.0]
        b = [math.sqrt(3) / 2, 0.5]
        assert cosine_similarity(a, b) == pytest.approx(0.866025, abs=1e-5)

    def test_dimension_mismatch(self) -> None:
        with pytest.raises(ValueError):
            cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])


class TestTokenOverlap:
    def test_identical(self) -> None:
        assert token_overlap("Hòa thích ăn bò", "Hòa thích ăn bò") == 1.0

    def test_no_overlap(self) -> None:
        assert token_overlap("Hòa thích bò", "Mai thích gà") == pytest.approx(1 / 5)

    def test_empty(self) -> None:
        assert token_overlap("", "anything") == 0.0
        assert token_overlap("anything", "") == 0.0

    def test_punctuation_normalized(self) -> None:
        assert token_overlap("Hòa thích bò!", "hòa thích bò") == 1.0


class TestEmbeddingTraceLogger:
    def test_disabled_writes_nothing(self, tmp_path: Path) -> None:
        log_path = tmp_path / "trace.jsonl"
        logger = EmbeddingTraceLogger(log_path=log_path, enabled=False)
        logger.log(
            event_type="EMBED",
            model_name="text-embedding-v3",
            provider="openai_compat",
            api_url="https://example.com",
            vector_dim=1024,
            raw_dim=1024,
            l2_norm=1.0,
            latency_ms=12.3,
            cache_hit=False,
            input_text="query: hello",
        )
        assert not log_path.exists()

    def test_enabled_writes_valid_jsonl(self, tmp_path: Path) -> None:
        log_path = tmp_path / "nested" / "trace.jsonl"
        logger = EmbeddingTraceLogger(log_path=log_path, enabled=True)
        logger.log(
            event_type="EMBED",
            model_name="text-embedding-v3",
            provider="openai_compat",
            api_url="https://example.com",
            vector_dim=1024,
            raw_dim=1024,
            l2_norm=1.0,
            latency_ms=12.345,
            cache_hit=False,
            input_text="query: hello",
            query_text="hello",
            matched_text="world",
            cosine_similarity=0.91,
            token_overlap=0.71,
            action="KNN_RESULT",
            knn_score=0.09,
            bm25_score=0.12,
            rrf_rank=1,
        )

        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event_type"] == "EMBED"
        assert record["model_name"] == "text-embedding-v3"
        assert record["provider"] == "openai_compat"
        assert record["vector_dim"] == 1024
        assert record["raw_dim"] == 1024
        assert record["l2_norm"] == 1.0
        assert record["latency_ms"] == 12.345
        assert record["cache_hit"] is False
        assert record["input_text"] == "query: hello"
        assert record["query_text"] == "hello"
        assert record["matched_text"] == "world"
        assert record["cosine_similarity"] == 0.91
        assert record["token_overlap"] == 0.71
        assert record["action"] == "KNN_RESULT"
        assert record["knn_score"] == 0.09
        assert record["bm25_score"] == 0.12
        assert record["rrf_rank"] == 1
        assert "timestamp" in record

    def test_multiple_lines(self, tmp_path: Path) -> None:
        log_path = tmp_path / "trace.jsonl"
        logger = EmbeddingTraceLogger(log_path=log_path, enabled=True)
        for i in range(3):
            logger.log(
                event_type="EMBED",
                model_name="m",
                provider="p",
                api_url="u",
                vector_dim=1,
                raw_dim=1,
                l2_norm=1.0,
                latency_ms=float(i),
                cache_hit=False,
                input_text=f"q{i}",
            )
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3
        assert all(json.loads(line)["input_text"].startswith("q") for line in lines)

    def test_appends_to_existing_file(self, tmp_path: Path) -> None:
        log_path = tmp_path / "trace.jsonl"
        log_path.write_text('{"old": true}\n', encoding="utf-8")
        logger = EmbeddingTraceLogger(log_path=log_path, enabled=True)
        logger.log(
            event_type="EMBED",
            model_name="m",
            provider="p",
            api_url="u",
            vector_dim=1,
            raw_dim=1,
            l2_norm=1.0,
            latency_ms=0.0,
            cache_hit=False,
            input_text="new",
        )
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["old"] is True
        assert json.loads(lines[1])["input_text"] == "new"
