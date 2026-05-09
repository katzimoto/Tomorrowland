# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Phase 08b: Frontend foundation — React 19 + TypeScript + Vite scaffold with
  TanStack Router and Query, React Hook Form + Zod auth form, design-token CSS
  system, primitive component library (Button, IconButton, TextInput,
  SearchInput, Badge, Tabs, Dialog, Skeleton, EmptyState, Toast), AppShell with
  responsive NavRail, API client with 401 session-expiry handling, auth token
  storage boundary, Login page, Playwright config at four viewports, Vitest +
  Testing Library unit tests (18 tests), and multi-stage frontend Dockerfile
  building the React app.
- Phase 08a: Compose runtime foundation — backend ASGI entrypoint, public health
  endpoint, production-oriented API and frontend containers, migration service,
  Compose runtime wiring, and local production operations guide.
- Phase 07e: Related documents and expertise map — backend endpoints for permission-filtered related document surfacing and neutral expertise evidence using Qdrant chunks plus views, comments, shared annotations, and subscriptions.
- Phase 07d: Subscriptions and notifications — `alert_subscriptions` and `alert_notifications` tables, subscription CRUD endpoints, unread notification listing and read marking, `AlertMatcher` with source-permission filtering, ingest-time matching, admin alert trigger, feature flag enforcement, and integration tests.
- Phase 07c: RAG Q&A — `RagService` retrieves chunks from Qdrant, assembles context, calls Ollama, returns answer + citations; `POST /qa` endpoint with `question` and `top_k`; `feature.rag_qa` enforcement; source-grant-aligned ES/Qdrant indexing; best-effort fallback on Ollama failure; mocked Qdrant tests.
- Phase 07b: Annotations — `annotations` table, `AnnotationRepository`, `GET|POST /documents/{doc_id}/annotations`, `PUT|DELETE /annotations/{annotation_id}`, private/shared visibility filtering, hard delete with creator/admin permission checks, JSON position support.
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
- Phase 08: Productization, UI, and production Compose.
- Phase 09: Optional integrations and legacy format support, including NiFi,
  Atlassian, old Office extraction, and nonessential Kafka consumer wiring.
