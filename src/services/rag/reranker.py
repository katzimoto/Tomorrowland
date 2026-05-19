"""Reranker protocol and implementations for RAG."""

from __future__ import annotations

from typing import Any, Protocol


class Reranker(Protocol):
    """Protocol for reranking retrieved chunks before context assembly.

    Implementations must accept the list of chunk dicts returned by
    ``_retrieve_chunks()`` and the original question, and return a
    re-ordered (and optionally filtered) list of chunk dicts.
    """

    def rerank(self, chunks: list[dict[str, Any]], question: str) -> list[dict[str, Any]]:
        """Rerank *chunks* given the *question*.

        The returned list may be a subset of the input (e.g. top-N after
        cross-encoder scoring).
        """
        ...


class NoOpReranker:
    """Pass-through reranker that returns chunks unchanged."""

    def rerank(self, chunks: list[dict[str, Any]], question: str) -> list[dict[str, Any]]:
        return chunks
