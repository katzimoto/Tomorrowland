"""Reranker protocol and implementations for RAG."""

from __future__ import annotations

import logging
import re
from typing import Any, Protocol

from services.intelligence.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

RELEVANCE_PROMPT = """\
On a scale of 0 to 10, how relevant is the following document excerpt to the question?
Respond with only a number between 0 and 10.

Question: {question}

Excerpt: {chunk_text}

Relevance score:"""


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


class CrossEncoderReranker:
    """LLM-based reranker that scores each chunk's relevance via an Ollama model.

    Each chunk is scored independently with a relevance prompt. Chunks with
    a score below the threshold are dropped; the remainder are re-sorted by
    score descending.

    This is a prompt‑based approximation of a cross‑encoder. For production
    use, replace with a dedicated cross‑encoder model (e.g. ``cross-encoder/
    ms-marco-MiniLM-L-6-v2``) served alongside Ollama.
    """

    def __init__(
        self,
        ollama_client: OllamaClient,
        min_score: float = 3.0,
        top_n: int = 8,
    ) -> None:
        self._ollama = ollama_client
        self._min_score = min_score
        self._top_n = top_n

    @staticmethod
    def _parse_score(text: str) -> float:
        match = re.search(r"\d+\.?\d*", text.strip())
        if match:
            try:
                return float(match.group())
            except ValueError:
                pass
        return 0.0

    def rerank(self, chunks: list[dict[str, Any]], question: str) -> list[dict[str, Any]]:
        if not chunks:
            return chunks

        scored: list[tuple[float, dict[str, Any]]] = []
        for chunk in chunks:
            prompt = RELEVANCE_PROMPT.format(
                question=question,
                chunk_text=chunk.get("chunk_text", "")[:2000],
            )
            try:
                response = self._ollama.generate(prompt)
                score = self._parse_score(response)
            except Exception:
                logger.warning("Reranker scoring failed for a chunk, using 0", exc_info=True)
                score = 0.0
            scored.append((score, chunk))

        scored.sort(key=lambda pair: (-pair[0], pair[1].get("document_id", "")))
        return [chunk for score, chunk in scored[: self._top_n] if score >= self._min_score]
