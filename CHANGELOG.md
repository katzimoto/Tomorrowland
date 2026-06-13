# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed
- **Citation deduplication respects text lane and chunk identity (#764)**:
  RAG citations are now deduplicated by `chunk_id` (which embeds a lane suffix,
  e.g. `-orig-0` vs `-tr-0`) rather than the legacy `(document_id, chunk_index)`
  pair.  This prevents original and translated chunks that share the same
  document/index from being collapsed into one citation.  When `chunk_id` is
  absent (legacy payloads), the fallback key is
  `(document_id, chunk_index, text_lane or "original")`, keeping lane separation
  intact without breaking existing citations.  The `Citation` model now exposes
  `chunk_id` and `text_lane` so Evidence Inspector can display which evidence
  lane each citation came from.  `RetrievalCandidateTrace` also gains
  `text_lane` for trace-v2 diagnostics.  Applies to both streaming and
  non-streaming answer paths.
- **Qdrant language and text-lane metadata preserved in vector payloads (#763)**:
  `QdrantSearchClient.upsert_chunks` now copies `language`, `text_lane`, and
  `translated_from` fields from the embed pipeline into Qdrant payloads.
  Previously the `language` field emitted by `EmbedConsumer` was silently
  dropped. All three search methods (`search`, `search_filtered`,
  `list_chunks_by_document`) now surface these fields in `SearchResult.metadata`.
  `RagService` propagates them into citation `language`/`translated_from` fields
  and retrieval trace candidates. Downstream systems (Evidence Inspector v2,
  RetrievalTrace v2, citation anchors) can now reliably distinguish original
  from translated vector hits. Legacy payloads without these fields degrade
  gracefully — no reindex required.
- **Uniform filter enforcement across BM25 and vector results (#759)**:
  `/search` filters (source, MIME type, language, tags, file extension, date
  range) now apply equally to Meilisearch/BM25 and Qdrant/vector candidates.
  A post-retrieval predicate (`_matches_filters`) is applied to all merged
  results after `DocumentRow` enrichment and before pagination, ensuring no
  out-of-filter Qdrant result can appear in the final response.  The
  `date_to`/upper-bound date filter is now enforced server-side via a new
  `created_before` field on `DocumentSearchFilters` (previously left
  client-side).  The language filter is also pushed into Qdrant as a
  `source_language` payload condition to reduce wasted vector candidates.
- **Qdrant collection dimension alignment (#758)**: `/search` fallback
  `QdrantSearchClient` construction now passes `dimension=encoder.dimension`
  instead of the hard-wired default (384). When `app.state.qdrant_client` is
  absent, the client now targets the same collection the embed worker writes to,
  ensuring correct vector retrieval for all embedding providers (Ollama,
  OpenAI-compatible, local).

### Added
- **Preview artifact orphan cleanup (#749)**: adds two admin API endpoints for
  safe, operator-invokable preview artifact maintenance.
  `GET /admin/preview/artifacts/orphans` performs a dry-run scan and reports
  stale artifact directories with estimated bytes reclaimable; nothing is
  deleted.  `POST /admin/preview/artifacts/sweep` executes the cleanup,
  removing only orphaned `files_root/previews/<document-id>/<sha256>/`
  directories whose `(document_id, content_sha256)` pair has no live row in
  `document_preview_artifacts`.  Both endpoints require admin privileges, log
  aggregate counts (not paths), and never touch original uploaded files or
  extracted document payloads.  Adds `PreviewArtifactStore.scan_orphans` and
  an operations runbook at `docs/operations/preview-artifacts.md`.
- **Eval suite v2 — layout-aware and preview-anchor regression cases (#754)**:
  expands the offline eval suite from 8 to 21 fixture cases across 12 categories.
  New categories cover: `layout_aware` (parent/child heading context, multi-column
  PDF, sibling layout blocks), `preview_anchor` (PDF page anchor, email body
  anchor, XLSX sheet anchor, missing-metadata fallback), `translation_anchor`
  (English and Hebrew questions against translated retrieval branches), and
  `malicious` (prompt-injection and sensitive-content no-answer edge cases).
  Fixtures gain optional `expected_anchor_kind`, `expected_page`, and
  `expected_sheet_name` fields; the harness evaluates anchor matching as a
  hard failure when expected values are set and records observed
  `cited_page_numbers`, `cited_section_headings`, `cited_languages`,
  `cited_translated_from`, trace v2 fields (`trace_version`,
  `retrieval_degraded`, `reranker_dropped_count`, `scope_filtered_count`,
  `dedup_count`), and `layout_expansion_applied` in every result record.
  `RetrievalMetrics` gains `anchor_accuracy`, `anchor_cases_total`, and
  `anchor_cases_passed` to distinguish document-level recall from
  citation-anchor quality. Nightly artifact JSON is updated to include anchor
  metrics for the Quality Lab (#714). 28 unit tests cover all metric functions.
- **Citation anchors for rendered artifacts (#752)**:
  defines the `CitationPreviewAnchor` interface that connects a RAG citation to
  an exact, format-aware preview target.  `buildCitationAnchor()` converts a
  `DocumentChatCitation` + optional `PreviewManifest` into an anchor:
  PDF/Office documents navigate to `page_number`; spreadsheets resolve the
  target sheet from `section_heading` (sheet name), then `page_number` (sheet
  index), then fall back to the first sheet; email and text targets use the
  citation excerpt for body-text search and highlight.  `PreviewWithHighlight`
  now fetches the manifest and builds the anchor automatically; `PreviewPane`
  accepts a `citationAnchor` prop that routes page/sheet navigation to the
  correct renderer.  `SheetViewer` opens on the cited sheet at mount.  Pending,
  partial, and failed manifest states already handled by existing dispatchers;
  access revocation enforced by the backend API (403).  16 unit tests cover
  PDF/Office page anchor, email/text excerpt anchor, XLSX sheet-by-name and
  sheet-by-index resolution, first-sheet fallback, and missing-metadata
  graceful degradation.
- **Evidence Inspector v2 — backend attribution and rerank diagnostics (#750)**:
  the Evidence panel now surfaces retrieval trace v2 data for each citation.
  The Evidence tab shows backend attribution chips (`vector`, `bm25`, `metadata`,
  `translated`), fused rank, reranker rank change (input → output), and final
  context position for the matched candidate. The Retrieval tab (admin) gains a
  degraded-backends list with safe error categories, a count-summary row for
  scope-filtered, deduplicated, below-threshold, and reranker-dropped candidates,
  and a `#ctx` column in the candidates table. All v2 fields degrade gracefully
  when absent — v1 traces render identically to before.
- **Retrieval trace v2 — backend attribution and rerank deltas (#751)**:
  extends `RetrievalTrace` and `RetrievalCandidateTrace` with decision-level
  diagnostic fields. Each final candidate now carries `backends` (which of
  `vector`/`bm25`/`metadata`/`translated` contributed, with per-backend score
  and rank), `fused_rank`/`fused_score` (post-merge position and combined
  score), `reranker_delta` (input rank/score, cross-encoder score, output rank),
  and `final_context_rank` (1-based position in the prompt context).
  `RetrievalTrace` gains `trace_version=2`, `degraded_backends` (safe
  category-only error info per failed backend), `scope_filtered_count`,
  `dedup_count`, `score_threshold_filtered_count`, and `reranker_dropped_count`.
  All new fields are optional — existing v1 consumers are unaffected. The RAG
  reranker implementations now embed `_reranker_score` into returned chunk dicts
  so the cross-encoder score surfaces in the trace.  26 new unit tests cover
  hybrid, reranked, translated, metadata, degraded, and ACL-filtered paths.
- **Mail preview rendering pipeline — slice 1 (#539)**: high-fidelity EML
  preview behind a new manifest API. `GET /preview/{id}/manifest` reports
  render status (`pending`/`running`/`ready`/`partial`/`failed`); mail bodies
  render to a sanitized HTML artifact (`nh3` allowlist + deny-all CSP, served
  for sandboxed-iframe display) plus a plain-text artifact, with `cid:` inline
  images embedded as `data:` URIs and remote images/tracking pixels stripped
  and counted. `GET /preview/{id}/artifact/{artifact_id}` serves artifacts by
  opaque ID (no filesystem paths in responses); `POST /admin/preview/{id}/rerender`
  clears a cached render. Artifacts are cached per `document_id + content_sha256`
  in the new `document_preview_artifacts` table and on disk under
  `files_root/previews/`. Rendering runs in a new `preview-worker`
  (`tomorrowland-preview-worker`, queue `document.preview.requested`) so the
  API keeps its read-only `files_data` mount; a render failure is terminal
  (no retry loop on corrupt/oversized files). PDF/image/text documents report a
  ready-immediate manifest and keep using the existing download/text endpoints;
  Office kinds report a text fallback until later slices. New settings:
  `ENABLE_PREVIEW_RENDER` (default `true`), `PREVIEW_MAX_FILE_BYTES`,
  `PREVIEW_MAX_INLINE_IMAGES`, `PREVIEW_MAX_INLINE_IMAGE_BYTES`. New dependency:
  `nh3`. See `docs/planning/preview-mail-office-first-2026-06.md`.
- **Mail preview UI — slice 2 (#539)**: the document preview pane renders mail
  through a new manifest-driven `EmailViewer` — a metadata header card, the
  sanitized HTML body in a `sandbox=""` iframe with a Formatted/Text toggle,
  collapsible quoted reply history, a blocked-remote-images notice, and an
  attachment list that links to each attachment's child document. A
  `ParentContextBanner` on attachment documents links back to the parent email.
  In-document search and citation highlighting operate on the text body. The
  pane falls back to the existing extracted-text email renderer whenever the
  manifest is pending, disabled, or failed (zero regression). Extracted and
  translation view modes keep the plain-text renderer.
- **Outlook MSG preview — slice 3 (#539)**: `.msg` documents
  (`application/vnd.ms-outlook`) now render through the same manifest pipeline
  and `EmailViewer` as EML, via a new MSG renderer built on the existing
  `extract-msg` dependency. HTML bodies are nh3-sanitized with `cid:` inline
  images embedded; RTF-only Outlook bodies degrade to the plain-text body
  (RTF→HTML conversion is a tracked follow-up). The EML and MSG renderers now
  share a common manifest/inline-image assembler. No new dependency.
- **Office DOCX/PPTX visual preview — slice 4 (#539)**: Word and PowerPoint
  documents (and the legacy/ODF equivalents) now render a high-fidelity visual
  preview. A new `preview-worker` image (`docker/preview-worker.Dockerfile` =
  the backend image plus LibreOffice headless + fonts) converts the document to
  a cached `converted.pdf` artifact, which the existing pdf.js viewer renders
  with page/slide navigation, zoom, and in-document search. The frontend
  `OfficeManifestPreview` dispatches to the PDF viewer when the render is ready
  and falls back to the extracted-text/slides renderer while pending, disabled,
  or failed. Conversion runs only in the preview worker (no macros, isolated
  per-job LibreOffice profile, subprocess timeout, page-count cap → `partial`).
  Spreadsheets are intentionally excluded (sheet-grid rendering is a later
  slice) and keep their table preview. The release build packages the new image
  into the air-gapped split-parts bundle. New settings:
  `PREVIEW_RENDER_TIMEOUT_SECONDS`, `PREVIEW_MAX_PAGES`. New env var:
  `TOMORROWLAND_PREVIEW_WORKER_IMAGE`.
- **XLSX sheet-grid preview — slice 5 (#539)**: `.xlsx` spreadsheets render as
  structured per-sheet grids with real sheet tabs (a new `SheetViewer`) instead
  of flattened text. The preview worker emits one JSON grid artifact per sheet
  (`openpyxl`, `data_only`), capped to the first rows/columns
  (`PREVIEW_MAX_SHEET_ROWS`/`PREVIEW_MAX_SHEET_COLS`); over the cap the preview
  is marked `partial` and a banner points to the download for the full sheet.
  In-document search highlights and counts cell matches in the active sheet. The
  frontend `SheetManifestPreview` falls back to the extracted-text table preview
  while pending, disabled, or failed. Legacy `.xls` and `.ods` keep the table
  preview (openpyxl reads only `.xlsx`).
- **Preview admin diagnostics — slice 6 (#539)**: a `RendererStatusBadge` shown
  to admins on the document preview surfaces the preview renderer, render status,
  and (on failure) the error category/detail, plus a one-click **Re-render** that
  discards the cached render and re-polls the manifest. A `sweep_orphans`
  maintenance helper reclaims preview artifact directories left behind by
  superseded versions or deleted documents.
- **Docling PDF extractor (#649)**: `DoclingPdfExtractor` registered as a
  `QualityTier.HIGH` backend for `application/pdf` when `ENABLE_DOCLING=true`.
  Produces layout-aware Markdown (tables, multi-column, headings) for richer RAG
  chunking.  Docling is an optional dependency (`pip install tomorrowland[docling]`);
  when absent the parser router falls through to the existing pypdf extractor.
  New config setting: `ENABLE_DOCLING` (default `false`).

### Removed
- **Dead legacy translation worker (#695)**: deleted
  `src/services/pipeline/translation_worker.py` (290 lines). It had no
  console entrypoint, no Compose `command`, and zero callers — the live
  translation path is `translate_worker.py` (`tomorrowland-translate-worker`).
  Its only test coverage (empty-content graceful skip) was ported to the live
  `TranslateConsumer`.

### Added (CI / quality)
- **Nightly integration & eval workflow (#703)**: `.github/workflows/nightly-integration.yml`
  runs every night at 02:00 UTC (and on `workflow_dispatch`). Two jobs: (1) full
  `tests/integration/` suite against PostgreSQL, plus migration downgrade smoke for
  the 5 most recent revisions (both SQLite and Postgres); (2) retrieval eval
  (`tests/eval --eval`) with Qdrant service, result JSON uploaded as artifact for
  trending (`continue-on-error: true` — no hard gate on eval metrics).
- **Migration downgrade smoke test (#703)**: `tests/test_migration_downgrade.py`
  parametrises the 5 most recent Alembic revisions and for each runs
  `upgrade → downgrade -1 → upgrade head`. SQLite variant runs in the regular
  per-PR unit suite; Postgres variant is guarded by `PGTEST=1`.
- **Coverage floors (#703)**: backend unit tests now enforce `--cov-fail-under=60`
  (branch + statement, baseline 62%). Frontend vitest thresholds raised from
  30/20/25/30 to 50/33/42/50 (statements/branches/functions/lines) after the
  WS4 test-gap issues (#701, #702) landed. Both floors documented in
  `docs/agents/ci-hardening.md`.

### Fixed
- **Chat streaming error — inline error state (#702)**: when a streaming send
  fails, `ChatWindow` now renders an inline `EmptyState` with a Retry button
  (in addition to the existing toast). The user's unsent message is preserved in
  the input so they can retry or edit before resending. The error state clears
  automatically when the user sends a new message.

- **Double enrichment per document (#694)**: intelligence and alert stages
  fired twice for every document with content, because both the translate
  worker's early index publish and the embed worker's post-embed index publish
  triggered downstream enrichment. Index messages now carry an `enrich` flag:
  the translate stage publishes the early pass with `enrich=false` (the
  document stays immediately keyword-searchable, including when the embed
  stage is degraded) and the embed stage publishes the final pass with
  `enrich=true`, so intelligence/alert run exactly once — on the updated,
  post-translation content. Messages without the flag (in-flight during
  deploy) keep the old behavior, and the flag survives retry republishes.

### Added (v0.3 — Trust and Retrieval Quality)
- **BGE Reranker (#650)**: `SearchResponse` now includes `reranker_applied: bool`
  so callers can tell whether cross-encoder reranking was performed. The BGE
  endpoint-based reranker (`BAAI/bge-reranker-v2-m3`) is enabled via
  `SEARCH_RERANKER_ENABLED=true` + `SEARCH_RERANKER_URL`.
- **Retrieval trace in chat (#665)**: Assistant messages now persist and expose
  their `retrieval_trace` (pipeline stages, timings, candidate scores). Admins
  receive the trace in every message response; a dedicated
  `GET /chat/sessions/{id}/messages/{id}/trace` endpoint is available for
  admin/developer inspection. The frontend Evidence Inspector's Retrieval tab
  shows stage counts, timings, and the final candidate list.
- **Evidence Inspector v1 (#664)**: The citation side-panel is upgraded to a
  tabbed inspector with Evidence, Source, Retrieval (admin), and Actions tabs.
  The Evidence tab shows the excerpt, chunk index, and translation metadata;
  Source shows document and source info; Actions includes copy-citation and a
  report-bad-citation feedback form.
- **Citation feedback (#666)**: New `citation_feedback` table and
  `POST /citation-feedback` endpoint let users report citation quality problems
  (wrong passage, missing source, unsupported claim, etc.). Permission-gated:
  users can only submit feedback for documents they can access. Admin query
  endpoints allow eval code to read feedback by document, message, or type.
- **Offline eval harness (#667)**: `tests/eval/` provides a `pytest --eval`
  runner with fixtures across 9 categories (factual, citation-required,
  no-answer, Hebrew/multilingual, permission boundary, multi-doc, follow-up,
  table-heavy). Emits machine-readable JSON; supports comparing two
  configurations (e.g. reranker on/off via `--eval-config`). Metrics: recall@k,
  MRR, citation accuracy, no-answer accuracy, unauthorized-leakage count, and
  per-stage latency.

### Added
- Air-gapped (and default) Docker Compose now pass the external model-provider
  settings — `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, and
  `EMBEDDING_API_KEY` — through to the `api` and every pipeline worker. Operators
  can run the air-gapped stack against an external local LLM that speaks the OpenAI
  API (e.g. a LiteLLM proxy, vLLM, or llama.cpp) **without loading an Ollama model
  bundle**, by setting `LLM_PROVIDER=litellm` (or `openai-compatible` / `llama-cpp`)
  plus `LLM_BASE_URL` / `LLM_MODEL`. Defaults stay empty, so the bundled Ollama is
  still used out of the box. `.env.airgap.example` and the air-gapped deployment
  guide document the LiteLLM path. Previously these variables existed in `Settings`
  but were never injected into the containers, so the external-LLM path was
  unreachable in Compose deployments.

### Changed
- **CI performance**: the `migrated_engine` test fixture now runs the Alembic
  chain once per session into a template (Postgres template database / SQLite
  template file) and clones it per test, instead of re-running all migrations
  inside every test; integration tests run with `pytest -n auto`; coverage
  instrumentation is opt-in (`--cov=src`) instead of always-on; the PR Quality
  Gate workflow keeps only the cleanliness check and defers lint/type/test and
  docs builds to Backend CI and Docs CI. Backend PR feedback drops from
  ~15 minutes to a few minutes with no loss of checks.
- Simplified air-gapped release to not require local AI for startup. `ollama/ollama`
  image pinned to `0.5.13`; Ollama removed from `api` depends_on health check in
  `docker-compose.airgap.yml`. Docs, env template, and READMEs updated to clearly
  separate required (platform archive + image parts) from optional (Ollama model
  bundle) components. Missing model bundle produces a warning only, not a startup
  failure.

### Removed
- Removed the unused legacy QA UI (`frontend/src/features/qa/*` and
  `frontend/src/api/qa.ts`). It was orphaned dead code — not registered in
  `routes.tsx`, not imported anywhere, and superseded by Full Document Chat
  (#492), which provides the same question-answering with citations.

### Fixed
- Air-gapped Compose now includes the Meilisearch keyword-search service and the
  seven pipeline workers (`parse`, `translate`, `embed`, `index`, `intelligence`,
  `alert`, `enrich`), plus the `MEILISEARCH_*` and `RABBITMQ_*` environment wiring
  they require. Previously `docker-compose.airgap.yml` shipped without them, so an
  air-gapped deployment started but could not ingest or search documents. Keyword
  search and ingestion now work out of the box without any local model; the embed
  and intelligence stages stay degraded until an optional Ollama model bundle is
  loaded.
- Bound RabbitMQ's AMQP (`5672`) and management (`15672`) ports to `127.0.0.1` in
  the air-gapped Compose file, matching every other service and preventing
  external exposure of the broker and its management UI with default credentials.
- Replaced stale `Elasticsearch` references with `Meilisearch` across the packaged
  air-gapped scripts and operations docs (search backend migrated in #545), and
  corrected the "workers not included" notes in the deployment and
  production-compose docs.
- `validate-airgap-artifact.sh` now asserts the Meilisearch service and all seven
  pipeline workers are present in the air-gapped Compose file, guarding against
  this regression.

### Added
- Issue #550: Harden Jira service-account sync with rich issue metadata, optional
  project filters, JQL override, streaming attachments, MIME filters, retry/backoff,
  and real connection validation.
  - Explicit `auth_mode` config (defaults to `"service_account"`; unsupported
    modes are rejected with a clear error).
  - Optional per-source `project_keys` list filter; legacy single `project_key`
    maps automatically to `project_keys: ["<value>"]`. Empty/omitted means all
    issues visible to the service account. Project keys are validated against
    `^[A-Za-z0-9_]{1,255}$` to avoid unsafe JQL injection.
  - Explicit `jql` override field. When set, wins over `project_keys`,
    `project_key`, and `updated_since`. Default JQL always appends
    `ORDER BY updated ASC` for deterministic pagination; custom JQL preserves
    existing ordering when present.
  - Rich structured issue ingestion: 22 fields requested via Jira API
    (summary, description, project, issuetype, status, priority, resolution,
    labels, components, fixVersions, versions, created, updated, resolutiondate,
    assignee, reporter, creator, parent, subtasks, issuelinks, attachment,
    comment). Machine-readable versions stored in document metadata;
    human-readable versions rendered into searchable issue text.
  - People fields (assignee, reporter, creator) preserved with stable
    identifiers (key, name, display_name, email, active). Searchable text
    includes readable lines like `Assignee: Alice Cohen`.
  - Comments included by default with inline rendering (author + timestamp +
    body). Configurable via `include_comments`, `comments_mode`,
    `max_comments_per_issue`, `comment_body_format`. Comment metadata preserves
    author, update_author, created, updated, and visibility fields. Restricted
    comment visibility is captured as metadata but not enforced per user
    (deferred to future Jira DLS/user-delegated work).
  - Related issues and hierarchy: issue links (blocks/blocked by/relates
    to/etc.), parent issue, and subtasks indexed as metadata and searchable
    text with relationship type, direction, linked key/summary/status.
  - Changelog/worklog config placeholders (`include_changelog`,
    `include_worklogs`) default to `False`; no changelog/worklog ingestion by
    default.
  - Streaming attachment downloads with incremental SHA256 (shared
    `_AtlassianConnectorBase` implementation from #548). Configurable
    `max_attachment_mb` (default 50 MiB) enforced during streaming.
  - Configurable MIME allowlist (`attachment_mime_allowlist`) and blocklist
    (`attachment_mime_blocklist`) with prefix matching for blocklist entries.
  - Configurable retry with exponential backoff and jitter for transient HTTP
    errors (429, 5xx) and network failures. Configurable
    `request_timeout_seconds` (default 30). Permanent auth/config errors
    (401, 403, 404) are never retried.
  - Real connection validation via `GET /rest/api/2/myself` (auth check) +
    `GET /rest/api/2/project/{key}` (when project_keys configured) or
    `POST /rest/api/2/search?maxResults=1` (general reachability).
  - 50+ new unit tests covering auth_mode defaults/rejection, project_keys
    validation/precedence/legacy-mapping, JQL override and ordering, rich
    metadata extraction, people fields, comments rendering and metadata,
    parent/subtasks/issuelinks, changelog/worklog defaults, attachment MIME
    filtering, connection validation, backward compatibility, and edge cases.
    Existing Jira sources continue working without config changes.
- Issue #548: Harden Confluence service-account sync with optional space filters,
  streaming attachment downloads, MIME filters, retry/backoff, and real connection
  validation.
  - Explicit `auth_mode` config (defaults to `"service_account"`; unsupported
    modes are rejected with a clear error).
  - Optional per-source `space_keys` list filter; legacy single `space_key`
    maps automatically to `space_keys: ["<value>"]`. Empty/omitted means all
    spaces visible to the service account. Space keys are validated against
    `^[A-Za-z0-9_]{1,255}$` to avoid unsafe CQL injection.
  - Streaming attachment downloads with incremental SHA256: bytes are written
    directly to durable storage (when `storage_root` is provided) or to a temp
    file, never loaded fully into memory. Configurable `max_attachment_mb`
    (default 50 MiB) enforced during streaming; partial downloads are cleaned
    up on size-limit violation.
  - Configurable MIME allowlist (`attachment_mime_allowlist`) and blocklist
    (`attachment_mime_blocklist`). Blocklist entries ending in `/` use prefix
    matching (e.g. `video/` blocks all video subtypes). Blocklist wins over
    allowlist. Skipped attachments are counted and logged with safe summaries.
  - Configurable retry with exponential backoff and jitter for transient HTTP
    errors (429, 5xx) and network failures. Configurable `request_timeout_seconds`
    (default 30) applied to both API requests and attachment downloads.
    Permanent auth/config errors (401, 403, 404) are never retried.
  - Real connection validation via `GET /rest/api/space/{key}` (when space_keys
    configured) or `GET /rest/api/space?limit=1` (when no space filter).
    Distinguishes reachable, auth-failed, and config-invalid states.
  - Skipped attachment counters logged per-page; follow-up to surface through
    #540 sync lifecycle counters documented as deferred.
  - 36 new unit tests covering auth_mode defaults/rejection, space_keys
    validation/precedence/legacy-mapping, streaming SHA256 correctness,
    max-size enforcement, MIME allow/block/prefix logic, retry/backoff config,
    connection validation, and backward compatibility with existing Confluence
    sources. No config changes required for existing sources.
- Issue #540: canonical connector sync lifecycle and source health model.
  New `sync_runs` and `document_tombstones` tables plus source-health columns on
  `ingestion_sources` (migration `e5f7g9h1i2j3`). Sync runs track an explicit
  state machine (`queued → running → completed/completed_with_warnings/failed/
  cancelled`) with validated transitions, `incremental`/`full_resync` modes, and
  per-document counts. Manual sync-now and the scheduler now create and manage
  sync runs, guard against concurrent syncs per source, and record failures to
  source health (including failures that occur before any document is processed,
  via a separate committed transaction). New admin-only endpoints
  `GET /admin/sources/{id}/sync-runs` (bounded pagination) and
  `GET /admin/sources/{id}/health`; source list/get responses now expose
  `last_successful_sync_at`, `last_failed_sync_at`, `failure_count`,
  `warning_count`, and `last_sync_id`. Tombstone helpers record upstream
  deletions and flag documents `status='deleted'`; callers must pass an
  `index_cleanup` callback to remove a tombstoned document from the Meilisearch/
  Qdrant indexes (DB status alone does not hide it from search). `ConnectorDocument`
  gains an optional `last_modified`; `ConnectorSyncResult` is defined as the
  forward connector contract but is not yet wired into connectors. Wiring
  deletion detection into the live sync loop and full index exclusion are tracked
  as #540 follow-ups. 42 unit tests plus integration coverage for sync-now
  failure recording, the concurrent-sync guard, and admin authorization.
- Issue #582: LDAP group mapping via live DC search — admin-only endpoints for
  ephemeral LDAP group search (`GET /admin/ldap/groups/search?q=...`) and
  explicit LDAP-group-to-Tomorrowland-group mappings (`GET/POST/DELETE
  /admin/ldap/group-mappings`). Search uses the configured LDAP service
  account, escapes admin query input before injecting into LDAP filters, and
  enforces strict result limits and timeouts. Only explicit mappings are
  persisted; LDAP groups are never used directly in source/document ACLs.
  Login-time group resolution now matches user LDAP groups against explicit
  mappings only — unmapped LDAP groups are silently ignored. New
  `ldap_group_mappings` table (migration `l1m2n3o4p5q6`) stores DN, external
  ID, display name, target group, and audit fields. Real `LdapClient`
  (using `ldap3`) implements the `LdapAuthenticator` protocol plus
  `search_groups`. New config fields: `LDAP_GROUP_SEARCH_BASE_DN_LIST`,
  `LDAP_GROUP_SEARCH_FILTER`, `LDAP_GROUP_SEARCH_LIMIT`,
  `LDAP_GROUP_SEARCH_TIMEOUT`, `LDAP_GROUP_EXTERNAL_ID_ATTR`,
  `LDAP_GROUP_DISPLAY_NAME_ATTR`. Admin audit events for create/delete
  mapping operations. 14 unit tests covering repository CRUD, duplicate
  DN rejection, missing target group validation, filter escaping, and
  mapping-aware auth integration.

### Changed
- Issue #596: Default local setup to lighter Ollama models — `OLLAMA_MODEL`
  defaults to `qwen3:4b` and `OLLAMA_UTILITY_MODEL` defaults to `qwen3:1.7b`
  (~6–7 GiB RAM total) for improved first-run usability on modest hardware.
  Updated `.env.example`, `docker-compose.yml`, `docker-compose.airgap.yml`,
  `docker/ollama-llm.Dockerfile`, `docker/ollama.Dockerfile`, `src/shared/config.py`,
  `src/shared/feature_flags.py`, `src/services/intelligence/ollama_client.py`,
  `scripts/setup-env.sh`, `scripts/build-ollama-model-bundle.sh`, and
  `scripts/validate-ollama-model.sh`. Operators who already set explicit
  `OLLAMA_MODEL`/`OLLAMA_UTILITY_MODEL` overrides are unaffected. Larger
  models (`qwen3:8b`, `qwen3:14b`, `qwen3.5:35b-a3b`) remain fully supported.

### Added
- Issue #564: Air-gapped MCP adapter deployment — added `mcp-server` service
  to `docker-compose.airgap.yml` using the prebuilt backend image with
  `tomorrowland-mcp-server` entry point, bound to `127.0.0.1:8001` by default.
  Added MCP adapter configuration variables to `.env.example`
  (`MCP_API_URL`, `TOMORROWLAND_API_KEY`, `MCP_HOST`, `MCP_PORT`,
  `MCP_HOST_PORT`). Extended `scripts/validate-airgap-artifact.sh` with MCP
  adapter checks (service presence, no build steps, localhost binding warning).
  Expanded `docs/operations/mcp-adapter.md` with formal air-gapped Compose
  service guidance, Hermes/Claude Code air-gapped connection instructions, and
  air-gapped verification steps. Added MCP adapter section to
  `docs/operations/air-gapped-deployment.md`.
- Issue #563: Document Hermes researcher connection workflow — expanded
  `docs/operations/mcp-adapter.md` with a researcher-facing tool guide
  (when to use each tool, key parameters), example Hermes prompts for
  common research workflows (search, inspect, ask, find related, explore
  facets, multi-step chaining), citation behaviour and troubleshooting
  (what to do when citations are missing or insufficient), extended Hermes
  configuration with tool include list, and a known limits / deferred
  capabilities section tracking #561 (audit/usage limits), #562 (permission
  regression), #564 (air-gapped behaviour), and #565 (write tools).
  Updated `docs/README.md` operator index to list the MCP adapter doc.
- Issue #561: Audit logging and usage limits for researcher agent queries —
  all six `/api/agent/v1/*` endpoints emit structured `agent_audit` log
  lines (safe metadata only: route, user id, correlation id, query length,
  result count, latency, status; raw query text, document text, JWTs, and
  auth headers are never logged). Per-user sliding-window rate limiter
  (`AgentRateLimiter` in `src/shared/rate_limit.py`) enforces configurable
  call limits with a separate lower limit for the LLM-backed `ask_corpus`
  endpoint. MCP adapter inherits limits and logging automatically because
  every tool call proxies through the REST endpoints. `_translate_error`
  now maps HTTP 429 to a safe user message. Configurable via env vars:
  `AGENT_RATE_LIMIT_ENABLED` (default `true`),
  `AGENT_RATE_LIMIT_WINDOW_SECONDS` (default `60`),
  `AGENT_RATE_LIMIT_CALLS_PER_WINDOW` (default `100`),
  `AGENT_RATE_LIMIT_ASK_CORPUS_CALLS_PER_WINDOW` (default `20`).
  Normal search/RAG paths are unaffected. 11 new unit tests + 8 new
  integration tests.
- Source profiles: per-source strategy configuration system — new
  `source_profiles` table (migration `c4d5e6f7a8b9`) with configurable
  domain type, chunking strategy, retrieval strategy, and extraction
  strategy with DB-level CheckConstraints. `ProfileRepository` in
  `src/services/intelligence/profile_repository.py` provides full CRUD
  plus `activate_profile` (atomic one-active-per-source with auto-deprecation
  of the previous active profile) and `deprecate_profile`.
  Admin API at `/admin/source-profiles` with 7 endpoints: create (POST,
  status 201), list (GET, optional `source_id` filter), get (GET by id),
  update (PATCH), activate (POST `/{id}/activate`), deprecate (POST
  `/{id}/deprecate`), and delete (DELETE; blocks active profiles).
  All endpoints enforce admin auth and write audit log entries.
  `IntelligenceWorker.process_document()` now accepts an optional
  `source_id` parameter and resolves the active `SourceProfile` for
  strategy routing — foundational wiring with logging; actual strategy
  dispatch deferred to future work. 17 unit tests + 18 integration tests.
- Issue #560: Hermes MCP adapter for researcher API — new
  `tomorrowland-mcp-server` binary exposes six read-only MCP tools
  (`search_documents`, `get_document`, `get_passages`, `ask_corpus`,
  `get_related_documents`, `list_facets`) that proxy to the permissioned
  `/api/agent/v1/*` endpoints from #558. Streamable HTTP transport on
  `localhost:8001`. No direct DB/Qdrant/Meilisearch access. Auth forwarded
  as Bearer token. No secrets in logs. 25+ unit tests.
- Issue #558: Permissioned researcher API endpoints — new read-only `/api/agent/v1` surface (`search_documents`, `get_document`, `get_passages`, `ask_corpus`, `get_related_documents`, `list_facets`) that future Hermes/MCP clients (#560) can call through the same source/document ACL as normal users. Every endpoint enforces transitive group expansion via `AuthRepository.get_effective_group_ids` and `assert_doc_access`; admin bypass uses the standard `allow_all=True` path. `ask_corpus` re-checks per-citation source ACLs as defence in depth so Qdrant payload corruption cannot leak inaccessible documents. New `QdrantSearchClient.list_chunks_by_document` scrolls chunks in stable `chunk_index` order with the same group-id filter applied. No write tools, no MCP adapter, and no Hermes runtime in this PR.

### Removed
- Issue #545 (S1): Legacy comments API router and dead `FEATURE_DOCUMENT_COMMENTS` feature flag. All comments endpoints previously returned HTTP 410; callers must use the annotations API instead.
- Issue #545 (S4): DB-poll pipeline entrypoints and dead config. Deleted `src/services/pipeline/runner.py` and `vector_worker.py`; removed `INGEST_MODE` env var and `ingest_mode` config field; removed `pipeline-worker` and `vector-worker` Compose services with their `db-poll` profile blocks. The canonical pipeline is now RabbitMQ-only.
- Issue #545 (S5): Stale docs, smoke assumptions, and memory references to Elasticsearch, DB-poll, pipeline-worker, vector-worker, runner.py, vector_worker.py, and INGEST_MODE. Updated all documentation, scripts, and workflows to describe the canonical MVP runtime: Meilisearch (primary BM25), Qdrant (vector), RabbitMQ worker chain. Total #545 (S1–S5) complete.

### Fixed
- Issue #551: ACL audit HIGH findings regression tests. Added integration tests covering H1 (admin search bypass — ES receives `is_admin=True`, Qdrant receives `allow_all=True`), H2 (expertise admin bypass — `allow_all=True` forwarded to Qdrant), H3 (orphaned Qdrant vectors silently dropped from search results), H4 (subscription user-discovery leak — outsider excluded when no group overlap with requester), and H5 (related-docs transitive group expansion — child-group users reach parent-group sources via `get_effective_group_ids`). Also fixed two existing `RelatedService` test instantiations missing the required `job_repo` argument.

### Added
- Issue #544 (S6): Admin UI and operator documentation for model provider management — new `/admin/model-providers` page with provider list, create/edit/delete dialogs, credential entry (masked stored secrets), locality display (local/self_hosted/external), enabled/disabled state, health test action, model discovery action, model descriptor management dialog, and task-default management section. Wired into admin hub navigation. Frontend API client updated with TypeScript types for all provider endpoints. Credentials are never displayed in plaintext; edit dialog shows `credential_set` badge and masked input with clear-credential option. Destructive actions use explicit confirmation dialogs. Operator docs in `docs/operations/model-providers.md` cover local Ollama default, OpenAI-compatible, LiteLLM, llama.cpp, credential handling, air-gapped deployment, SSRF validation by locality, and task defaults with env fallback. 20+ unit tests cover provider list, create/edit flows, credential masking, descriptor management, task-default management, health/discover actions, empty/loading states, and error states.
- Issue #578 (S5): Task-default resolution and service wiring — new `TaskDefaultResolver` resolves model providers for named task types (`chat`, `utility`, `reranking`, etc.) from DB-backed `model_task_defaults`, falling back to env/config when no DB row exists (zero-row backward compatibility). Wired into `app.state.task_default_resolver` at startup. Chat router, intelligence worker admin endpoints, and reranker use the resolver to determine LLM provider, utility model, and reranker model — all with safe fallback to existing `Settings`-based behavior. Disabled providers/descriptors gracefully fall back (build_llm_provider returns None when descriptor has no model name). No secret leakage in logs. `POST /admin/model-providers/reload` reloads both the provider registry and the resolver in-process. 19 unit tests and 2 integration tests cover empty-DB, configured-DB, disabled-provider, missing-descriptor, reload, and parameter-passthrough paths.
- Issue #576 (S3): `CrossEncoderEndpointReranker` — new dedicated reranker that POSTs `{"query", "texts"}` to a configured endpoint (TEI-compatible) and parses `{"scores"}`. Falls back to identity (returns chunks unchanged) on any error. No ranking behavior changes unless configured.
- Issue #575 (S2): OpenAI-compatible embedding encoder — new `OpenAICompatibleEmbeddingEncoder` supporting configurable `/v1/embeddings` providers (API key, batch-size, index-stable sorting), new `EMBEDDING_API_KEY` config field, and `embedding_provider="openai-compatible"` factory path. Existing Ollama and deterministic-test behaviour unchanged.
- Issue #574 (S1): Model provider registry foundation — base adapter interfaces (`BaseModelProviderAdapter`, `ProviderCapabilities`, `ProviderHealthResult`), DB schema (`model_providers`, `model_descriptors`, `model_task_defaults` with locality/enabled/timestamps/unique constraints), Alembic migration, and repository layer with typed CRUD. No credential values stored — only `api_key_ref` references. No runtime behavior change.
- Issue #537: Retrieval trace foundation — typed models and minimal non-invasive RAG instrumentation.
  - New `RetrievalTrace`, `RetrievalStageTrace`, `RetrievalCandidateTrace` Pydantic models in `src/services/rag/trace_models.py`.
  - `RagService._retrieve_chunks` now returns per-stage timing and candidate counts (vector, BM25, metadata, translated, merge, dedup/filter).
  - `RagService.answer()` attaches a `RetrievalTrace` to `AnswerResponse` covering all stages, reranker status, final candidates, and total latency.
  - `RagService.answer_stream()` includes `retrieval_trace` in the `done` SSE event.
  - Trace candidates carry only identifiers, scores, and allowed metadata — no raw document text, no full prompts, no secrets.
  - 18 unit tests covering trace serialisation, per-stage counts, reranker flag, metadata/translated stages, empty-result path, and privacy rules.
- Issue #529 (backend slice): Admin ingestion pipeline status API — `GET /admin/ingestion/status` lists pipeline jobs with status/source_id/since/limit/offset filters and per-status summary counts; `GET /admin/ingestion/status/{document_id}` returns per-document job traces ordered by creation time. Both endpoints admin-only, use LEFT JOIN so deleted/missing documents return null title/source without crashing.
- Issue #529 (frontend slice): Admin ingestion pipeline status UI — new `/admin/ingestion` page with status summary cards (pending/running/completed/failed counts), filter bar (status, source_id, since), paginated jobs table, row expansion with per-document pipeline trace and requeue action. Linked from admin hub. Includes loading, empty, error, 404, and long-error-truncation states.
- Issue #530: Exact-location citation grounding — `page_number` and `section_heading` now flow from extraction through RAG citations.
  - Added `LocationSegment` dataclass with `start_char`/`end_char`/`page_number`/`section_heading` to extraction envelope.
  - PDF extractor emits `page_number` per page; PPTX extractor emits `page_number` per slide; DOCX extractor emits `section_heading` from heading styles.
  - Added `extraction_metadata` JSON column to `document_payloads` table (migration `y9z0a1b2c3d4`).
  - Parse worker persists location segments; vector worker reads them and maps chunks back to location via `resolve_chunk_locations()`.
  - Qdrant upsert stores `page_number` and `section_heading` payload fields.
  - Frontend `QACitation` type includes optional `page_number` and `section_heading`.
  - Unit tests cover PDF/PPTX/DOCX location segments, chunk-location resolution, Qdrant payload round-trip, and RAG citation assembly.
  - **Operators:** Existing documents already indexed in Qdrant will return `null` for location fields until re-parsed and re-indexed. Schedule a reindex pass after deploy to populate location metadata on existing documents.
- Issue #536: Side-by-side source preview with citation click-to-highlight. Clicking a chat citation opens an evidence panel beside the chat that loads the document preview, navigates to the cited page (PDF), and highlights the excerpt via search matching. Includes `EvidencePanel` (loading/403/404/missing-location states, mobile drawer fallback), `PreviewWithHighlight` wrapper, and `initialPage` passthrough to PdfViewer. Existing "Open document" full-page/new-tab behavior preserved. URL query param sync deferred (component state only).
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
- Issue #547: PR-gated Playwright E2E and document-flow smoke CI workflows. New `.github/workflows/smoke.yml` runs `playwright` (standalone Playwright E2E tests with mock backend — chromium, Vite dev server, 1440x900 viewport) and `document-flow` (full Compose stack with Postgres/ES/Qdrant/Meilisearch/Kafka + `scripts/dev/smoke_document_flow.sh` in `SMOKE_MODE=ci`). Playwright report and smoke JSON result uploaded as artifacts on every run. Added `test:e2e` npm script. Updated `docs/development/testing.md` with local document-flow smoke commands. Both jobs prune on path filters and use concurrency cancellation.

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
