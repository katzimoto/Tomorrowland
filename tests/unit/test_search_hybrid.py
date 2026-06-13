from __future__ import annotations

import pytest

from services.search.hybrid import RRF_K, SearchResult, merge_results


def _rrf(weight: float, rank: int, k: int = RRF_K) -> float:
    """Weighted Reciprocal Rank Fusion contribution for a single backend hit."""
    return weight / (k + rank)


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
    # Fused score is rank-based: rank 1 with weight 0.5.
    assert merged[0].score == pytest.approx(_rrf(0.5, 1))
    assert merged[1].score == pytest.approx(_rrf(0.5, 2))


def test_merge_bm25_only_ordering_stable_ignores_raw_scores() -> None:
    """BM25-only ordering follows backend rank, not raw score magnitude."""
    bm25 = [
        SearchResult(document_id="doc-a", score=99.0),
        SearchResult(document_id="doc-b", score=98.0),
        SearchResult(document_id="doc-c", score=0.01),
    ]
    merged = merge_results(bm25_results=bm25, vector_results=[], vector_weight=0.7, bm25_weight=0.3)

    assert [r.document_id for r in merged] == ["doc-a", "doc-b", "doc-c"]


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
    assert merged[0].score == pytest.approx(_rrf(0.7, 1))
    assert merged[1].score == pytest.approx(_rrf(0.7, 2))


def test_merge_vector_only_ordering_stable() -> None:
    """Vector-only ordering is preserved regardless of raw cosine values."""
    vector = [
        SearchResult(document_id="doc-x", score=0.51),
        SearchResult(document_id="doc-y", score=0.509),
        SearchResult(document_id="doc-z", score=0.5),
    ]
    merged = merge_results(
        bm25_results=[], vector_results=vector, vector_weight=1.0, bm25_weight=0.0
    )

    assert [r.document_id for r in merged] == ["doc-x", "doc-y", "doc-z"]


def test_merge_combines_ranks_correctly() -> None:
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

    assert len(merged) == 3
    scores = {r.document_id: r.score for r in merged}
    # doc-1 appears in both backends at rank 1 → boosted by both contributions.
    assert scores["doc-1"] == pytest.approx(_rrf(0.4, 1) + _rrf(0.6, 1))
    # doc-2 only in BM25 at rank 2.
    assert scores["doc-2"] == pytest.approx(_rrf(0.4, 2))
    # doc-3 only in vector at rank 2.
    assert scores["doc-3"] == pytest.approx(_rrf(0.6, 2))
    # The cross-backend candidate ranks first.
    assert merged[0].document_id == "doc-1"


def test_merge_sorted_by_score_descending() -> None:
    bm25 = [SearchResult(document_id="doc-1", score=1.0)]
    vector = [SearchResult(document_id="doc-2", score=2.0)]

    merged = merge_results(
        bm25_results=bm25, vector_results=vector, vector_weight=0.5, bm25_weight=0.5
    )

    # Equal weights, both rank 1 → tie on fused score, broken by document_id.
    assert [r.document_id for r in merged] == ["doc-1", "doc-2"]


def test_merge_tie_breaking_by_doc_id() -> None:
    bm25 = [SearchResult(document_id="doc-b", score=1.0)]
    vector = [SearchResult(document_id="doc-a", score=1.0)]

    merged = merge_results(
        bm25_results=bm25, vector_results=vector, vector_weight=0.5, bm25_weight=0.5
    )

    # Both have identical fused score and best rank: tie-break by document_id.
    assert merged[0].document_id == "doc-a"
    assert merged[1].document_id == "doc-b"


def test_merge_tie_breaking_by_chunk_index() -> None:
    """Same fused score and best rank within one document → break by chunk_index."""
    # Each chunk is rank 1 in exactly one backend with equal weights, so both
    # share an identical fused score and best rank (1) and the same document_id.
    bm25 = [
        SearchResult(
            document_id="doc-1",
            score=1.0,
            metadata={"chunk_id": "doc-1-orig-2", "chunk_index": 2},
        ),
    ]
    vector = [
        SearchResult(
            document_id="doc-1",
            score=0.9,
            metadata={"chunk_id": "doc-1-orig-0", "chunk_index": 0},
        ),
    ]
    merged = merge_results(
        bm25_results=bm25, vector_results=vector, vector_weight=0.5, bm25_weight=0.5
    )
    # Tie resolved by ascending chunk_index: chunk 0 before chunk 2.
    assert [r.metadata["chunk_index"] for r in merged] == [0, 2]


def test_high_vector_score_does_not_dominate_better_ranked_bm25() -> None:
    """A huge raw Qdrant score must not beat a better-ranked BM25 candidate."""
    bm25 = [
        SearchResult(document_id="bm25-top", score=3.2),
        SearchResult(document_id="shared", score=1.1),
    ]
    vector = [
        # Enormous raw cosine-ish score, but only rank 3 in the vector list.
        SearchResult(document_id="filler-1", score=0.99),
        SearchResult(document_id="filler-2", score=0.98),
        SearchResult(document_id="bm25-top", score=0.97),
    ]
    merged = merge_results(
        bm25_results=bm25, vector_results=vector, vector_weight=0.5, bm25_weight=0.5
    )

    # bm25-top is rank 1 in BM25 (+ rank 3 in vector) → it stays on top despite
    # filler-1 carrying a near-1.0 raw vector score.
    assert merged[0].document_id == "bm25-top"


def test_candidate_in_both_backends_is_boosted() -> None:
    """A candidate present in both backends outranks single-backend candidates."""
    bm25 = [
        SearchResult(document_id="solo-bm25", score=5.0),
        SearchResult(document_id="shared", score=1.0),
    ]
    vector = [
        SearchResult(document_id="solo-vec", score=0.95),
        SearchResult(document_id="shared", score=0.5),
    ]
    merged = merge_results(
        bm25_results=bm25, vector_results=vector, vector_weight=0.5, bm25_weight=0.5
    )

    # "shared" is rank 2 in both, but the sum of two contributions beats either
    # solo candidate's single rank-1 contribution.
    assert merged[0].document_id == "shared"
    scores = {r.document_id: r.score for r in merged}
    assert scores["shared"] == pytest.approx(_rrf(0.5, 2) + _rrf(0.5, 2))


def test_backend_weights_affect_fused_order() -> None:
    """Tilting the weights toward one backend reorders single-backend hits."""
    bm25 = [SearchResult(document_id="bm25-doc", score=1.0)]
    vector = [SearchResult(document_id="vec-doc", score=1.0)]

    vector_heavy = merge_results(
        bm25_results=bm25, vector_results=vector, vector_weight=0.9, bm25_weight=0.1
    )
    bm25_heavy = merge_results(
        bm25_results=bm25, vector_results=vector, vector_weight=0.1, bm25_weight=0.9
    )

    assert vector_heavy[0].document_id == "vec-doc"
    assert bm25_heavy[0].document_id == "bm25-doc"


def test_rrf_k_changes_dampening() -> None:
    """A smaller k sharpens rank separation; a larger k flattens it."""
    bm25 = [
        SearchResult(document_id="doc-1", score=1.0),
        SearchResult(document_id="doc-2", score=1.0),
    ]
    sharp = merge_results(
        bm25_results=bm25, vector_results=[], vector_weight=0.0, bm25_weight=1.0, k=1
    )
    flat = merge_results(
        bm25_results=bm25, vector_results=[], vector_weight=0.0, bm25_weight=1.0, k=1000
    )

    sharp_gap = sharp[0].score - sharp[1].score
    flat_gap = flat[0].score - flat[1].score
    assert sharp_gap > flat_gap
    # Ordering is identical regardless of k.
    assert [r.document_id for r in sharp] == [r.document_id for r in flat] == ["doc-1", "doc-2"]


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

    # BM25 fields take precedence when deduplicating.
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


def test_merge_preserves_multiple_chunks_per_document() -> None:
    """Chunks from the same document must NOT be collapsed — dedup by chunk_id."""
    vector = [
        SearchResult(
            document_id="doc-1",
            score=0.9,
            chunk_text="chunk A",
            metadata={"chunk_id": "doc-1-orig-0"},
        ),
        SearchResult(
            document_id="doc-1",
            score=0.8,
            chunk_text="chunk B",
            metadata={"chunk_id": "doc-1-orig-1"},
        ),
    ]

    merged = merge_results(
        bm25_results=[], vector_results=vector, vector_weight=1.0, bm25_weight=0.0
    )

    assert len(merged) == 2, "Both chunks must survive — dedup is by chunk_id, not document_id"
    chunk_texts = {r.chunk_text for r in merged}
    assert chunk_texts == {"chunk A", "chunk B"}


def test_merge_deduplicates_same_chunk_from_bm25_and_vector() -> None:
    """The same chunk_id in both sources must be merged into a single result."""
    bm25 = [
        SearchResult(
            document_id="doc-1",
            score=1.0,
            chunk_text="bm25 text",
            metadata={"chunk_id": "doc-1-orig-0"},
        )
    ]
    vector = [
        SearchResult(
            document_id="doc-1",
            score=0.8,
            chunk_text="vector text",
            metadata={"chunk_id": "doc-1-orig-0"},
        )
    ]

    merged = merge_results(
        bm25_results=bm25, vector_results=vector, vector_weight=0.5, bm25_weight=0.5
    )

    assert len(merged) == 1
    # Both backends rank it #1 → fused score is the sum of both contributions.
    assert merged[0].score == pytest.approx(_rrf(0.5, 1) + _rrf(0.5, 1))
    # BM25 fields take precedence.
    assert merged[0].chunk_text == "bm25 text"


def test_merge_deduplicates_by_doc_id() -> None:
    """Results with no chunk_id still dedup by document_id (backward compat)."""
    bm25 = [SearchResult(document_id="doc-1", score=1.0)]
    vector = [SearchResult(document_id="doc-1", score=0.9)]

    merged = merge_results(
        bm25_results=bm25, vector_results=vector, vector_weight=0.5, bm25_weight=0.5
    )

    assert len(merged) == 1
    assert merged[0].document_id == "doc-1"
    assert merged[0].score == pytest.approx(_rrf(0.5, 1) + _rrf(0.5, 1))


def test_chained_merge_preserves_metadata_lane_candidate() -> None:
    """Chaining a metadata lane into an already-fused list keeps its candidate.

    Mirrors RagService's sequential fusion (BM25+vector → metadata → translated):
    the previously-fused list is passed back in as ``vector_results``.
    """
    bm25 = [SearchResult(document_id="doc-1", score=1.0, metadata={"chunk_id": "doc-1-orig-0"})]
    vector = [SearchResult(document_id="doc-2", score=0.9, metadata={"chunk_id": "doc-2-orig-0"})]
    first = merge_results(
        bm25_results=bm25, vector_results=vector, vector_weight=0.5, bm25_weight=0.5
    )

    metadata_lane = [
        SearchResult(
            document_id="doc-3",
            score=2.0,
            chunk_text="meta hit",
            metadata={"chunk_id": "doc-3-meta-0"},
        )
    ]
    fused = merge_results(
        bm25_results=metadata_lane,
        vector_results=first,
        vector_weight=0.2,
        bm25_weight=0.8,
    )

    keys = {(r.metadata or {}).get("chunk_id") for r in fused}
    assert keys == {"doc-1-orig-0", "doc-2-orig-0", "doc-3-meta-0"}
    # The metadata-lane chunk retains its text after the chained merge.
    meta = next(r for r in fused if (r.metadata or {}).get("chunk_id") == "doc-3-meta-0")
    assert meta.chunk_text == "meta hit"
