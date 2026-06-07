# Phase 03d: Worker Pipeline

## Goal

Wire extraction, translation, chunking, embedding, and indexing into a single
callable pipeline, exposed via an admin API.

## Scope

- Fast worker `process_document(documant_id)` pipeline.
- `POST /admin/ingestion/{source_id}/sync-now` endpoint (admin-only,
  synchronous for MVP).
- Folder scanning, document creation, and pipeline invocation.

## Implementation Notes

- The pipeline runs synchronously in the API request for Phase 03 MVP.
  Background workers are deferred to a later phase.
- Pipeline steps in order:
  1. Load the document row from Postgres.
  2. Extract text via the extraction registry.
  3. Translate via the LibreTranslate client (fallback to original).
  4. Chunk via the token splitter.
  5. Encode chunks with the mock encoder.
  6. Index the full document in the search index (originally Elasticsearch, now Meilisearch).
  7. Index chunks in Qdrant.
  8. Update the document row: `status = "indexed"` and set
     `translation_quality`.
- SHA256 deduplication skips files already present in `ingested_files`.
- Any unhandled exception sets `status = "failed"` and logs with the
  correlation ID.

## Validation

- Integration test: drop a fixture file, call sync-now, assert the document
  row has `status = "indexed"`.
- Integration test: assert the search index (Meilisearch) contains the document and Qdrant
  contains its chunks.
- Integration test: mock LibreTranslate failure and assert the document is
  still indexed with `translation_quality = null`.
- Integration test: ingest the same file twice and assert the second call is
  a no-op.

## Acceptance Criteria

- Calling the admin sync endpoint indexes every file in a folder source.
- Duplicate files are skipped.
- Translation failures do not block indexing.
- The pipeline updates the document status correctly.
