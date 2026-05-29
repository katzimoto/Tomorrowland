# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed
- Issue #551: ACL audit HIGH findings regression tests. Added integration tests covering H1 (admin search bypass — ES receives `is_admin=True`, Qdrant receives `allow_all=True`), H2 (expertise admin bypass — `allow_all=True` forwarded to Qdrant), H3 (orphaned Qdrant vectors silently dropped from search results), H4 (subscription user-discovery leak — outsider excluded when no group overlap with requester), and H5 (related-docs transitive group expansion — child-group users reach parent-group sources via `get_effective_group_ids`). Also fixed two existing `RelatedService` test instantiations missing the required `job_repo` argument.

### Added
- Issue #552: Source-scoped RAG/hybrid BM25 retrieval now enforces source identity via `metadata.source_id` in Meilisearch payloads. Meilisearch settings version bumped to 2 — operators must run Meilisearch backfill/reindex after deploy.
  - Added `source_id` field to `ChunkMetadata` Pydantic model.
  - Added `metadata.source_id` to Meilisearch filterable and displayed attributes.
  - Populated `source_id` in all indexing sites (backfill, worker, slow_worker, index_worker).
  - `search_rag`, `search_rag_metadata`, and `search_rag_translated` accept `source_ids` parameter and apply a `metadata.source_id IN [...]` filter.
  - `_apply_scope_to_bm25` post-filters out stale records lacking a matching `source_id`.
  - RagService wires source scope (`source_ids`) into all three BM25 search paths.
  - Regression tests cover BM25 source-scoped filtering, missing-source_id exclusion, and Meilisearch settings.
- Issue #541: Document-flow smoke test infrastructure. New `scripts/dev/smoke_document_flow.sh` runs 10 stages: dependency check, API health, frontend health, Docker-based bootstrap (`services.ops.smoke_bootstrap`), auth login (`POST /auth/login`), ingestion + poll (`POST /admin/ingestion/{id}/sync-now`), search (`POST /search`), preview (`GET /preview/{id}`), text (`GET /documents/{id}/text`), and download (`GET /download/{id}`). Supports `SMOKE_MODE=ci` with hard failures, `SMOKE_DOCUMENT_ID` to bypass search-based doc discovery, and machine-readable JSON result output. All data-dependent stages gracefully skip when prerequisites (Docker, credentials, or document ID) are absent. New `docs/development/local-demo.md` documents the smoke workflow for local demos and CI reuse.
- Issue #528: LLM generation provider abstraction — OpenAI-compatible endpoint support. New `LLMProvider` protocol in `src/services/intelligence/llm_provider.py`; `OllamaClient` satisfies it structurally. `OpenAICompatibleLLMProvider` targets `/v1/chat/completions` for LM Studio, llama.cpp HTTP server, and vLLM (no openai SDK dependency). `build_llm_provider()` factory in `src/services/intelligence/factory.py` resolves from `LLM_PROVIDER` env var (`ollama` default, `openai-compatible` alternative); `LLM_BASE_URL` overrides `OLLAMA_URL` and `LLM_MODEL` overrides `OLLAMA_MODEL`. Chat, RAG, and intelligence workers wired through factory instead of direct `OllamaClient` construction.
- Issue #527: Pre-benchmark fixture corpus and extraction/citation/failure-mode assertion improvements. Added fixture files (`sample-with-headings.docx`, `sample-multisheet.xlsx`, `wrong-extension.docx` as misnamed PPTX, `corrupt.pdf`, `encrypted.pdf`). New unit tests in `tests/unit/test_extraction_fixture_corpus.py` cover DOCX heading/table content, PPTX slide titles, XLSX multi-sheet values, EML body+attachment children, MSG subject/sender, scanned-PDF OCR fallback path, corrupt/encrypted/wrong-extension failure modes, and `has_extractor` boundary. New integration test in `tests/integration/test_chunk_index_pipeline.py` verifies every Qdrant point payload carries a non-null integer `chunk_index` after a full pipeline run. Fixed `PdfExtractor` to catch `FileNotDecryptedError` so encrypted PDFs return empty text instead of crashing.
- Issue #526: Markdown-structured Office extraction for improved RAG chunking, enabled by default. Native converters for DOCX (headings, lists, tables), PPTX (slide titles, bullets), and XLSX (sheet headings, cell tables) replace flat plain-text extraction for those MIME types. Each converter falls back to the original extractor on empty output or error. Disable with `ENABLE_MARKITDOWN=false`. Implemented natively with python-docx, python-pptx, and openpyxl — no new dependencies required.

## [0.2.0] - 2026-05-28

### Changed
- Issue #133: Replaced the "N" letter mark with a new dark cyberpunk bicycle logo. The new asset (`frontend/public/tomorrowland-logo-cyber-bike.svg`) features a neon cyan bicycle on a deep navy background with scanline and HUD-bracket accents. Updated the nav rail, login page, and favicon to use the new logo. Added a reusable `TomorrowlandLogo` component at `frontend/src/components/brand/TomorrowlandLogo.tsx`.
- Documentation now reflects that Confluence and Jira Server/Data Center polling
  connectors are implemented; Phase 09 only retains NiFi, legacy Office, Kafka,
  and optional Atlassian hardening follow-ups.

### Added
- ACL hardening D2 — MEDIUM gaps (PR #516, issue #400): `/me/activity` and `/notifications` now filter stale rows after group-access revocation (M1/M4); `/admin/config` masks sensitive config keys — token, secret, password, api_key, private_key, client_secret (M2); `/documents/{id}/versions` enforces per-version ACL for cross-source version families (M3). Admin bypass (`is_admin=True`) preserved in all paths.
- Document details and advanced search track (PR #500, issues #483–#489): expanded document details panel with grouped sections and copy-to-search chip links (#483, #489); advanced search with Meilisearch/Elasticsearch filter pipeline and URL-driven state (#484); document relationship structure visualization in the details panel (#488); clickable detail values that pre-populate the search bar (#489).
- Document Chat (PR #492, phases A–G, issue #471): persistent chat sessions backed by `chat_sessions`/`chat_messages` tables; SSE streaming of Ollama responses; scope model (document/collection) with Qdrant filter alignment; conversation-aware query rewrite using previous turns; hybrid search with reranking for retrieval; citation UX with source cards; starter question generation; a11y polish and full test coverage. Phase A foundation fixes (PR #479) include citation_id threading and React key stability.
- High-fidelity document viewer MVP (PR #466, issues #440–#451): PDF.js multi-page viewer with page navigation and zoom (#442); view mode switcher (Original/Extracted/Translation) and fidelity status bar (#443); image viewer with 25–400% zoom, pan, keyboard controls, and TIFF fallback (#444); metadata Details tab with MIME, file size, language, status, and SHA-256 (#445); syntax-highlighting CodeViewer (JSON/XML/YAML/Python/JS/TS/Bash/SQL) with copy and raw toggle (#447); native MediaPreview for audio/video with byte-range download and error fallback (#448); in-document search with Ctrl+F shortcut, match count, and Prev/Next navigation (#449); a11y, react-window virtualization, and telemetry hardening (#450); test suite consolidation (#451); `GET /documents/{id}/text` full-text API (#441); HTML preview sandbox security fix (#440).
- Document versioning (PR #387, issues #201–#205): `document_version_families` table with `(source_id, external_id)` uniqueness and `current_document_id` pointer; `version_family_id`, `version_number`, `is_latest` added to documents with backfill migration; `GET /documents/{id}/versions` ordered history endpoint; `VersionBadge` in search results and `VersionBanner` on older-version documents with link to latest; "Include older versions" filter checkbox in the search filter panel; full i18n coverage (en/he).
- Admin group management screen (PR #412): `/admin/groups` list with create, rename, and delete dialogs; `DELETE /admin/groups/{id}` and `PATCH /admin/groups/{id}/name` backend endpoints; `/admin` hub page linking Sources and Groups.
- AI surfaces completion — remaining workstreams (PR #418, issue #400): hybrid RAG retrieval fusing Qdrant vector and Meilisearch BM25 via Reciprocal Rank Fusion; `Reranker` protocol with `NoOpReranker` wired between retrieval and assembly; citation deduplication by `(document_id, chunk_index)`; Meilisearch vault integration for knowledge projection; chunker and intelligence projection polish.
- ACL hardening D1/D2 — HIGH-severity fixes (PRs #403–#408, issue #142): D1 audit with full permission matrix and D2 fix checklist (`docs/context/acl-audit.md`) (#406); H1 admin search bypass fix — `is_admin`/`allow_all` now forwarded to Elasticsearch and Qdrant clients (#407); H2 expertise admin bypass fix (#407); H3 orphaned-vector leak in vector search (#407); H4 subscription user-discovery leak — replaced document-overlap gate with group co-membership check (#408); H5 related-docs group expansion fix (#408); expertise signal-details per-signal contribution tracking (C2, #405); stored-text lookup and tag/entity overlap scoring scaffold (C1, #403).
- User-managed document tags (PR #494, issue #486): `user_document_tags` table with private/public visibility and a 20-tag-per-document limit; inline tag editor in the document details panel with private/public toggle.
- Rendered Markdown preview (PR #493, issue #485): `MarkdownPreview` renderer with Rendered/Raw toggle, DOMPurify HTML sanitization, and copy-raw button; dispatched for `text/markdown` and `.md`/`.mdx`/`.markdown` extensions.
- Unified comments and annotation replies (PR #495, issue #487): `annotation_replies` table; all non-deleted comments migrated as document-level annotations (`position=NULL`); soft-delete with `[deleted]` placeholder; `reply_count` on annotation list responses; comments tab removed from InsightPane in favour of unified Annotations tab.
- Issue #63 (Phase 10e): Structured JSON logging and OpenTelemetry no-op hooks. `JsonFormatter` in `src/shared/logging.py` now emits RFC 3339 UTC `timestamp`, lowercase `level`, `request_id` from the Phase 10a context variable, `correlation_id`, and allowlisted structured extras (`component`, `outcome`, `operation_id`). Exception records include `error_type` (class name only — never the message) plus the full `exc_info` traceback. Arbitrary extra fields (passwords, tokens, credentials) are silently dropped by the allowlist. New `src/shared/tracing.py` provides a `start_span` context-manager that creates real OpenTelemetry spans when the package is installed and a provider is configured, and is a complete no-op otherwise. 27 new unit tests in `tests/unit/test_structured_logging.py` cover JSON validity, timestamp format, lowercase level, request_id flow, error_type safety, allowlisted extras, credential-key suppression, monitoring-view queryable fields, and OTel no-op behaviour.
- Issue #84: Frontend perceived performance polish — tuned TanStack Query cache behavior, kept prior search results visible during refetch, added bounded preview prefetch on search-result hover/focus, improved skeleton-based loading in document insight panes, and added optimistic rollback flows for comments, annotations, subscriptions, and notification mark-read interactions.
- Polished README and operator documentation for the simplified Tomorrowland air-gapped release artifact flow, split image parts, optional model bundles, and safe upgrade instructions.
- Simplified air-gapped release artifact operator flow. Adds `scripts/tomorrowland-airgap.sh`, a single operator-facing wrapper that supports `validate`, `validate --load-images`, `load-images`, `up`, `status`, `down`, `backup`, `upgrade`, and `help`. The wrapper auto-detects split image parts beside the platform archive (no manual reassembly), delegates to existing lower-level scripts, and hides internal plumbing from operators. The main platform archive remains small and excludes the Docker image tar in split mode; image parts are distributed beside it. Updated `build-release-artifact.sh`, `validate-airgap-artifact.sh`, and `upgrade-airgap.sh` to include the wrapper in the archive, require it in validation, and copy it on upgrade. Updated operator docs to a short copy-pasteable happy-path command sequence. Missing Ollama model bundle remains degraded-only, not a platform startup blocker.
- RabbitMQ stage-based job bus (#432): parse → translate → embed → index → intelligence/alert pipeline with per-stage queues, 30s retry tiers, DLQ, admin monitoring routes (`GET /admin/rabbit/queues`, `GET /admin/jobs`), and air-gap support. `RABBITMQ_ENABLED=false` (default) keeps existing DB-poll path.
- Issue #85: Search workflow keyboard navigation and quick preview — `/` focus, listbox result selection with Arrow/j/k keys, Enter-to-open, Space quick preview with Esc focus restoration, and accessible selected result state.
- Added release and board guardrails to `AGENTS.md` so agents keep RC blockers, release assets, branch freshness, board labels, and handoffs consistent.
- Refactored `AGENTS.md` into a compact, token-efficient guide (~140 lines). Moved coordination templates (claim, transfer, handoff, issue/PR templates) into a new `docs/agents/templates.md`. Updated `docs/agents/token-efficiency.md` and `docs/README.md` to reference the new templates file.
- Issue #127: Split air-gapped release image bundle into GitHub Release-safe part files. The Docker image tar is distributed as `tomorrowland-images-<version>.tar.part-*` beside a small platform archive so each asset stays below the 2 GiB per-file limit. Adds `SPLIT_IMAGE_BUNDLE` / `IMAGE_PART_SIZE` build controls (split mode on by default), `images/README-images.txt` in the platform archive explaining where the parts are, `image_bundle` metadata in `release-manifest.json`, split-part discovery and streaming load in `load-airgap-images.sh`, contiguous-part verification and reconstruction in `validate-airgap-artifact.sh`, workflow upload of all split assets, and `docs/operations/split-airgap-artifacts.md` operator guide. Legacy `SPLIT_IMAGE_BUNDLE=0` embedded mode is preserved.
- Issue #115: Default RC2 Ollama model bundle tooling and docs. Adds connected-host bundle build, air-gapped load, offline model validation/smoke-test scripts, model-bundle-aware platform artifact validation, release workflow upload support for `tomorrowland-ollama-bundle-<model>-<version>.tar.gz`, `.env.airgap.example` model-bundle guidance, and deployment/upgrade/release-note documentation that treats missing model weights as degraded local Q&A/RAG capability rather than platform startup failure.
- Issue #107: Air-gapped translation language pack for English, Hebrew, Chinese Simplified, Korean, Thai, Arabic, French, Russian, and Spanish, bundled into the Docker artifact with validation. Adds a pinned `tomorrowland/libretranslate:airgap` image with Argos Translate packs pre-installed at build time, `SUPPORTED_TRANSLATION_SOURCE/TARGET_LANGUAGES` env config, a `scripts/validate-translation-languages.sh` validation script, and updated air-gapped deployment and upgrade documentation.
- Issue #86: Large list and lazy panel performance — paged history loading, paged document comments in the insight pane, deferred hidden document-panel fetch coverage, and memoized high-churn rows for search results, notifications, and admin sources without backend API or route changes.
- Issue #64: Optional `monitoring` Compose profile with loopback-bound Prometheus/Grafana, tracked Prometheus scrape and alert rules, provisioned Grafana datasource and five starter dashboards, separate monitoring volumes, and unchanged default `docker compose up` behavior.
- Issue #65: NiFi event integration with a typed Kafka event envelope, inline text and staged-file payload normalization, bounded fake-testable Kafka drain, event-level DLQ routing, post-processing/post-DLQ offset commits, source-grant preservation, and deterministic NiFi/Kafka tests without live services.
- Issue #88: Frontend user performance telemetry — privacy-safe in-memory timing diagnostics for login-to-shell, route navigation, search requests/first results, document preview loads, Q&A answers, and admin source sync actions, with opt-in local console inspection and no third-party analytics.
- Issue #83: Hebrew and English UI localization — typed in-repo i18n dictionary (`en`/`he`), `LanguageProvider` context, `LanguageSelector` dropdown in the NavRail and login page, full translation coverage across navigation, login, search, filters, document view, Q&A, comments, annotations, subscriptions, notifications, history, expertise, admin, and command menu. Hebrew switches `document.lang` to `he` and `document.dir` to `rtl`. Selection persists in `localStorage`. Dynamic document content (titles, snippets, usernames) is not translated. English remains the default.
- Refreshed agent coordination docs so Claude, Codex, and human reviewers work from the current issue-based release queue, avoid stale completed missions, and follow tighter context-loading/shared-file conflict guidance.
- Documented host-mounted SMB/CIFS share ingestion through the existing `folder` connector, including read-only host mounts, read-only `api` bind mounts, source setup, security guidance, air-gapped notes, upgrade path stability, and troubleshooting for Issue #78.
- Air-gapped upgrade workflow with read-only preflight checks, fail-closed backup, explicit restore, upgrade orchestration, release manifest safety metadata, and operator documentation that preserves data volumes while loading local images and running migrations.
- Release artifact and air-gapped Compose deployment path with prebuilt image bundling, offline validation/loading scripts, air-gapped environment template, GitHub Actions workflow, and operator runbook for download-to-first-use installs.
- Added an admin-only `/admin/readiness` endpoint with cached dependency probes and Prometheus dependency health metrics.
- Phase 08e UI collaboration and discovery: standalone comments and annotations panels, subscriptions with saved-search conversion, grouped notifications, private history note, neutral expertise map, Cmd/Ctrl+K command menu, and Playwright accessibility smoke coverage.
- Phase 10b domain metrics: Prometheus counters, gauges, and histograms for authentication, authorization, admin actions, ingestion, pipeline stages, search, translation, intelligence, Ollama, RAG, preview, downloads, comments, annotations, subscriptions, and notifications.
- Phase 10a metrics foundation: per-app Prometheus registry, `/metrics` endpoint, default process/GC metrics, `tomorrowland_build_info`, HTTP request counters/histograms, exception metrics, route-template-safe labels, and `X-Request-ID` propagation.
- Phase 08d: Document detail page — MIME-aware PreviewPane (11 typed renderers: Text, HTML with DOMParser XSS sanitization, Table, Archive, Email, Slides, Image, Unsupported, ExtractionFailed, FileMissing, LoadingTimeout), InsightPane tab architecture (Summary, Q&A, Related, Annotations, Comments, Subscriptions), DocumentToolbar (back button, title h1, TrustDisplay quality badge, TranslationVersionSelector, RequestTranslationDialog, download link), QA sub-components (QuestionInput, AnswerPanel, CitationCard, CitationList, QAPanel embeddable), and QAPage refactored to delegate entirely to QAPanel.
- Phase 08c: Main product UI — search workspace (SearchPage with URL-synced `?q=&mode=` params,
  keyboard `/` shortcut, skeleton loading, mode toggle, filter panel, result rows with MIME icon
  and "Why" tooltip), document preview page (split-pane PreviewPane + DetailsPanel with Summary,
  Entities, Tags, Related, Annotations, and Comments tabs, full CRUD for comments and annotations,
  XSS-safe HTML sanitization), Q&A page with answer block and citation links, Subscriptions page
  (create/edit dialog with threshold slider, toggle, delete with confirmation), Notifications page
  (mark-read on click, unread accent), History page (recent views list), live unread count in
  NavRail badge, and frontend CI job (lint + typecheck + test + build).
- Split GitHub Actions into focused backend, frontend, docs, container, and security workflows with path filters, dependency caches, concurrency cancellation, BuildKit caching, and release CD for version tags.
- Metrics and monitoring design plus Phase 10 observability plan covering
  Prometheus metrics, admin readiness, structured logs, dashboards, alerts, and
  future worker observability.
- Phase 08f-5 production audit helper for static production checks, Compose config validation, tracked secret scanning, and opt-in dependency audits.
- Phase 08f-4 smoke bootstrap helper for idempotent admin/group/source fixture setup and path-guarded deterministic document creation inside the API container.
- Phase 08f-3 no-mock Compose smoke test script covering startup, fixture setup, authentication, folder-source ingestion, search, preview, download, frontend reachability, and default volume teardown.
- Phase 08f-2 operations documentation: fully annotated `.env.example` plus expanded production Compose runbook for setup, reset, backup, restore, health checks, and troubleshooting.
- Phase 08f-1 production defaults: configurable CORS origins wired into FastAPI, Compose defaults pinned to the local frontend origin, and tracked JWT examples use production-change placeholders.
- Phase 08f production hardening plan split into five reviewable PRs for production defaults, operations documentation, Compose smoke testing, smoke bootstrap fixtures, and production audit automation.
- Confluence and Jira Server/Data Center connectors that validate non-cloud
  Atlassian URLs, expose admin form schemas, poll pages/issues, normalize
  page/issue text, and download attachments for ingestion.
- Data source connector abstraction — `src/services/connectors/` package with a
  `SourceConnector` protocol, `ConnectorField` for self-describing config schemas,
  `FolderConnector` (extracted from `sync_now`), and `NiFiConnector` stub ready for
  implementation. Adding a new source type now requires one class and one registry entry.
- `GET /admin/connector-types` endpoint returning each connector's field schema
  (label, key, sensitive flag) so the UI can render the correct form dynamically.
- `POST /admin/sources` now accepts and persists a `config` dict for per-source
  credentials and settings (e.g. API tokens, base URLs).
- `PipelineWorker.process_document` accepts optional `pre_extracted_text`, enabling
  API/network connectors that deliver text directly rather than file paths.
- Admin Sources page (`/admin`) — React feature using the Phase 08b design system:
  sources table, Add Source dialog with a form that adapts to the selected connector
  type (sensitive fields masked), and inline Sync result display.
- Agent efficiency guidance: canonical uppercase `AGENTS.md` plus `frontend/AGENTS.md` with scoped commands, token-saving workflow, and common mistake checklists.
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
- Phase 07b: Annotations — `annotations` table, `AnnotationRepository`, `GET|POST /documents/{documant_id}/annotations`, `PUT|DELETE /annotations/{annotation_id}`, private/shared visibility filtering, hard delete with creator/admin permission checks, JSON position support.
- Phase 07a: Document comments — `document_comments` table, `CommentRepository`, `GET|POST|PATCH|DELETE /documents/{documant_id}/comments`, soft-delete with creator/admin permission checks, pagination and sorting, `feature.document_comments` flag.
- Phase 06: Intelligence layer — `document_summaries`, `entities`, `document_entities`, `document_tags` tables, `IntelligenceWorker` with mocked Ollama client, summarize/extract_entities/auto_tag tasks, `GET /documents/{documant_id}/summary`, `/entities`, `/tags`, `POST /admin/intelligence/{documant_id}/trigger`, wired into `PipelineWorker` after indexing, best-effort failure behavior.
- Phase 05c: Translation versions — `document_translation_versions` table, `GET /documents/{documant_id}/translation-versions`, versioned preview with `?translation_version_id=`, `POST /documents/{documant_id}/translate` creates version records, `SlowWorker` processes pending versions, auto-enrich creates `auto_enrich` version.
- Phase 05b: Translation enrichment — manual request `POST /documents/{documant_id}/translate`, auto-enrich threshold via `document_views` count, `SlowWorker` re-translation/re-indexing, `GET /admin/enrichment-queue`.
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
- SMB source connector MVP using `smbprotocol`/`smbclient` service-account username/password authentication, source type registration, migrations for `smb` source/document constraints, and operational docs that call out NTFS ACL, Kerberos, and DFS limitations.

### Fixed
- Issue #480: Enter key now submits in comment and annotation composers without requiring a toolbar click.
- Non-ASCII filename downloads: `Content-Disposition` header now uses RFC 5987 `filename*=UTF-8''` encoding so filenames with Hebrew, CJK, and other non-ASCII characters download correctly.
- Translation stage monotonic progression and frontend waiting/done state separation for translate-stage jobs.
- Pipeline stateless execution, data visibility between stages, and structured observability logging across all workers.
- `IndexConsumer` now publishes to the intelligence, alert, and enrich queues and marks jobs succeeded in the correct order.
- Issue #139: Fixed frontend/backend document contract drift by normalizing backend entity list responses into the insight UI shape and treating backend `available` translation versions as selectable while pending/running versions remain disabled.
- Issue #114: Air-gapped LibreTranslate image build no longer fails with `ModuleNotFoundError: No module named 'argostranslate'`. `docker/libretranslate.Dockerfile` now installs pinned `argostranslate==1.9.6` into the system Python before running `install-translation-packs.py`, because the `libretranslate/libretranslate:v1.6.3` base image keeps its Python dependencies in a virtual environment that is not on the `python3` path when executing `RUN` commands as root.
- Frontend collaboration/discovery API clients now match backend comments, annotations, and expertise wire formats.
- `services/health.py` now uses `typing_extensions.TypedDict` for Python 3.11
  compatibility (Pydantic 2 rejected `typing.TypedDict` on Python < 3.12).
- Frontend admin sources integration now passes lint/build checks with type-only
  imports, matching primitive props, and a Fast Refresh-safe toast context split.
- Connector metadata from `ConnectorDocument.metadata` is now persisted into `documents.metadata` during admin-triggered syncs.
