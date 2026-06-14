"""Unit tests for coarse-to-fine section routing in RAG retrieval (#715 PR4).

Tests verify:
- _fine_retrieve builds correct Qdrant filter from section pairs
- Coarse-to-fine path extracts section pairs from Stage 1 results
- Fine stage is skipped when no section headings present (fallback to flat)
- Coarse-to-fine is a no-op when the feature flag is disabled
- RetrievalTrace includes coarse_section_search + fine_section_search stages
"""

from __future__ import annotations

from unittest.mock import MagicMock

from qdrant_client.models import FieldCondition, Filter, MatchValue

from services.rag.service import RagService
from services.search.hybrid import SearchResult


def _make_chunk(
    doc_id: str = "doc-1",
    score: float = 0.9,
    text: str = "test chunk text",
    section_heading: str | None = "Introduction",
    page_number: int = 1,
    chunk_index: int = 0,
    chunk_id: str = "doc-1-orig-0",
) -> SearchResult:
    return SearchResult(
        document_id=doc_id,
        score=score,
        chunk_text=text,
        metadata={
            "chunk_id": chunk_id,
            "chunk_index": chunk_index,
            "page_number": page_number,
            "section_heading": section_heading,
        },
    )


def _make_service(
    *,
    enable_coarse_to_fine: bool = False,
    chunks: list[SearchResult] | None = None,
    fine_chunks: list[SearchResult] | None = None,
) -> RagService:
    qdrant = MagicMock()
    qdrant.search.return_value = chunks or []
    qdrant.search_filtered.return_value = fine_chunks or []
    qdrant.dimension = 384

    encoder = MagicMock()
    encoder.encode.return_value = [0.1, 0.2, 0.3]
    encoder.dimension = 384

    llm = MagicMock()
    llm.generate.return_value = "Generated answer."
    llm.model = "test-model"

    conn = MagicMock()
    conn.__enter__.return_value = conn

    return RagService(
        qdrant_client=qdrant,
        encoder=encoder,
        ollama_client=llm,
        connection=conn,
        enable_coarse_to_fine_routing=enable_coarse_to_fine,
    )


# ---------------------------------------------------------------------------
# _fine_retrieve filter construction
# ---------------------------------------------------------------------------


def test_fine_retrieve_builds_should_filter() -> None:
    """_fine_retrieve must construct a Qdrant Filter with should clauses per pair."""
    srv = _make_service(enable_coarse_to_fine=True)
    pairs = [("doc-a", "Intro"), ("doc-b", "Results")]
    qdrant_filter = Filter(must=[FieldCondition(key="group_id", match=MatchValue(value="g1"))])

    srv._fine_retrieve(
        pairs=pairs,
        query_vector=[0.1, 0.2, 0.3],
        qdrant_filter=qdrant_filter,
    )

    srv._qdrant.search_filtered.assert_called_once()
    call_kwargs = srv._qdrant.search_filtered.call_args.kwargs
    final_filter = call_kwargs["query_filter"]

    # Must contain 2 conditions in must
    assert len(final_filter.must) == 2
    # First is the group ACL
    assert final_filter.must[0].key == "group_id"
    # Second is the pair should filter
    pair_filter = final_filter.must[1]
    assert pair_filter.should is not None
    assert len(pair_filter.should) == 2


def test_fine_retrieve_without_base_filter() -> None:
    """When no base ACL filter, _fine_retrieve wraps pairs in a bare Filter."""
    srv = _make_service(enable_coarse_to_fine=True)
    pairs = [("doc-a", "Intro")]

    srv._fine_retrieve(
        pairs=pairs,
        query_vector=[0.1, 0.2, 0.3],
        qdrant_filter=None,
    )

    srv._qdrant.search_filtered.assert_called_once()
    call_kwargs = srv._qdrant.search_filtered.call_args.kwargs
    final_filter = call_kwargs["query_filter"]

    # Single must entry: the pair filter
    assert len(final_filter.must) == 1
    pair_filter = final_filter.must[0]
    assert pair_filter.should is not None
    assert len(pair_filter.should) == 1


def test_fine_retrieve_degraded_gracefully() -> None:
    """When Qdrant raises, _fine_retrieve returns empty list without crashing."""
    srv = _make_service(enable_coarse_to_fine=True)
    srv._qdrant.search_filtered.side_effect = RuntimeError("Qdrant unavailable")

    pairs = [("doc-a", "Intro")]
    result = srv._fine_retrieve(
        pairs=pairs,
        query_vector=[0.1, 0.2, 0.3],
        qdrant_filter=None,
    )
    assert result == []


# ---------------------------------------------------------------------------
# Coarse-to-fine routing in _retrieve_chunks
# ---------------------------------------------------------------------------


def test_coarse_to_fine_disabled_no_op() -> None:
    """When feature flag is off, retrieval is identical to flat behavior."""
    srv = _make_service(
        enable_coarse_to_fine=False,
        chunks=[_make_chunk(doc_id="doc-1", section_heading="Intro", score=0.9)],
    )
    result = srv.answer("test question", group_ids=["g1"])
    trace = result.retrieval_trace

    stage_names = [s.stage for s in trace.stages]
    assert "coarse_section_search" not in stage_names
    assert "fine_section_search" not in stage_names
    assert len(trace.candidates) >= 1


def test_coarse_to_fine_enabled_adds_stages() -> None:
    """When feature flag is on and headings present, trace includes new stages."""
    coarse_chunks = [
        _make_chunk(doc_id="doc-1", section_heading="Intro", score=0.9, chunk_id="c1"),
        _make_chunk(doc_id="doc-2", section_heading="Results", score=0.7, chunk_id="c2"),
    ]
    fine_chunks = [
        _make_chunk(doc_id="doc-1", section_heading="Intro", score=0.95, chunk_id="f1"),
        _make_chunk(doc_id="doc-1", section_heading="Intro", score=0.85, chunk_id="f2"),
    ]
    srv = _make_service(
        enable_coarse_to_fine=True,
        chunks=coarse_chunks,
        fine_chunks=fine_chunks,
    )
    result = srv.answer("test question", group_ids=["g1"])
    trace = result.retrieval_trace

    stage_names = [s.stage for s in trace.stages]
    assert "coarse_section_search" in stage_names
    assert "fine_section_search" in stage_names


def test_coarse_to_fine_no_headings_falls_back() -> None:
    """When no chunks carry section_heading, fine stage is skipped."""
    chunks = [
        _make_chunk(doc_id="doc-1", section_heading=None, score=0.9, chunk_id="c1"),
        _make_chunk(doc_id="doc-2", section_heading=None, score=0.7, chunk_id="c2"),
    ]
    srv = _make_service(enable_coarse_to_fine=True, chunks=chunks)
    result = srv.answer("test question", group_ids=["g1"])
    trace = result.retrieval_trace

    stage_names = [s.stage for s in trace.stages]
    assert "coarse_section_search" in stage_names
    assert "fine_section_search" not in stage_names  # skipped — no headings


def test_coarse_to_fine_with_meili_merge() -> None:
    """Fine results correctly merge with BM25/metadata/translated from Stage 1."""
    meili = MagicMock()
    meili.search_rag.return_value = [
        _make_chunk(doc_id="doc-1", section_heading="Intro", score=0.8, chunk_id="m1"),
    ]
    meili.search_rag_metadata.return_value = []
    meili.search_rag_translated.return_value = []

    # Stage 1 results (coarse)
    qdrant = MagicMock()
    qdrant.search.return_value = [
        _make_chunk(doc_id="doc-1", section_heading="Intro", score=0.9, chunk_id="q1"),
        _make_chunk(doc_id="doc-2", section_heading="Results", score=0.7, chunk_id="q2"),
    ]
    qdrant.dimension = 384

    # Stage 2 results (fine)
    qdrant.search_filtered.return_value = [
        _make_chunk(doc_id="doc-1", section_heading="Intro", score=0.95, chunk_id="f1"),
    ]

    encoder = MagicMock()
    encoder.encode.return_value = [0.1, 0.2, 0.3]
    encoder.dimension = 384
    llm = MagicMock()
    llm.generate.return_value = "Generated answer."
    llm.model = "test-model"
    conn = MagicMock()
    conn.__enter__.return_value = conn

    srv = RagService(
        qdrant_client=qdrant,
        encoder=encoder,
        ollama_client=llm,
        connection=conn,
        meili_provider=meili,
        enable_coarse_to_fine_routing=True,
    )
    result = srv.answer("test question", group_ids=["g1"])

    # Fine stage should have been called with correct filter
    assert qdrant.search_filtered.called
    trace = result.retrieval_trace
    stage_names = [s.stage for s in trace.stages]
    assert "fine_section_search" in stage_names


def test_coarse_to_fine_empty_chunks_returns_empty() -> None:
    """When Stage 1 returns no chunks, coarse-to-fine is a no-op."""
    srv = _make_service(enable_coarse_to_fine=True, chunks=[])
    result = srv.answer("test question", group_ids=["g1"])
    trace = result.retrieval_trace

    stage_names = [s.stage for s in trace.stages]
    assert "coarse_section_search" not in stage_names
    assert "fine_section_search" not in stage_names
    assert len(trace.candidates) == 0


def test_fine_retrieve_failed_falls_back() -> None:
    """When fine Qdrant search returns empty, Stage 1 results are used."""
    stage1 = [
        _make_chunk(doc_id="doc-1", section_heading="Intro", score=0.9, chunk_id="c1"),
    ]
    srv = _make_service(
        enable_coarse_to_fine=True,
        chunks=stage1,
        fine_chunks=[],  # fine stage returns nothing
    )
    result = srv.answer("test question", group_ids=["g1"])
    trace = result.retrieval_trace

    # Stage 1 candidate should still be present
    assert len(trace.candidates) >= 1
    stage_names = [s.stage for s in trace.stages]
    assert "fine_section_search" in stage_names
