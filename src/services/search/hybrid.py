from __future__ import annotations

from typing import Any

from services.search.models import SearchResult

__all__ = ["RRF_K", "SearchResult", "merge_results"]

# Default Reciprocal Rank Fusion constant.  ``k`` dampens the influence of high
# ranks: a larger ``k`` flattens the contribution curve so that being #1 vs #2
# matters less.  60 is the value from the original RRF paper (Cormack et al.,
# 2009) and the de-facto default across hybrid-search systems.
RRF_K = 60


def merge_results(
    bm25_results: list[SearchResult],
    vector_results: list[SearchResult],
    vector_weight: float,
    bm25_weight: float,
    *,
    k: int = RRF_K,
) -> list[SearchResult]:
    """Merge BM25 and vector search results using weighted Reciprocal Rank Fusion.

    Backend scores from Meilisearch (lexical/BM25) and Qdrant (vector/cosine)
    live on different, uncalibrated scales, so adding them directly lets one
    backend dominate by accident of scale.  Instead we fuse by **rank**:

        ``fused = bm25_weight / (k + rank_bm25) + vector_weight / (k + rank_vector)``

    where each ``rank`` is the candidate's 1-based position in that backend's
    own ordered result list.  Rank-based fusion is scale-invariant: a candidate
    ranked #1 by BM25 always contributes ``bm25_weight / (k + 1)`` regardless of
    the raw lexical score, and a candidate appearing in *both* backends is
    boosted by the sum of both contributions.

    The merge process:

    1. Deduplicates by *chunk_id* (from ``result.metadata["chunk_id"]``) when
       available, falling back to *document_id* for document-level BM25 results
       that carry no chunk identity.  This preserves all chunks from
       multi-chunk documents instead of collapsing them to one per document.
    2. Accumulates the weighted RRF score per merge key across both backends.
    3. Sorts deterministically by ``(-fused_score, best_individual_rank,
       document_id, chunk_index, chunk_id)`` so ties resolve stably.

    The returned ``SearchResult.score`` carries the **fused RRF score** (a small
    positive number, not a backend-native relevance score).  When a chunk
    appears in both result sets, fields from the BM25 result take precedence
    (e.g. *title*, *metadata*).

    Callers can fuse more than two lanes by chaining: the previously-fused list
    (already rank-ordered) is passed in as ``vector_results`` for the next
    merge, which re-fuses by its position in that list.
    """
    fused: dict[str, float] = {}
    best_rank: dict[str, int] = {}
    fields: dict[str, dict[str, Any]] = {}

    def _merge_key(result: SearchResult) -> str:
        chunk_id = (result.metadata or {}).get("chunk_id")
        return str(chunk_id) if chunk_id else result.document_id

    def _accumulate(
        results: list[SearchResult],
        weight: float,
        *,
        overwrite_fields: bool,
    ) -> None:
        for rank, result in enumerate(results, start=1):
            key = _merge_key(result)
            fused[key] = fused.get(key, 0.0) + weight / (k + rank)
            if key not in best_rank or rank < best_rank[key]:
                best_rank[key] = rank
            if overwrite_fields or key not in fields:
                fields[key] = {
                    "document_id": result.document_id,
                    "title": result.title,
                    "chunk_text": result.chunk_text,
                    "metadata": result.metadata,
                }

    # BM25 first so its fields win on cross-backend duplicates.
    _accumulate(bm25_results, bm25_weight, overwrite_fields=True)
    _accumulate(vector_results, vector_weight, overwrite_fields=False)

    def _tie_key(key: str) -> tuple[float, int, str, int, str]:
        info = fields[key]
        metadata = info.get("metadata") or {}
        raw_index = metadata.get("chunk_index")
        chunk_index = raw_index if isinstance(raw_index, int) else -1
        chunk_id = str(metadata.get("chunk_id") or "")
        # Higher fused score first; then the best (lowest) individual rank; then
        # a stable identity key (document_id, chunk_index, chunk_id).
        return (-fused[key], best_rank[key], info["document_id"], chunk_index, chunk_id)

    merged: list[SearchResult] = []
    for key in sorted(fused, key=_tie_key):
        info = fields[key]
        merged.append(
            SearchResult(
                document_id=info["document_id"],
                score=fused[key],
                title=info.get("title"),
                chunk_text=info.get("chunk_text"),
                metadata=info.get("metadata"),
            )
        )
    return merged
