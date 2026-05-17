from __future__ import annotations

from typing import Any

from services.search.models import SearchResult

__all__ = ["SearchResult", "merge_results"]


def merge_results(
    bm25_results: list[SearchResult],
    vector_results: list[SearchResult],
    vector_weight: float,
    bm25_weight: float,
) -> list[SearchResult]:
    """Merge BM25 and vector search results into a single ranked list.

    The merge process:
    1. Deduplicates by *document_id*.
    2. Combines scores using the formula:
       ``combined = vector_weight * vector_score + bm25_weight * bm25_score``
    3. Sorts by combined score descending, with *document_id* as tie-breaker.

    When a document appears in both result sets, fields from the BM25 result
    take precedence (e.g. *title*, *metadata*).
    """
    scores: dict[str, float] = {}
    fields: dict[str, dict[str, Any]] = {}

    for result in bm25_results:
        scores[result.document_id] = (
            scores.get(result.document_id, 0.0) + bm25_weight * result.score
        )
        fields[result.document_id] = {
            "title": result.title,
            "chunk_text": result.chunk_text,
            "metadata": result.metadata,
        }

    for result in vector_results:
        scores[result.document_id] = (
            scores.get(result.document_id, 0.0) + vector_weight * result.score
        )
        # Only set fields if not already present from BM25
        if result.document_id not in fields:
            fields[result.document_id] = {
                "title": result.title,
                "chunk_text": result.chunk_text,
                "metadata": result.metadata,
            }

    merged: list[SearchResult] = []
    for document_id, total_score in scores.items():
        info = fields[document_id]
        merged.append(
            SearchResult(
                document_id=document_id,
                score=total_score,
                title=info.get("title"),
                chunk_text=info.get("chunk_text"),
                metadata=info.get("metadata"),
            )
        )

    # Sort by score descending, then document_id ascending for tie-breaking
    merged.sort(key=lambda r: (-r.score, r.document_id))
    return merged
