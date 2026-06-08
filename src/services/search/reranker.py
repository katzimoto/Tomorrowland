"""Search reranker for post-retrieval relevance scoring.

Integrates BGE Reranker (and other cross-encoder models) into the hybrid
search pipeline.  Two backends are supported:

* **Endpoint** (primary) – a dedicated TEI-compatible ``/rerank`` HTTP endpoint
  serving a cross-encoder model such as ``BAAI/bge-reranker-v2-m3``.
* **LLM / Ollama** (fallback) – prompt-based relevance scoring through the
  existing Ollama generation path (cheaper to trial, lower quality at scale).
"""

from __future__ import annotations

import logging
import re
from typing import Any, Protocol

import httpx

from services.search.models import SearchResult

logger = logging.getLogger(__name__)

# Chunk text sent to the reranker is truncated to this length to avoid
# blowing up request payloads and to respect cross-encoder token limits.
_CHUNK_TEXT_MAX_CHARS = 2000


class SearchReranker(Protocol):
    """Protocol for reranking search results before they are returned to the user.

    Implementations re-score the given results against the original query and
    return a re-ordered (and optionally filtered) list.
    """

    def rerank(self, query: str, results: list[SearchResult]) -> list[SearchResult]:
        """Rerank *results* against *query*.

        The returned list may be a subset of the input (e.g. top-N after
        cross-encoder scoring).  Order is from most- to least-relevant.
        """
        ...


class NoOpSearchReranker:
    """Pass-through reranker that returns results unchanged."""

    def rerank(self, query: str, results: list[SearchResult]) -> list[SearchResult]:
        return results


class EndpointSearchReranker:
    """Calls a dedicated cross-encoder ``/rerank`` HTTP endpoint.

    The endpoint is expected to follow the TEI (Text Embeddings Inference)
    cross-encoder API format:

      POST /rerank
      {"query": "<question>", "texts": ["<chunk1>", "<chunk2>", ...]}
      → {"scores": [0.8, 0.3, ...]}

    Falls back to returning results unchanged on any error so that reranker
    failures never degrade the search experience.
    """

    def __init__(
        self,
        url: str,
        model: str = "BAAI/bge-reranker-v2-m3",
        min_score: float = 0.0,
        top_n: int = 20,
        timeout: float = 10.0,
    ) -> None:
        self._url = url.rstrip("/")
        self._model = model
        self._min_score = min_score
        self._top_n = top_n
        self._timeout = timeout

    def rerank(self, query: str, results: list[SearchResult]) -> list[SearchResult]:
        if not results:
            return results

        # Gather chunk texts for the request, truncating to avoid OOM.
        texts: list[str] = [(r.chunk_text or "")[:_CHUNK_TEXT_MAX_CHARS] for r in results]

        payload: dict[str, Any] = {
            "query": query,
            "texts": texts,
        }
        # Some deployments (TEI, Infinity) accept an optional model override.
        if self._model:
            payload["model"] = self._model

        try:
            response = httpx.post(
                self._url,
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()
            scores: list[float] | None = data.get("scores")
            if scores is None or len(scores) != len(results):
                logger.warning(
                    "EndpointSearchReranker: expected %d scores, got %d",
                    len(results),
                    len(scores) if scores is not None else 0,
                )
                return results
        except Exception:
            logger.warning(
                "EndpointSearchReranker request failed",
                exc_info=True,
            )
            return results

        # Pair scores with results, sort descending, apply top_n and min_score.
        scored: list[tuple[float, SearchResult]] = list(zip(scores, results, strict=True))
        scored.sort(key=lambda pair: (-pair[0], pair[1].document_id))

        reranked: list[SearchResult] = []
        for score, result in scored:
            if score < self._min_score:
                continue
            reranked.append(
                SearchResult(
                    document_id=result.document_id,
                    score=score,  # Replace original score with reranker score
                    title=result.title,
                    chunk_text=result.chunk_text,
                    metadata=result.metadata,
                )
            )
            if len(reranked) >= self._top_n:
                break

        return reranked


class LLMSearchReranker:
    """Prompt-based reranker using the Ollama generation path.

    Each chunk is scored independently via a relevance prompt.  This is a
    lightweight approximation of a true cross-encoder — useful for trialling
    reranking before deploying a dedicated endpoint, but lower quality at
    scale.

    Requires an object that satisfies the ``LLMProvider`` protocol (the
    same one used by the RAG reranker).
    """

    _PROMPT = (
        "On a scale of 0 to 10, how relevant is the following document "
        "excerpt to the search query? "
        "Respond with only a number between 0 and 10.\n\n"
        "Search query: {query}\n\n"
        "Excerpt: {chunk_text}\n\n"
        "Relevance score:"
    )

    def __init__(
        self,
        llm_provider: Any,
        min_score: float = 3.0,
        top_n: int = 20,
        model: str | None = None,
    ) -> None:
        self._llm = llm_provider
        self._min_score = min_score
        self._top_n = top_n
        self._model = model

    @staticmethod
    def _parse_score(text: str) -> float:
        """Extract a numeric score (0-10) from the LLM response, normalising to 0-1."""
        match = re.search(r"\d+\.?\d*", text.strip())
        if match:
            try:
                raw = float(match.group())
                return min(1.0, max(0.0, raw / 10.0))
            except ValueError:
                pass
        return 0.0

    def rerank(self, query: str, results: list[SearchResult]) -> list[SearchResult]:
        if not results:
            return results

        scored: list[tuple[float, SearchResult]] = []
        for result in results:
            prompt = self._PROMPT.format(
                query=query,
                chunk_text=(result.chunk_text or "")[:_CHUNK_TEXT_MAX_CHARS],
            )
            try:
                response = self._llm.generate(prompt, model=self._model)
                score = self._parse_score(response)
            except Exception:
                logger.warning(
                    "LLMSearchReranker: scoring failed for document_id=%s",
                    result.document_id,
                    exc_info=True,
                )
                score = 0.0
            scored.append((score, result))

        scored.sort(key=lambda pair: (-pair[0], pair[1].document_id))

        reranked: list[SearchResult] = []
        for score, result in scored:
            if score < self._min_score:
                continue
            reranked.append(
                SearchResult(
                    document_id=result.document_id,
                    score=score,
                    title=result.title,
                    chunk_text=result.chunk_text,
                    metadata=result.metadata,
                )
            )
            if len(reranked) >= self._top_n:
                break

        return reranked
