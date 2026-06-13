"""Reranker protocol and implementations for RAG."""

from __future__ import annotations

import logging
import re
from typing import Any, Protocol

import httpx

from services.intelligence.llm_provider import LLMProvider

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


class CrossEncoderEndpointReranker:
    """Dedicated cross-encoder reranker that calls an external HTTP endpoint.

    Post ``{"query": <question>, "texts": [<chunk_texts>]}`` to the configured
    endpoint and expects ``{"scores": [<float>, ...]}`` back.  This matches the
    TEI (Text Embeddings Inference) cross-encoder API format used by Hugging
    Face TEI, Infinity, and similar serving stacks.

    Falls back to identity (returns chunks unchanged) on any error so the
    RAG pipeline is never blocked by a reranker failure.

    Only active when ``rerank_url`` is set; otherwise ``NoOpReranker`` is used.
    """

    def __init__(
        self,
        rerank_url: str,
        model: str | None = None,
        api_key: str | None = None,
        min_score: float = 0.0,
        top_n: int = 8,
        timeout: float = 30.0,
    ) -> None:
        self._url = rerank_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._min_score = min_score
        self._top_n = top_n
        self._timeout = timeout

    def rerank(self, chunks: list[dict[str, Any]], question: str) -> list[dict[str, Any]]:
        if not chunks:
            return chunks

        texts = [(chunk.get("chunk_text", "") or "")[:2000] for chunk in chunks]
        payload: dict[str, Any] = {"query": question, "texts": texts}
        if self._model:
            payload["model"] = self._model

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            response = httpx.post(
                self._url,
                json=payload,
                headers=headers,
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()
            scores: list[float] | None = data.get("scores")
            if scores is None or len(scores) != len(chunks):
                logger.warning(
                    "CrossEncoderEndpointReranker: expected %d scores, got %d",
                    len(chunks),
                    len(scores) if scores is not None else 0,
                )
                return chunks
        except Exception:
            logger.warning("CrossEncoderEndpointReranker request failed", exc_info=True)
            return chunks

        scored: list[tuple[float, dict[str, Any]]] = list(zip(scores, chunks, strict=True))
        scored.sort(key=lambda pair: (-pair[0], pair[1].get("document_id", "")))
        return [
            {**chunk, "_reranker_score": score}
            for score, chunk in scored[: self._top_n]
            if score >= self._min_score
        ]


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
        ollama_client: LLMProvider,
        min_score: float = 3.0,
        top_n: int = 8,
        model: str | None = None,
    ) -> None:
        self._ollama = ollama_client
        self._min_score = min_score
        self._top_n = top_n
        # When set, reranking uses this model instead of the client default.
        # Pass OLLAMA_RERANKER_MODEL (or its effective fallback) here.
        self._model = model

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
                response = self._ollama.generate(prompt, model=self._model)
                score = self._parse_score(response)
            except Exception:
                logger.warning("Reranker scoring failed for a chunk, using 0", exc_info=True)
                score = 0.0
            scored.append((score, chunk))

        scored.sort(key=lambda pair: (-pair[0], pair[1].get("document_id", "")))
        return [
            {**chunk, "_reranker_score": score}
            for score, chunk in scored[: self._top_n]
            if score >= self._min_score
        ]
