"""Tests for retrieval trace data structures and RAG instrumentation.

These tests verify that:
- Trace objects serialise correctly
- A successful RAG call produces a trace with per-stage data
- Vector stage count is recorded
- BM25 stage count is recorded when Meilisearch is enabled
- Reranker enabled/disabled is captured
- Trace candidates exclude raw text (no chunk_text)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.rag.models import AnswerResponse
from services.rag.service import RagService
from services.rag.trace_models import RetrievalCandidateTrace, RetrievalStageTrace, RetrievalTrace
from services.search.models import SearchResult

_VALID_DOC_UUID = "00000000-0000-0000-0000-000000000001"


def _make_chunk(
    doc_id: str = _VALID_DOC_UUID,
    chunk_id: str = f"{_VALID_DOC_UUID}-0",
    chunk_index: int = 0,
    score: float = 0.85,
    text: str = "relevant passage content",
    source_id: str = "src-1",
) -> SearchResult:
    return SearchResult(
        document_id=doc_id,
        score=score,
        chunk_text=text,
        metadata={
            "chunk_id": chunk_id,
            "chunk_index": chunk_index,
            "source_id": source_id,
            "source_language": "en",
        },
    )


def _make_service(
    *,
    chunks: list[SearchResult] | None = None,
    meili_chunks: list[SearchResult] | None = None,
    reranker: object | None = None,
    enable_metadata_search: bool = False,
    enable_translated_text: bool = False,
) -> RagService:
    qdrant = MagicMock()
    if chunks is not None:
        qdrant.search.return_value = chunks
        qdrant.search_filtered.return_value = chunks
    else:
        qdrant.search.return_value = []
        qdrant.search_filtered.return_value = []

    encoder = MagicMock()
    encoder.encode.return_value = [0.1, 0.2, 0.3]

    llm = MagicMock()
    llm.generate.return_value = "Generated answer."
    llm.generate_stream.return_value = iter(["Generated ", "answer."])
    llm.model = "test-model"

    meili = MagicMock()
    if meili_chunks is not None:
        meili.search_rag.return_value = meili_chunks
        meili.search_rag_metadata.return_value = meili_chunks
        meili.search_rag_translated.return_value = meili_chunks
    else:
        meili.search_rag.return_value = []

    conn = MagicMock()
    conn.__enter__.return_value = conn

    return RagService(
        qdrant_client=qdrant,
        encoder=encoder,
        ollama_client=llm,
        connection=conn,
        meili_provider=meili,
        reranker=reranker,
        enable_metadata_search=enable_metadata_search,
        enable_translated_text=enable_translated_text,
    )


# ---------------------------------------------------------------------------
# Fixture: patch DocumentRepository inside rag.service for all trace tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_doc_repo() -> None:
    doc_mock = MagicMock()
    doc_mock.title = "Test Document"
    repo_instance = MagicMock()
    repo_instance.get_by_id.return_value = doc_mock
    with patch("services.rag.service.DocumentRepository", return_value=repo_instance):
        yield


# ---------------------------------------------------------------------------
# Trace model serialisation
# ---------------------------------------------------------------------------


def test_retrieval_candidate_trace_serialises() -> None:
    """RetrievalCandidateTrace must serialise to a dict and back."""
    t = RetrievalCandidateTrace(
        document_id="doc-1",
        chunk_id="doc-1-0",
        chunk_index=0,
        score=0.85,
        source_id="src-1",
        doc_title="Test Doc",
        page_number=3,
        section_heading="Results",
        language="en",
    )
    d = t.model_dump()
    assert d["document_id"] == "doc-1"
    assert d["score"] == 0.85
    assert d["chunk_index"] == 0
    assert d["page_number"] == 3
    assert d["section_heading"] == "Results"
    assert "chunk_text" not in d


def test_retrieval_stage_trace_serialises() -> None:
    """RetrievalStageTrace must serialise to a dict and back."""
    t = RetrievalStageTrace(stage="vector", candidate_count=5, timing_ms=12.3)
    d = t.model_dump()
    assert d["stage"] == "vector"
    assert d["candidate_count"] == 5
    assert d["timing_ms"] == 12.3


def test_retrieval_trace_serialises() -> None:
    """RetrievalTrace must serialise with stages and candidates."""
    t = RetrievalTrace(
        stages=[
            RetrievalStageTrace(stage="vector", candidate_count=3, timing_ms=5.0),
            RetrievalStageTrace(stage="bm25", candidate_count=4, timing_ms=8.0),
        ],
        candidates=[
            RetrievalCandidateTrace(document_id="doc-1", score=0.9),
        ],
        reranker_enabled=True,
        total_latency_ms=100.0,
    )
    d = t.model_dump()
    assert len(d["stages"]) == 2
    assert len(d["candidates"]) == 1
    assert d["reranker_enabled"] is True
    assert d["total_latency_ms"] == 100.0


def test_retrieval_trace_defaults() -> None:
    """RetrievalTrace defaults must be empty lists and zero."""
    t = RetrievalTrace()
    assert t.stages == []
    assert t.candidates == []
    assert t.reranker_enabled is False
    assert t.total_latency_ms == 0.0


# ---------------------------------------------------------------------------
# Trace excludes raw text — privacy rule
# ---------------------------------------------------------------------------


def test_candidate_trace_excludes_chunk_text() -> None:
    """RetrievalCandidateTrace must NOT carry chunk_text to enforce privacy."""
    t = RetrievalCandidateTrace(document_id="doc-1", score=0.85)
    assert not hasattr(t, "chunk_text")


# ---------------------------------------------------------------------------
# RAG service instrumentation
# ---------------------------------------------------------------------------


def test_rag_answer_produces_trace() -> None:
    """A successful RAG call must return AnswerResponse with a retrieval_trace."""
    srv = _make_service(chunks=[_make_chunk()])
    result = srv.answer("test question", group_ids=["group-1"])
    assert isinstance(result, AnswerResponse)
    assert result.retrieval_trace is not None
    assert isinstance(result.retrieval_trace, RetrievalTrace)


def test_rag_trace_includes_vector_stage() -> None:
    """The trace must include a 'vector' stage with the correct candidate count."""
    srv = _make_service(chunks=[_make_chunk() for _ in range(3)])
    result = srv.answer("test question", group_ids=["group-1"])
    stages = result.retrieval_trace.stages
    vector_stages = [s for s in stages if s.stage == "vector"]
    assert len(vector_stages) == 1
    assert vector_stages[0].candidate_count == 3


def test_rag_trace_includes_bm25_stage_when_meili_configured() -> None:
    """When Meilisearch is configured, the trace must include a 'bm25' stage."""
    chunks = [_make_chunk()]
    srv = _make_service(chunks=chunks, meili_chunks=chunks)
    result = srv.answer("test question", group_ids=["group-1"])
    stage_names = [s.stage for s in result.retrieval_trace.stages]
    assert "bm25" in stage_names
    bm25_stages = [s for s in result.retrieval_trace.stages if s.stage == "bm25"]
    assert bm25_stages[0].candidate_count == 1


def test_rag_trace_includes_merge_stage() -> None:
    """When Meilisearch is configured, the trace must include a merge stage."""
    chunks = [_make_chunk()]
    srv = _make_service(chunks=chunks, meili_chunks=chunks)
    result = srv.answer("test question", group_ids=["group-1"])
    stage_names = [s.stage for s in result.retrieval_trace.stages]
    assert "merge_bm25_vector" in stage_names


def test_rag_trace_records_dedup_filter_stage() -> None:
    """The trace must include a dedup/filter stage."""
    chunks = [_make_chunk()]
    srv = _make_service(chunks=chunks, meili_chunks=chunks)
    result = srv.answer("test question", group_ids=["group-1"])
    stage_names = [s.stage for s in result.retrieval_trace.stages]
    assert "dedup" in stage_names


def test_rag_trace_records_final_context_stage() -> None:
    """The trace must include a 'final_context' stage with the truncated count."""
    chunks = [
        _make_chunk(
            doc_id=f"00000000-0000-0000-0000-00000000000{i}",
            chunk_id=f"00000000-0000-0000-0000-00000000000{i}-0",
            chunk_index=0,
            score=0.9 - i * 0.1,
        )
        for i in range(5)
    ]
    srv = _make_service(chunks=chunks, meili_chunks=chunks)
    srv._max_chunks = 3
    result = srv.answer("test question", group_ids=["group-1"])
    stages = result.retrieval_trace.stages
    final_stages = [s for s in stages if s.stage == "final_context"]
    assert len(final_stages) == 1
    assert final_stages[0].candidate_count == 3


def test_rag_trace_reranker_disabled_by_default() -> None:
    """When no reranker is configured, reranker_enabled must be False."""
    srv = _make_service(chunks=[_make_chunk()])
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace.reranker_enabled is False


def test_rag_trace_reranker_enabled() -> None:
    """When a reranker is configured, reranker_enabled must be True and rerank stage present."""
    reranker = MagicMock()
    reranker.rerank.return_value = [
        {
            "document_id": _VALID_DOC_UUID,
            "chunk_id": f"{_VALID_DOC_UUID}-0",
            "chunk_index": 0,
            "chunk_text": "reranked passage",
            "score": 0.95,
            "doc_title": "Test Document",
            "source_id": "src-1",
            "source_language": "en",
        }
    ]
    srv = _make_service(chunks=[_make_chunk()], reranker=reranker)
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace.reranker_enabled is True
    stage_names = [s.stage for s in result.retrieval_trace.stages]
    assert "rerank" in stage_names


def test_rag_trace_candidates_list_final_chunks() -> None:
    """The trace must list the final (truncated) candidates without raw text."""
    chunks = [
        _make_chunk(
            doc_id=_VALID_DOC_UUID,
            chunk_id=f"{_VALID_DOC_UUID}-{i}",
            chunk_index=i,
            score=0.9 - i * 0.1,
        )
        for i in range(3)
    ]
    srv = _make_service(chunks=chunks)
    result = srv.answer("test question", group_ids=["group-1"])
    candidates = result.retrieval_trace.candidates
    assert len(candidates) == 3
    for c in candidates:
        assert isinstance(c, RetrievalCandidateTrace)
        assert not hasattr(c, "chunk_text")


def test_rag_trace_no_results_path() -> None:
    """When no chunks are found, the trace must still include stages (no candidates)."""
    srv = _make_service(chunks=[])
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    assert result.retrieval_trace.candidates == []
    assert len(result.retrieval_trace.stages) > 0
    assert result.answer == (
        "I could not find any relevant information in the documents you have access to."
    )


def test_rag_trace_metadata_search_stage() -> None:
    """When metadata search is enabled, the trace must include a 'metadata' stage."""
    chunks = [_make_chunk()]
    srv = _make_service(chunks=chunks, meili_chunks=chunks, enable_metadata_search=True)
    result = srv.answer("test question", group_ids=["group-1"])
    stage_names = [s.stage for s in result.retrieval_trace.stages]
    assert "metadata" in stage_names


def test_rag_trace_translated_search_stage() -> None:
    """When translated text search is enabled, the trace must include 'translated' stage."""
    chunks = [_make_chunk()]
    srv = _make_service(chunks=chunks, meili_chunks=chunks, enable_translated_text=True)
    result = srv.answer("test question", group_ids=["group-1"])
    stage_names = [s.stage for s in result.retrieval_trace.stages]
    assert "translated" in stage_names


def test_rag_answer_serialises_trace_to_dict() -> None:
    """The trace on AnswerResponse must round-trip through model_dump."""
    srv = _make_service(chunks=[_make_chunk()])
    result = srv.answer("test question", group_ids=["group-1"])
    d = result.model_dump()
    assert "retrieval_trace" in d
    trace_dict = d["retrieval_trace"]
    assert "stages" in trace_dict
    assert "candidates" in trace_dict
    assert "reranker_enabled" in trace_dict
    assert "total_latency_ms" in trace_dict


# ---------------------------------------------------------------------------
# answer_stream trace tests
# ---------------------------------------------------------------------------


def test_answer_stream_done_event_carries_trace() -> None:
    """answer_stream done event must include a retrieval_trace dict."""
    srv = _make_service(chunks=[_make_chunk()])
    events = list(srv.answer_stream("test question", group_ids=["group-1"]))
    done_events = [e for e in events if e[0] == "done"]
    assert len(done_events) == 1
    payload = done_events[0][1]
    assert "retrieval_trace" in payload
    trace = payload["retrieval_trace"]
    assert isinstance(trace, dict)
    assert "stages" in trace
    assert "candidates" in trace
    assert "reranker_enabled" in trace


def test_answer_stream_trace_includes_rerank_stage() -> None:
    """answer_stream trace must include rerank and final_context stages when reranker configured."""
    reranker = MagicMock()
    reranker.rerank.return_value = [
        {
            "document_id": _VALID_DOC_UUID,
            "chunk_id": f"{_VALID_DOC_UUID}-0",
            "chunk_index": 0,
            "chunk_text": "reranked passage",
            "score": 0.95,
            "doc_title": "Test Document",
            "source_id": "src-1",
            "source_language": "en",
        }
    ]
    srv = _make_service(chunks=[_make_chunk()], reranker=reranker)
    events = list(srv.answer_stream("test question", group_ids=["group-1"]))
    done_payload = next(e[1] for e in events if e[0] == "done")
    stage_names = [s["stage"] for s in done_payload["retrieval_trace"]["stages"]]
    assert "rerank" in stage_names
    assert "final_context" in stage_names
    assert done_payload["retrieval_trace"]["reranker_enabled"] is True


def test_answer_stream_trace_no_results_path() -> None:
    """answer_stream done event must include a trace even when no chunks are found."""
    srv = _make_service(chunks=[])
    events = list(srv.answer_stream("test question", group_ids=["group-1"]))
    done_events = [e for e in events if e[0] == "done"]
    assert len(done_events) == 1
    trace = done_events[0][1]["retrieval_trace"]
    assert trace["candidates"] == []
    assert len(trace["stages"]) > 0


# ---------------------------------------------------------------------------
# RAG parallel retrieval (ThreadPoolExecutor)
# ---------------------------------------------------------------------------


def test_rag_retrieval_uses_thread_pool_executor() -> None:
    """_retrieve_chunks must submit backend queries to a ThreadPoolExecutor
    when Meilisearch is configured, not execute them serially."""
    chunks = [_make_chunk()]
    srv = _make_service(chunks=chunks, meili_chunks=chunks)

    from concurrent.futures import ThreadPoolExecutor

    real_submit = ThreadPoolExecutor.submit
    submit_calls: list[str] = []

    def _tracking_submit(self, fn, *args, **kwargs):
        fn_name = getattr(fn, "__name__", str(fn))
        submit_calls.append(fn_name)
        return real_submit(self, fn, *args, **kwargs)

    with patch(
        "concurrent.futures.ThreadPoolExecutor.submit", _tracking_submit
    ):
        srv.answer("test question", group_ids=["group-1"])

    # At minimum, qdrant search and bm25 search must have been submitted
    assert len(submit_calls) >= 2, (
        f"Expected >= 2 submit calls, got {len(submit_calls)}: {submit_calls}"
    )
    # Verify the actual backends (not just any two submits) were involved
    assert any("search" in c for c in submit_calls), (
        f"Expected a search_rag call in submit_calls: {submit_calls}"
    )
    assert any("search" in c for c in submit_calls[1:]), (
        f"Expected multiple search submissions, got: {submit_calls}"
    )
