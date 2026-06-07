# Phase 03c: Search Infrastructure

> **Note (June 2026):** This phase plan predates the Elasticsearch→Meilisearch
> migration (PR #573, 2026-05-30). The current implementation uses Meilisearch
> instead of Elasticsearch for BM25/full-text search. This document is retained
> as a historical phase plan.

## Goal

Create and manage the search index (originally Elasticsearch, now Meilisearch)
and Qdrant collection, with a mock embedding encoder.

## Scope

- Search client and document index mapping (now Meilisearch).
- Qdrant client and chunk collection creation.
- Mock embedding encoder (384-dim, deterministic, zero dependencies).
- Hybrid score merger for BM25 + vector results.

## Implementation Notes

- **MockEncoder** produces deterministic 384-dimensional vectors derived from
  the hash of the input text. This keeps CI fast and removes the torch
  dependency until Phase 06.
- **Search index** (now Meilisearch) indexes the full document (`content_english`, `title`,
  `summary`, `tags`, `metadata`, `allowed_group_ids`).
- **Qdrant** stores one point per chunk. Payload fields: `documant_id`, `group_id`,
  `chunk_index`, `text`.
- **Hybrid merge** retrieves the top 50 results from each backend, deduplicates
  by `documant_id`, and scores with `vector_weight * vector_score +
  bm25_weight * bm25_score`. Weights are read from `system_config`.

## Validation

- Unit tests for mock encoder shape and determinism.
- Unit tests for search index/search with a mocked client.
- Unit tests for Qdrant index/search with a mocked client.
- Unit tests for hybrid merge logic (score math, deduplication, tie-breaking).

## Acceptance Criteria

- A document and its chunks can be indexed manually and retrieved by hybrid
  search.
- Search results respect the configured BM25 / vector weight ratio.
- No external model is downloaded during tests or CI.
