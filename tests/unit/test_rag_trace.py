"""Tests for retrieval trace data structures and RAG instrumentation.

These tests verify that:
- Trace objects serialise correctly
- A successful RAG call produces a trace with per-stage data
- Vector stage count is recorded
- BM25 stage count is recorded when Meilisearch is enabled
- Reranker enabled/disabled is captured
- Trace candidates exclude raw text (no chunk_text)
- v2: backend attribution, reranker deltas, degraded backend info, filtering counts
"""

from __future__ import annotations

import time
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
    # RAG retrieval embeds the query via encode_query (asymmetric encoder API).
    encoder.encode_query.return_value = [0.1, 0.2, 0.3]

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
    assert d["score"] == pytest.approx(0.85)
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
    assert d["timing_ms"] == pytest.approx(12.3)


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
    assert d["total_latency_ms"] == pytest.approx(100.0)


def test_retrieval_trace_defaults() -> None:
    """RetrievalTrace defaults must be empty lists and zero."""
    t = RetrievalTrace()
    assert t.stages == []
    assert t.candidates == []
    assert t.reranker_enabled is False
    assert t.total_latency_ms == pytest.approx(0.0)


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
    assert "dedup_filter" in stage_names


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


def test_rag_hanging_qdrant_does_not_block_pool_shutdown() -> None:
    """When Qdrant hangs, pool.shutdown(wait=False) must not block the retrieval.

    Before the fix, the ThreadPoolExecutor context manager called
    shutdown(wait=True) on exit, which blocked until all threads completed.
    Now shutdown(wait=False, cancel_futures=True) is used so a stuck backend
    cannot block the caller beyond the future.result(timeout) window.
    """
    import threading
    from concurrent.futures import Future as _RealFuture

    _hang_event = threading.Event()

    def _hanging_search(**kwargs):
        _hang_event.wait()  # Never set — hangs forever
        return []

    # Meili returns results, Qdrant hangs
    chunks = [_make_chunk()]
    srv = _make_service(chunks=None, meili_chunks=chunks)
    srv._qdrant.search.side_effect = _hanging_search
    srv._qdrant.search_filtered.side_effect = _hanging_search

    # Patch future.result to use a very short timeout so the test completes
    # quickly instead of waiting the default 30s.
    _real_result = _RealFuture.result

    def _short_timeout_result(self, timeout=None):
        if timeout is not None:
            timeout = 0.5
        return _real_result(self, timeout=timeout)

    t0 = time.perf_counter()
    with patch.object(_RealFuture, "result", _short_timeout_result):
        result = srv.answer("test question", group_ids=["group-1"])
    elapsed = time.perf_counter() - t0

    # BM25 results must be returned despite hanging Qdrant
    assert result.retrieval_trace is not None
    assert len(result.retrieval_trace.candidates) >= 1
    assert result.retrieval_trace.retrieval_degraded is True
    # Must NOT block beyond the short timeout + small overhead
    assert elapsed < 5.0, f"Retrieval took {elapsed:.2f}s — pool shutdown may be blocking!"


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

    with patch("concurrent.futures.ThreadPoolExecutor.submit", _tracking_submit):
        srv.answer("test question", group_ids=["group-1"])

    # At minimum, qdrant search and bm25 search must have been submitted
    assert len(submit_calls) >= 2, (
        f"Expected >= 2 submit calls, got {len(submit_calls)}: {submit_calls}"
    )
    # Verify the actual backends (not just any two submits) were involved.
    # The tracked names come from getattr(fn, "__name__", str(fn)) on the
    # callables submitted to the pool.
    assert any("search_rag" in c for c in submit_calls), (
        f"Expected search_rag in submit_calls: {submit_calls}"
    )
    assert any("search" in c and c != submit_calls[0] for c in submit_calls[1:]), (
        f"Expected second search submission, got: {submit_calls}"
    )


# ---------------------------------------------------------------------------
# retrieval_degraded flag (#698)
# ---------------------------------------------------------------------------


def test_retrieval_degraded_false_when_all_backends_healthy() -> None:
    chunks = [_make_chunk()]
    srv = _make_service(chunks=chunks, meili_chunks=chunks)
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    assert result.retrieval_trace.retrieval_degraded is False


def test_retrieval_degraded_true_when_qdrant_fails() -> None:
    srv = _make_service(chunks=None, meili_chunks=[])
    srv._qdrant.search.side_effect = RuntimeError("Qdrant down")
    srv._qdrant.search_filtered.side_effect = RuntimeError("Qdrant down")
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    assert result.retrieval_trace.retrieval_degraded is True


def test_retrieval_degraded_true_when_bm25_fails() -> None:
    chunks = [_make_chunk()]
    srv = _make_service(chunks=chunks, meili_chunks=None)
    srv._meili.search_rag.side_effect = RuntimeError("Meili down")
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    assert result.retrieval_trace.retrieval_degraded is True


def test_retrieval_degraded_in_stream_when_qdrant_fails() -> None:
    srv = _make_service(chunks=None, meili_chunks=[])
    srv._qdrant.search.side_effect = RuntimeError("Qdrant down")
    srv._qdrant.search_filtered.side_effect = RuntimeError("Qdrant down")
    events = list(srv.answer_stream("test question", group_ids=["group-1"]))
    done_events = [e for e in events if e[0] == "done"]
    assert len(done_events) == 1
    trace = done_events[0][1]["retrieval_trace"]
    assert trace["retrieval_degraded"] is True


def test_retrieval_degraded_field_in_trace_model() -> None:
    from services.rag.trace_models import RetrievalTrace

    t = RetrievalTrace()
    assert t.retrieval_degraded is False

    t_degraded = RetrievalTrace(retrieval_degraded=True)
    assert t_degraded.model_dump()["retrieval_degraded"] is True


# ---------------------------------------------------------------------------
# v2: trace_version default
# ---------------------------------------------------------------------------


def test_trace_version_is_2() -> None:
    """RetrievalTrace must report trace_version=2 by default."""
    t = RetrievalTrace()
    assert t.trace_version == 2
    assert t.model_dump()["trace_version"] == 2


def test_trace_version_in_rag_answer() -> None:
    """trace_version must be 2 on traces produced by answer()."""
    srv = _make_service(chunks=[_make_chunk()])
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    assert result.retrieval_trace.trace_version == 2


# ---------------------------------------------------------------------------
# v2: backend attribution
# ---------------------------------------------------------------------------


def test_candidate_has_vector_backend_attribution() -> None:
    """When only vector search is active, each candidate must list 'vector' backend."""
    # Disable meili by setting meili_chunks=None while keeping the qdrant result.
    # _make_service always attaches a meili mock; we need it to return [].
    chunks = [_make_chunk()]
    srv = _make_service(chunks=chunks, meili_chunks=[])
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    assert len(result.retrieval_trace.candidates) >= 1
    cand = result.retrieval_trace.candidates[0]
    backend_names = [b.backend for b in cand.backends]
    assert "vector" in backend_names


def test_candidate_has_bm25_and_vector_attribution_when_both_active() -> None:
    """When a chunk appears in both vector and BM25 results, it must list both backends."""
    chunk = _make_chunk()
    srv = _make_service(chunks=[chunk], meili_chunks=[chunk])
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    assert len(result.retrieval_trace.candidates) >= 1
    cand = result.retrieval_trace.candidates[0]
    backend_names = [b.backend for b in cand.backends]
    assert "vector" in backend_names
    assert "bm25" in backend_names


def test_candidate_backend_attribution_includes_score_and_rank() -> None:
    """Each BackendAttributionTrace must carry a score and 1-based rank."""
    from services.rag.trace_models import BackendAttributionTrace

    chunk = _make_chunk()
    srv = _make_service(chunks=[chunk], meili_chunks=[chunk])
    result = srv.answer("test question", group_ids=["group-1"])
    cand = result.retrieval_trace.candidates[0]  # type: ignore[index]
    for b in cand.backends:
        assert isinstance(b, BackendAttributionTrace)
        assert b.score >= 0.0
        assert b.rank is not None
        assert b.rank >= 1


def test_metadata_branch_attribution_when_enabled() -> None:
    """When metadata search is enabled and returns results, candidates list 'metadata' backend."""
    chunk = _make_chunk()
    srv = _make_service(chunks=[chunk], meili_chunks=[chunk], enable_metadata_search=True)
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    cand = result.retrieval_trace.candidates[0]
    backend_names = [b.backend for b in cand.backends]
    assert "metadata" in backend_names


def test_translated_branch_attribution_when_enabled() -> None:
    """When translated text search is enabled and returns results, candidates list 'translated'."""
    chunk = _make_chunk()
    srv = _make_service(chunks=[chunk], meili_chunks=[chunk], enable_translated_text=True)
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    cand = result.retrieval_trace.candidates[0]
    backend_names = [b.backend for b in cand.backends]
    assert "translated" in backend_names


# ---------------------------------------------------------------------------
# v2: fused rank and score
# ---------------------------------------------------------------------------


def test_candidate_has_fused_rank() -> None:
    """Candidates must carry a non-None fused_rank when Meilisearch is active."""
    chunk = _make_chunk()
    srv = _make_service(chunks=[chunk], meili_chunks=[chunk])
    result = srv.answer("test question", group_ids=["group-1"])
    cand = result.retrieval_trace.candidates[0]  # type: ignore[index]
    assert cand.fused_rank is not None
    assert cand.fused_rank >= 1


def test_candidate_has_fused_score() -> None:
    """Candidates must carry a non-None fused_score when Meilisearch is active."""
    chunk = _make_chunk()
    srv = _make_service(chunks=[chunk], meili_chunks=[chunk])
    result = srv.answer("test question", group_ids=["group-1"])
    cand = result.retrieval_trace.candidates[0]  # type: ignore[index]
    assert cand.fused_score is not None
    assert cand.fused_score >= 0.0


# ---------------------------------------------------------------------------
# v2: final_context_rank
# ---------------------------------------------------------------------------


def test_candidates_have_sequential_final_context_rank() -> None:
    """Each candidate's final_context_rank must be its 1-based position in the final list."""
    chunks = [
        _make_chunk(
            doc_id=f"00000000-0000-0000-0000-00000000000{i}",
            chunk_id=f"00000000-0000-0000-0000-00000000000{i}-0",
            chunk_index=0,
            score=0.9 - i * 0.1,
        )
        for i in range(3)
    ]
    srv = _make_service(chunks=chunks, meili_chunks=[])
    result = srv.answer("test question", group_ids=["group-1"])
    candidates = result.retrieval_trace.candidates  # type: ignore[union-attr]
    for expected_rank, cand in enumerate(candidates, 1):
        assert cand.final_context_rank == expected_rank


# ---------------------------------------------------------------------------
# v2: reranker delta
# ---------------------------------------------------------------------------


def test_reranker_delta_present_when_reranker_configured() -> None:
    """When a reranker is configured, surviving candidates must have a reranker_delta."""
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
    assert result.retrieval_trace is not None
    cand = result.retrieval_trace.candidates[0]
    assert cand.reranker_delta is not None
    assert cand.reranker_delta.input_rank >= 1
    assert cand.reranker_delta.output_rank == 1
    assert cand.reranker_delta.dropped is False


def test_reranker_delta_none_when_no_reranker() -> None:
    """When no reranker is configured, reranker_delta must be None on all candidates."""
    srv = _make_service(chunks=[_make_chunk()])
    result = srv.answer("test question", group_ids=["group-1"])
    for cand in result.retrieval_trace.candidates:  # type: ignore[union-attr]
        assert cand.reranker_delta is None


def test_reranker_delta_in_stream_event() -> None:
    """answer_stream done event must carry reranker_delta on candidates when reranker active."""
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
    candidates = done_payload["retrieval_trace"]["candidates"]
    assert len(candidates) == 1
    delta = candidates[0]["reranker_delta"]
    assert delta is not None
    assert delta["input_rank"] >= 1
    assert delta["output_rank"] == 1
    assert delta["dropped"] is False


def test_reranker_dropped_count_recorded() -> None:
    """reranker_dropped_count must equal the number of candidates dropped by the reranker."""
    chunk_a = _make_chunk(doc_id=_VALID_DOC_UUID, chunk_id=f"{_VALID_DOC_UUID}-0", score=0.9)
    chunk_b = _make_chunk(
        doc_id="00000000-0000-0000-0000-000000000002",
        chunk_id="00000000-0000-0000-0000-000000000002-0",
        score=0.8,
    )
    reranker = MagicMock()
    # Reranker drops chunk_b — only returns chunk_a
    reranker.rerank.return_value = [
        {
            "document_id": _VALID_DOC_UUID,
            "chunk_id": f"{_VALID_DOC_UUID}-0",
            "chunk_index": 0,
            "chunk_text": "kept passage",
            "score": 0.9,
            "doc_title": "Test Document",
            "source_id": "src-1",
            "source_language": "en",
        }
    ]
    srv = _make_service(chunks=[chunk_a, chunk_b], reranker=reranker)
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    assert result.retrieval_trace.reranker_dropped_count == 1


# ---------------------------------------------------------------------------
# v2: score threshold filtering count
# ---------------------------------------------------------------------------


def test_score_threshold_filtered_count() -> None:
    """score_threshold_filtered_count must reflect candidates dropped below threshold."""
    chunk_a = _make_chunk(doc_id=_VALID_DOC_UUID, chunk_id=f"{_VALID_DOC_UUID}-0", score=0.9)
    chunk_b = _make_chunk(
        doc_id="00000000-0000-0000-0000-000000000002",
        chunk_id="00000000-0000-0000-0000-000000000002-0",
        score=0.05,
    )
    # No meili so scores are scaled by 0.5x from vector weight
    srv = _make_service(chunks=[chunk_a, chunk_b], meili_chunks=[])
    # Set threshold high enough to drop chunk_b (its merged score = 0.5*0.05 = 0.025)
    srv._score_threshold = 0.2
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    assert result.retrieval_trace.score_threshold_filtered_count >= 1


# ---------------------------------------------------------------------------
# v2: dedup_count
# ---------------------------------------------------------------------------


def test_dedup_count_is_zero_for_unique_chunks() -> None:
    """When all chunks are unique, dedup_count must be 0."""
    chunks = [
        _make_chunk(
            doc_id=f"00000000-0000-0000-0000-00000000000{i}",
            chunk_id=f"00000000-0000-0000-0000-00000000000{i}-0",
            chunk_index=0,
            score=0.9 - i * 0.1,
        )
        for i in range(3)
    ]
    srv = _make_service(chunks=chunks, meili_chunks=[])
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    assert result.retrieval_trace.dedup_count == 0


# ---------------------------------------------------------------------------
# v2: degraded backend info
# ---------------------------------------------------------------------------


def test_degraded_backends_empty_when_all_healthy() -> None:
    """When all backends succeed, degraded_backends must be an empty list."""
    chunks = [_make_chunk()]
    srv = _make_service(chunks=chunks, meili_chunks=chunks)
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    assert result.retrieval_trace.degraded_backends == []


def test_degraded_backends_records_vector_failure() -> None:
    """When Qdrant fails, degraded_backends must contain a 'vector' entry."""
    srv = _make_service(chunks=None, meili_chunks=[])
    srv._qdrant.search.side_effect = RuntimeError("Qdrant down")
    srv._qdrant.search_filtered.side_effect = RuntimeError("Qdrant down")
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    backends = [d.backend for d in result.retrieval_trace.degraded_backends]
    assert "vector" in backends


def test_degraded_backends_records_bm25_failure() -> None:
    """When Meilisearch BM25 fails, degraded_backends must contain a 'bm25' entry."""
    chunks = [_make_chunk()]
    srv = _make_service(chunks=chunks, meili_chunks=None)
    srv._meili.search_rag.side_effect = RuntimeError("Meili down")
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    backends = [d.backend for d in result.retrieval_trace.degraded_backends]
    assert "bm25" in backends


def test_degraded_backend_has_error_category_not_raw_message() -> None:
    """DegradedBackendInfo must use a safe category string, not the raw exception message."""
    srv = _make_service(chunks=None, meili_chunks=[])
    srv._qdrant.search.side_effect = RuntimeError("contains sensitive path /internal/db")
    srv._qdrant.search_filtered.side_effect = RuntimeError("contains sensitive path /internal/db")
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    for d in result.retrieval_trace.degraded_backends:
        # category must be a controlled string, not the raw exception message
        assert d.error_category in ("timeout", "connection_error", "unexpected_error")
        assert "sensitive" not in d.error_category
        assert "/internal" not in d.error_category


def test_degraded_backends_in_stream_event() -> None:
    """answer_stream done event must carry degraded_backends when a backend fails."""
    srv = _make_service(chunks=None, meili_chunks=[])
    srv._qdrant.search.side_effect = RuntimeError("Qdrant down")
    srv._qdrant.search_filtered.side_effect = RuntimeError("Qdrant down")
    events = list(srv.answer_stream("test question", group_ids=["group-1"]))
    done_events = [e for e in events if e[0] == "done"]
    assert len(done_events) == 1
    trace = done_events[0][1]["retrieval_trace"]
    backends = [d["backend"] for d in trace["degraded_backends"]]
    assert "vector" in backends


# ---------------------------------------------------------------------------
# Embedding failure degradation (#760)
# ---------------------------------------------------------------------------


def test_embedding_failure_sets_retrieval_degraded() -> None:
    """retrieval_degraded must be True when encoder.encode raises."""
    chunks = [_make_chunk()]
    srv = _make_service(chunks=[], meili_chunks=chunks)
    srv._encoder.encode_query.side_effect = RuntimeError("embedding service unavailable")
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    assert result.retrieval_trace.retrieval_degraded is True


def test_embedding_failure_bm25_candidates_returned() -> None:
    """When encoding fails, BM25 candidates from Meilisearch must still be returned."""
    chunks = [_make_chunk()]
    srv = _make_service(chunks=[], meili_chunks=chunks)
    srv._encoder.encode_query.side_effect = RuntimeError("embedding service unavailable")
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    assert len(result.retrieval_trace.candidates) >= 1


def test_embedding_failure_metadata_candidates_returned() -> None:
    """When encoding fails, metadata-search candidates must still be returned."""
    chunks = [_make_chunk()]
    srv = _make_service(chunks=[], meili_chunks=chunks, enable_metadata_search=True)
    srv._encoder.encode_query.side_effect = RuntimeError("embedding service unavailable")
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    assert len(result.retrieval_trace.candidates) >= 1


def test_embedding_failure_translated_candidates_returned() -> None:
    """When encoding fails, translated-text candidates must still be returned."""
    chunks = [_make_chunk()]
    srv = _make_service(chunks=[], meili_chunks=chunks, enable_translated_text=True)
    srv._encoder.encode_query.side_effect = RuntimeError("embedding service unavailable")
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    assert len(result.retrieval_trace.candidates) >= 1


def test_embedding_failure_all_lexical_empty_returns_no_answer() -> None:
    """When encoding fails and all lexical branches return nothing, return no-answer."""
    srv = _make_service(chunks=[], meili_chunks=[])
    srv._encoder.encode_query.side_effect = RuntimeError("embedding service unavailable")
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    assert result.retrieval_trace.candidates == []
    assert "could not find" in result.answer.lower()


def test_embedding_failure_trace_marks_query_embedding_backend() -> None:
    """degraded_backends must include a 'query_embedding' entry when encoding fails."""
    chunks = [_make_chunk()]
    srv = _make_service(chunks=[], meili_chunks=chunks)
    srv._encoder.encode_query.side_effect = RuntimeError("embedding service unavailable")
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    backend_names = [d.backend for d in result.retrieval_trace.degraded_backends]
    assert "query_embedding" in backend_names


def test_embedding_failure_no_raw_exception_in_trace() -> None:
    """DegradedBackendInfo must not contain raw exception text when encoding fails."""
    srv = _make_service(chunks=[], meili_chunks=[])
    srv._encoder.encode_query.side_effect = RuntimeError("contains sensitive path /internal/model")
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    for d in result.retrieval_trace.degraded_backends:
        assert d.error_category in ("timeout", "connection_error", "unexpected_error")
        assert "sensitive" not in d.error_category
        assert "/internal" not in d.error_category


def test_embedding_failure_stream_path_consistent() -> None:
    """answer_stream must also degrade gracefully when encoding fails."""
    chunks = [_make_chunk()]
    srv = _make_service(chunks=[], meili_chunks=chunks)
    srv._encoder.encode_query.side_effect = RuntimeError("embedding service unavailable")
    events = list(srv.answer_stream("test question", group_ids=["group-1"]))
    done_events = [e for e in events if e[0] == "done"]
    assert len(done_events) == 1
    trace = done_events[0][1]["retrieval_trace"]
    assert trace["retrieval_degraded"] is True
    backend_names = [d["backend"] for d in trace["degraded_backends"]]
    assert "query_embedding" in backend_names
    assert len(trace["candidates"]) >= 1


def test_embedding_failure_reranker_runs_on_lexical_candidates() -> None:
    """When encoding fails, the reranker must still run on surviving BM25 candidates."""
    chunks = [_make_chunk()]
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
    srv = _make_service(chunks=[], meili_chunks=chunks, reranker=reranker)
    srv._encoder.encode_query.side_effect = RuntimeError("embedding service unavailable")
    result = srv.answer("test question", group_ids=["group-1"])
    assert result.retrieval_trace is not None
    assert result.retrieval_trace.reranker_enabled is True
    reranker.rerank.assert_called_once()
    stage_names = [s.stage for s in result.retrieval_trace.stages]
    assert "rerank" in stage_names


# ---------------------------------------------------------------------------
# v2: v2 fields in serialised trace
# ---------------------------------------------------------------------------


def test_v2_fields_present_in_model_dump() -> None:
    """All v2 fields must appear in model_dump output for downstream consumers."""
    srv = _make_service(chunks=[_make_chunk()], meili_chunks=[_make_chunk()])
    result = srv.answer("test question", group_ids=["group-1"])
    d = result.model_dump()
    trace_dict = d["retrieval_trace"]
    assert "trace_version" in trace_dict
    assert "degraded_backends" in trace_dict
    assert "scope_filtered_count" in trace_dict
    assert "dedup_count" in trace_dict
    assert "score_threshold_filtered_count" in trace_dict
    assert "reranker_dropped_count" in trace_dict
    # Check candidate v2 fields
    candidate = trace_dict["candidates"][0]
    assert "backends" in candidate
    assert "fused_rank" in candidate
    assert "fused_score" in candidate
    assert "reranker_delta" in candidate
    assert "final_context_rank" in candidate
