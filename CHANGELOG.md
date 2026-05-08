# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Phase 07a: Document comments — `document_comments` table, `CommentRepository`, `GET|POST|PATCH|DELETE /documents/{doc_id}/comments`, soft-delete with creator/admin permission checks, pagination and sorting, `feature.document_comments` flag.
- Phase 06: Intelligence layer — `document_summaries`, `entities`, `document_entities`, `document_tags` tables, `IntelligenceWorker` with mocked Ollama client, summarize/extract_entities/auto_tag tasks, `GET /documents/{doc_id}/summary`, `/entities`, `/tags`, `POST /admin/intelligence/{doc_id}/trigger`, wired into `PipelineWorker` after indexing, best-effort failure behavior.
- Phase 05c: Translation versions — `document_translation_versions` table, `GET /documents/{doc_id}/translation-versions`, versioned preview with `?translation_version_id=`, `POST /documents/{doc_id}/translate` creates version records, `SlowWorker` processes pending versions, auto-enrich creates `auto_enrich` version.
- Phase 05b: Translation enrichment — manual request `POST /documents/{doc_id}/translate`, auto-enrich threshold via `document_views` count, `SlowWorker` re-translation/re-indexing, `GET /admin/enrichment-queue`.
- Phase 05a: Preview service — truncated MIME-type-aware snippets, HTML sanitization, archive filename listing, per-user view tracking via `document_views`, `GET /me/activity`.
- Phase 04: Admin operations — users, groups, sources, permissions, config, DLQ retry, activity audit.
- Phase 03e: Search, preview, and download APIs with permission filtering and path-traversal guards.
- Phase 03d: Worker pipeline — synchronous ingestion with extraction, translation, chunking, embedding, indexing.
- Phase 03c: Search infrastructure — Elasticsearch + Qdrant clients, mock encoder, hybrid merger.
- Phase 03b: LibreTranslate client with fallback and token-based chunking (sentence-aware).
- Phase 03a: Document persistence and text extraction (15 file types).
- Phase 02: Authentication, JWT, LDAP boundary, and permission enforcement.
- Phase 01: Foundation schema, shared contracts, service skeletons, and tests.
- Phase 00: Planning, repository hygiene, and GitHub Actions bootstrap.

### Planned
- Phase 07b–07e: Annotations, RAG Q&A, subscriptions/notifications, related documents + expertise map.
- Phase 08: External integrations (NiFi, Confluence, Jira), old Office extraction, observability.
