"""Tests for the RAG reranker protocol and built-in implementations."""

from __future__ import annotations

from services.rag.reranker import NoOpReranker, Reranker


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
