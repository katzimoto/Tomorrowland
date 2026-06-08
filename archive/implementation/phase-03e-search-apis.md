# Phase 03e: Search, Preview And Download APIs

## Goal

Expose user-facing endpoints for permission-filtered search, document preview,
and file download.

## Scope

- `POST /search` — hybrid BM25 + vector search with permission filtering.
- `GET /preview/{documant_id}` — returns content, metadata, and translation state.
- `GET /download/{documant_id}` — raw file bytes with correct content type.
- Permission enforcement on every endpoint.

## Implementation Notes

- **Search** filters documents by source permissions. The query joins
  `documents -> ingestion_sources -> source_permissions` and restricts
  `source_permissions.group_id` to the user's groups.
- **Preview** returns the stored `content_english`, `title`, `mime_type`,
  `translation_quality`, and `metadata`.
- **Download** streams the original file from `FILES_ROOT / path` with a
  path-traversal guard (resolved path must stay inside `FILES_ROOT`).
- All three endpoints return `401` for missing tokens, `403` for unauthorized
  documents, and `404` for missing documents.

## Validation

- Integration test: search returns matching documents for an authorized user.
- Integration test: search excludes documents from unauthorized sources.
- Integration test: pagination works (`page`, `page_size`).
- Integration test: preview returns content for an authorized doc and `403`
  for an unauthorized doc.
- Integration test: download returns bytes for an authorized doc and `403`
  for an unauthorized doc.
- Integration test: path traversal is blocked.
- Integration test: a document with `translation_quality = null` still appears
  in search results.

## Acceptance Criteria

- An authenticated user can search, preview, and download only documents whose
  source is granted to one of their groups.
- Search uses hybrid scoring with weights from `system_config`.
- Download serves the original file with correct `Content-Type` and
  `Content-Disposition`.
- All endpoints have integration tests covering success, auth failure,
  permission denial, and not-found cases.
