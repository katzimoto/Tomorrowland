# Phase 03a: Extraction And Persistence

## Goal

Read files from disk and persist their metadata plus extracted text in Postgres.

## Scope

- Text extraction abstraction with a registry pattern.
- Extractors for plain text, PDF, and DOCX.
- Document repository CRUD with status lifecycle.
- SHA256 deduplication via `ingested_files`.

## Implementation Notes

- The extractor registry maps MIME types to extractor instances.
- `extract_text(path, mime_type)` returns `""` for unsupported types; it never
  raises. Callers decide whether an empty result is acceptable.
- Document creation sets `status = "pending"`.
- The `ingested_files` table prevents re-processing the same file by SHA256.
- Extraction is synchronous and runs in the fast worker process.

## Validation

- Unit tests for every extractor (plain, PDF, DOCX).
- Unit tests for unsupported-type fallback.
- Unit tests for document repository CRUD and status transitions.

## Acceptance Criteria

- Pointing a file path at the system creates a `Document` row with extracted text.
- Re-ingesting the same file (same SHA256) is a no-op.
- Unsupported MIME types yield empty text without crashing.
- All extractors are tested with real fixture files.
