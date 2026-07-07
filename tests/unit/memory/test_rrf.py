"""Unit tests for _rrf_fuse in TimelineSummaryStore."""
from __future__ import annotations

from twin.shared.memory.diary.store import _rrf_fuse


def _doc(summary_id: str, **kwargs) -> dict:
    return {"summary_id": summary_id, **kwargs}


def test_rrf_overlap_reranks():
    """Documents in both lists should rank higher than those in only one."""
    knn = [_doc("a"), _doc("b"), _doc("c")]
    bm25 = [_doc("b"), _doc("d")]

    result = _rrf_fuse(knn, bm25, limit=4)
    ids = [r["summary_id"] for r in result]

    # "b" is in both lists → highest RRF score → first
    assert ids[0] == "b"
    # all unique IDs present
    assert set(ids) == {"a", "b", "c", "d"}


def test_rrf_knn_only():
    knn = [_doc("x"), _doc("y")]
    result = _rrf_fuse(knn, [], limit=5)
    assert [r["summary_id"] for r in result] == ["x", "y"]


def test_rrf_bm25_only():
    bm25 = [_doc("p"), _doc("q")]
    result = _rrf_fuse([], bm25, limit=5)
    assert [r["summary_id"] for r in result] == ["p", "q"]


def test_rrf_empty_both():
    assert _rrf_fuse([], [], limit=5) == []


def test_rrf_limit_applied():
    knn = [_doc(str(i)) for i in range(10)]
    result = _rrf_fuse(knn, [], limit=3)
    assert len(result) == 3


def test_rrf_merges_fields():
    """BM25 doc should have its fields merged into the base KNN doc."""
    knn = [_doc("a", field_knn="knn_val")]
    bm25 = [_doc("a", field_bm25="bm25_val")]

    result = _rrf_fuse(knn, bm25, limit=1)
    assert result[0]["field_knn"] == "knn_val"
    assert result[0]["field_bm25"] == "bm25_val"


def test_rrf_knn_wins_on_field_conflict():
    """When both dicts have the same field, KNN value is kept."""
    knn = [_doc("a", topic="knn_topic")]
    bm25 = [_doc("a", topic="bm25_topic")]

    result = _rrf_fuse(knn, bm25, limit=1)
    assert result[0]["topic"] == "knn_topic"
