from __future__ import annotations

import pytest

from services.search.hybrid import SearchResult, merge_results


def test_merge_empty_results() -> None:
    merged = merge_results(bm25_results=[], vector_results=[], vector_weight=0.5, bm25_weight=0.5)

    assert merged == []


def test_merge_bm25_only() -> None:
    bm25 = [
        SearchResult(document_id="doc-1", score=1.5),
        SearchResult(document_id="doc-2", score=1.2),
    ]
    merged = merge_results(bm25_results=bm25, vector_results=[], vector_weight=0.5, bm25_weight=0.5)

    assert len(merged) == 2
    assert merged[0].document_id == "doc-1"
    assert merged[0].score == pytest.approx(0.75)  # 1.5 * 0.5


def test_merge_vector_only() -> None:
    vector = [
        SearchResult(document_id="doc-1", score=0.9),
        SearchResult(document_id="doc-2", score=0.8),
    ]
    merged = merge_results(
        bm25_results=[], vector_results=vector, vector_weight=0.7, bm25_weight=0.3
    )

    assert len(merged) == 2
    assert merged[0].document_id == "doc-1"
    assert merged[0].score == pytest.approx(0.63)  # 0.9 * 0.7


def test_merge_deduplicates_by_doc_id() -> None:
    bm25 = [SearchResult(document_id="doc-1", score=1.0)]
    vector = [SearchResult(document_id="doc-1", score=0.9)]

    merged = merge_results(
        bm25_results=bm25, vector_results=vector, vector_weight=0.5, bm25_weight=0.5
    )

    assert len(merged) == 1
    assert merged[0].document_id == "doc-1"
    # Score should be combined: 1.0 * 0.5 + 0.9 * 0.5 = 0.95
    assert merged[0].score == pytest.approx(0.95)


def test_merge_combines_scores_correctly() -> None:
    bm25 = [
        SearchResult(document_id="doc-1", score=2.0),
        SearchResult(document_id="doc-2", score=1.0),
    ]
    vector = [
        SearchResult(document_id="doc-1", score=0.8),
        SearchResult(document_id="doc-3", score=0.9),
    ]

    merged = merge_results(
        bm25_results=bm25, vector_results=vector, vector_weight=0.6, bm25_weight=0.4
    )

    # doc-1: 2.0 * 0.4 + 0.8 * 0.6 = 0.8 + 0.48 = 1.28
    # doc-2: 1.0 * 0.4 = 0.4
    # doc-3: 0.9 * 0.6 = 0.54
    assert len(merged) == 3
    scores = {r.document_id: r.score for r in merged}
    assert scores["doc-1"] == pytest.approx(1.28)
    assert scores["doc-2"] == pytest.approx(0.4)
    assert scores["doc-3"] == pytest.approx(0.54)


def test_merge_sorted_by_score_descending() -> None:
    bm25 = [SearchResult(document_id="doc-1", score=1.0)]
    vector = [SearchResult(document_id="doc-2", score=2.0)]

    merged = merge_results(
        bm25_results=bm25, vector_results=vector, vector_weight=0.5, bm25_weight=0.5
    )

    assert merged[0].document_id == "doc-2"
    assert merged[1].document_id == "doc-1"


def test_merge_tie_breaking_by_doc_id() -> None:
    bm25 = [SearchResult(document_id="doc-b", score=1.0)]
    vector = [SearchResult(document_id="doc-a", score=1.0)]

    merged = merge_results(
        bm25_results=bm25, vector_results=vector, vector_weight=0.5, bm25_weight=0.5
    )

    # Both have same score: 1.0 * 0.5 = 0.5
    # Tie-break by document_id ascending
    assert merged[0].document_id == "doc-a"
    assert merged[1].document_id == "doc-b"


def test_merge_preserves_payload_fields() -> None:
    bm25 = [SearchResult(document_id="doc-1", score=1.0, title="Title 1", chunk_text="chunk 1")]
    vector = [
        SearchResult(
            document_id="doc-1",
            score=0.9,
            title="Title 1 V",
            chunk_text="chunk 1 V",
        )
    ]

    merged = merge_results(
        bm25_results=bm25, vector_results=vector, vector_weight=0.5, bm25_weight=0.5
    )

    # BM25 fields take precedence when deduplicating
    assert merged[0].title == "Title 1"
    assert merged[0].chunk_text == "chunk 1"


def test_merge_different_docs_no_overlap() -> None:
    bm25 = [SearchResult(document_id="doc-1", score=1.5)]
    vector = [SearchResult(document_id="doc-2", score=0.9)]

    merged = merge_results(
        bm25_results=bm25, vector_results=vector, vector_weight=0.5, bm25_weight=0.5
    )

    assert len(merged) == 2
    assert {r.document_id for r in merged} == {"doc-1", "doc-2"}
