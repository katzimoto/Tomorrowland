# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
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
- Phase 05b: Translation enrichment — manual request, auto-enrich threshold, slow worker reindex.
- Phase 06: Intelligence layer — Ollama integration, summarization, entity extraction, auto-tagging.
- Phase 07: RAG Q&A, annotations, subscriptions, notifications, related documents, expertise map.
- Phase 08: External integrations (NiFi, Confluence, Jira), old Office extraction, observability.
