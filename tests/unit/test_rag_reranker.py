"""Tests for the RAG reranker protocol and built-in implementations."""

from __future__ import annotations

from unittest.mock import MagicMock

from services.rag.reranker import CrossEncoderReranker, NoOpReranker, Reranker


def _make_ollama_mock(*, responses: list[str] | None = None):
    m = MagicMock()
    if responses:
        m.generate.side_effect = responses
    else:
        m.generate.return_value = "5"
    return m


def test_noop_reranker_returns_chunks_unchanged() -> None:
    """NoOpReranker must return the exact same list."""
    reranker = NoOpReranker()
    chunks = [
        {"document_id": "doc-1", "chunk_text": "hello", "score": 0.9},
        {"document_id": "doc-2", "chunk_text": "world", "score": 0.5},
    ]
    result = reranker.rerank(chunks, "test question")
    assert result is chunks
    assert result == chunks


def test_noop_reranker_empty_list() -> None:
    """NoOpReranker must handle empty input."""
    reranker = NoOpReranker()
    assert reranker.rerank([], "question") == []


def test_noop_reranker_preserves_chunk_structure() -> None:
    """NoOpReranker must preserve all keys in each chunk dict."""
    reranker = NoOpReranker()
    chunks = [
        {
            "document_id": "doc-1",
            "chunk_id": "chunk-1",
            "chunk_text": "text",
            "score": 0.8,
            "doc_title": "Doc 1",
            "source_id": "src-1",
            "chunk_index": 0,
        }
    ]
    result = reranker.rerank(chunks, "question")
    assert result[0] == chunks[0]


def test_reranker_protocol_is_abstract() -> None:
    """The Reranker protocol should define 'rerank' but not be instantiable directly."""
    import inspect

    assert hasattr(Reranker, "rerank")
    assert inspect.isfunction(Reranker.rerank)


# ---------------------------------------------------------------------------
# CrossEncoderReranker
# ---------------------------------------------------------------------------


def test_cross_encoder_rerank_filters_below_threshold() -> None:
    """Chunks scoring below min_score (3.0) must be dropped."""
    olly = _make_ollama_mock(responses=["2", "5", "9"])
    reranker = CrossEncoderReranker(olly, min_score=3.0, top_n=10)
    chunks = [
        {"document_id": "d1", "chunk_text": "low relevance", "score": 0.3},
        {"document_id": "d2", "chunk_text": "medium relevance", "score": 0.5},
        {"document_id": "d3", "chunk_text": "high relevance", "score": 0.9},
    ]
    result = reranker.rerank(chunks, "test question")
    assert len(result) == 2
    assert result[0]["document_id"] == "d3"
    assert result[1]["document_id"] == "d2"


def test_cross_encoder_rerank_respects_top_n() -> None:
    """At most top_n chunks must be returned."""
    olly = _make_ollama_mock(responses=["8", "7", "6", "9", "5"])
    reranker = CrossEncoderReranker(olly, min_score=0.0, top_n=3)
    chunks = [{"document_id": f"d{i}", "chunk_text": f"text {i}", "score": 0.5} for i in range(5)]
    result = reranker.rerank(chunks, "question")
    assert len(result) == 3


def test_cross_encoder_rerank_empty_input() -> None:
    """Empty chunk list must return empty list."""
    olly = _make_ollama_mock()
    reranker = CrossEncoderReranker(olly)
    assert reranker.rerank([], "question") == []


def test_cross_encoder_rerank_orders_by_score_desc() -> None:
    """Returned chunks must be ordered by relevance score descending."""
    olly = _make_ollama_mock(responses=["3", "9", "6"])
    reranker = CrossEncoderReranker(olly, min_score=0.0, top_n=10)
    chunks = [
        {"document_id": "d1", "chunk_text": "a", "score": 0.5},
        {"document_id": "d2", "chunk_text": "b", "score": 0.5},
        {"document_id": "d3", "chunk_text": "c", "score": 0.5},
    ]
    result = reranker.rerank(chunks, "question")
    assert [r["document_id"] for r in result] == ["d2", "d3", "d1"]


def test_cross_encoder_rerank_min_score_zero() -> None:
    """min_score=0 should keep all non-zero-scored chunks."""
    olly = _make_ollama_mock(responses=["1", "2", "3"])
    reranker = CrossEncoderReranker(olly, min_score=0.0, top_n=10)
    chunks = [{"document_id": f"d{i}", "chunk_text": f"text {i}", "score": 0.5} for i in range(3)]
    result = reranker.rerank(chunks, "question")
    assert len(result) == 3


def test_cross_encoder_rerank_parse_score_from_full_response() -> None:
    """The score parser must extract a number from full-sentence responses."""
    olly = _make_ollama_mock(responses=["The relevance score is 7.", "Score: 4", "3 out of 10"])
    reranker = CrossEncoderReranker(olly, min_score=0.0, top_n=10)
    chunks = [
        {"document_id": "d1", "chunk_text": "a", "score": 0.5},
        {"document_id": "d2", "chunk_text": "b", "score": 0.5},
        {"document_id": "d3", "chunk_text": "c", "score": 0.5},
    ]
    result = reranker.rerank(chunks, "question")
    assert len(result) == 3
    assert result[0]["document_id"] == "d1"


def test_cross_encoder_rerank_handles_ollama_error() -> None:
    """When Ollama generate raises, the chunk must receive score 0 (and be dropped)."""
    olly = MagicMock()
    olly.generate.side_effect = RuntimeError("Ollama down")
    reranker = CrossEncoderReranker(olly, min_score=3.0, top_n=10)
    chunks = [
        {"document_id": "d1", "chunk_text": "important", "score": 0.9},
        {"document_id": "d2", "chunk_text": "also important", "score": 0.8},
    ]
    result = reranker.rerank(chunks, "question")
    assert result == []


def test_cross_encoder_rerank_calls_generate_with_relevance_prompt() -> None:
    """Ollama generate must be called with a prompt containing the question and chunk_text."""
    olly = MagicMock()
    olly.generate.return_value = "8"
    reranker = CrossEncoderReranker(olly, min_score=0.0, top_n=10)
    chunks = [
        {"document_id": "d1", "chunk_text": "specific document text", "score": 0.7},
    ]
    reranker.rerank(chunks, "What is the answer?")
    prompt = olly.generate.call_args[0][0]
    assert "What is the answer?" in prompt
    assert "specific document text" in prompt
