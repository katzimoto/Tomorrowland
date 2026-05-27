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
    1. Deduplicates by *chunk_id* (from ``result.metadata["chunk_id"]``) when
       available, falling back to *document_id* for document-level BM25 results
       that carry no chunk identity.  This preserves all chunks from
       multi-chunk documents instead of collapsing them to one per document.
    2. Combines scores using the formula:
       ``combined = vector_weight * vector_score + bm25_weight * bm25_score``
    3. Sorts by combined score descending, with *document_id* as tie-breaker.

    When a chunk appears in both result sets, fields from the BM25 result
    take precedence (e.g. *title*, *metadata*).
    """
    scores: dict[str, float] = {}
    fields: dict[str, dict[str, Any]] = {}

    def _merge_key(result: SearchResult) -> str:
        chunk_id = (result.metadata or {}).get("chunk_id")
        return str(chunk_id) if chunk_id else result.document_id

    for result in bm25_results:
        key = _merge_key(result)
        scores[key] = scores.get(key, 0.0) + bm25_weight * result.score
        fields[key] = {
            "document_id": result.document_id,
            "title": result.title,
            "chunk_text": result.chunk_text,
            "metadata": result.metadata,
        }

    for result in vector_results:
        key = _merge_key(result)
        scores[key] = scores.get(key, 0.0) + vector_weight * result.score
        # Only set fields if not already present from BM25
        if key not in fields:
            fields[key] = {
                "document_id": result.document_id,
                "title": result.title,
                "chunk_text": result.chunk_text,
                "metadata": result.metadata,
            }

    merged: list[SearchResult] = []
    for _key, total_score in scores.items():
        info = fields[_key]
        merged.append(
            SearchResult(
                document_id=info["document_id"],
                score=total_score,
                title=info.get("title"),
                chunk_text=info.get("chunk_text"),
                metadata=info.get("metadata"),
            )
        )

    # Sort by score descending, then document_id ascending for tie-breaking
    merged.sort(key=lambda r: (-r.score, r.document_id))
    return merged
