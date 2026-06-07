# Phase 03: Core Search MVP

## Goal

Deliver a working permission-filtered search system for ingested documents.

## Scope

This phase is split into five reviewable sub-phases.

- **03a** — Document persistence and text extraction.
- **03b** — Translation and chunking.
- **03c** — Search infrastructure (Elasticsearch + Qdrant) with mock embeddings.
- **03d** — Fast worker pipeline and admin ingestion trigger.
- **03e** — Search, preview, and download APIs.

## Decision Gates

- Chunk text is stored in the **Qdrant point payload** as the primary retrievable
  source for RAG citations. A Postgres `chunks` table is deferred to Phase 06.
- Delete cascade uses the Postgres `documents` table as the source of truth.
  Deletion is soft-delete (`status = 'deleted'`). Hard deletion is deferred to
  Phase 04.
- Translation state machine:
  - `null`  → `"fast"` (fast worker success)
  - `null`  stays `null` (fast worker failure)
  - `"fast"` → `"high"` (slow worker success)

## Validation

- Each sub-phase has its own unit and integration tests.
- End-to-end: ingest a fixture document, index it, search it, preview it, and
  download it.
- Permission-filtered search tests.
- Translation failure fallback tests.

## Implementation Notes

- Phase 03 introduces the real ingestion, search, preview, and download code,
  but it does not require Docker Compose to run the API and workers as
  containers. Full no-mock Compose deployment is deferred to Phase 08.

## Acceptance Criteria

- A user can find only documents their groups allow.
- Indexed documents include enough metadata for search results and previews.
- Translation failure still leaves the document searchable with fallback state.
- All five sub-phases pass lint, type check, and 90 % coverage.

## Sub-Phase Index

| Sub-Phase | Document |
|---|---|
| 03a | [phase-03a-extraction-persistence.md](phase-03a-extraction-persistence.md) |
| 03b | [phase-03b-translation-chunking.md](phase-03b-translation-chunking.md) |
| 03c | [phase-03c-search-infrastructure.md](phase-03c-search-infrastructure.md) |
| 03d | [phase-03d-worker-pipeline.md](phase-03d-worker-pipeline.md) |
| 03e | [phase-03e-search-apis.md](phase-03e-search-apis.md) |
