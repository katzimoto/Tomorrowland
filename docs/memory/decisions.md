# Tomorrowland Decisions

Shared record for durable architecture, product, and agent workflow decisions.

## 2026-05-29 — BM25 source-scope filtering: Meilisearch filter + post-filter fallback

Status: Active
Source: issue #552

Decision:
- Source-scoped RAG/hybrid retrieval enforces `source_id` on BM25 via a two-layer approach:
  1. **Query-time filter**: `metadata.source_id IN [...]` is composed into the Meilisearch filter expression in `search_rag`, `search_rag_metadata`, and `search_rag_translated`.
  2. **Post-filter fallback**: `_apply_scope_to_bm25` additionally filters out results whose `metadata.source_id` is not in the allowed set, handling stale index records that lack the field.

Reason:
- Qdrant already enforces source scope via `build_qdrant_filter`/`search_filtered`, but BM25/Meilisearch had no equivalent. Hybrid retrieval could merge out-of-source BM25 results into scoped context.
- Meilisearch IN filter naturally excludes null/missing fields, so no special null handling is needed at query time.
- Post-filter provides defense-in-depth for records indexed before `source_id` was populated.

Impact:
- All indexing sites (backfill, worker, slow_worker, index_worker) now populate `metadata.source_id`.
- Settings version bumped to 2 — operators must run backfill/reindex after deploy.
- If backfill is not run, source-scoped queries will return no BM25 results for those sources (fails closed).

## 2026-05-29 — Markdown Office extraction: native implementation, not markitdown package

Status: Active
Source: PR #533, issue #526

Decision:
- DOCX/PPTX/XLSX → Markdown converters implemented natively with python-docx, python-pptx, openpyxl.
- Do not add `markitdown` as a direct dependency.

Reason:
- markitdown 0.1.x requires `magika>=0.6.1,<0.7`; this project requires `magika>=1.0` (core dep for MIME detection).
- Installing both simultaneously downgrades magika and breaks `MimeDetector`.
- The conflict cannot be resolved without either dropping markitdown or degrading MIME detection.

Impact:
- `src/services/extraction/markitdown_extractor.py` contains the native converters.
- If markitdown ships a magika-1.0-compatible release, the internals can be swapped — the `MarkItDownExtractor` interface and `ENABLE_MARKITDOWN` flag are stable.
- No new pyproject.toml deps; uv.lock gains magika 1.0.3 transitive deps (onnxruntime, flatbuffers).

Next action:
- Monitor markitdown releases for magika>=1.0 compatibility.

## 2026-05-27 — Original file storage: move-before-create + connector direct-write

Status: Active
Source: Claude Code session; src/services/pipeline/original_store.py

Decision:
- All connector-fetched files (except audio/*, video/*) are persisted to `files_root/originals/` before the `documents` DB row is created, so `doc.path` always points to a permanent file.
- `move_to_originals(path, mime_type, files_root)` uses `shutil.move()` — O(1) rename on same FS, copy+delete cross-device; idempotent for files already inside `files_root`.
- `ConnectorDocument.fetch_documents()` Protocol accepts `storage_root: Path | None = None`. When provided, connectors write directly to `storage_root`, bypassing tempfiles. Scheduler and sync-now pass `storage_root=files_root / "originals"`. Tier 1 `move_to_originals` still runs as safety net (returns `None` if already inside `files_root`).
- Download route: when `doc.path is None`, falls back to serving `document_payloads.content_text` as a `.txt` file instead of 404.
- Frontend `has_file: bool` on `PreviewResponse` drives download button label ("Download" vs "Download text").

Impact:
- SMB/Atlassian files no longer deleted after extraction (old `_maybe_delete_connector_temp()` in worker still runs but finds the file inside `files_root` → no-op).
- Folder connector path is already persistent — `storage_root` ignored.
- NiFi is event-driven — `storage_root` ignored; inline text docs have no persistent file.
- Audio and video MIME types are explicitly skipped (too large, no useful extraction).

## 2026-05-28 — Extraction: MIME detection is three-layer (Magika → python-magic → mimetypes)

Status: Active
Source: PR #524 (ffe2265); src/services/extraction/mime_detector.py

Decision:
- `MimeDetector.detect()` resolution order:
  1. **Magika** (`magika>=1.0`, core dep) — ML-based, score ≥ 0.80 required. Correctly identifies DOCX/XLSX/PPTX without ZIP inspection. Score 0.80 threshold passes DOCX/XLSX/PPTX/PDF/EPUB (≥0.90); falls through for EML (0.53), plain text (0.49), bare OLE bytes (0.18).
  2. **python-magic** — libmagic content sniff; degrades gracefully if not installed.
  3. **mimetypes.guess_type** + `sniff_office_mime` (stdlib ZIP/OLE) — extension-based fallback.
- Generic-type guard applies to both Magika and python-magic: if the result is `text/plain`, `application/zip`, or `application/octet-stream` and the extension provides a more specific type, the extension wins (e.g. `.eml` → `message/rfc822`).
- Magika singleton is lazy — ONNX model loads on first `identify_path()` call, not at worker startup.
- `_MAGIKA_AVAILABLE` flag preserves full graceful degradation if `magika` package is ever removed.
- Module-level `detect_mime_type()` convenience wrapper used by connectors (unchanged).
- `application/octet-stream` is **not registered** in `ExtractorRegistry` — unknown MIME types return `""`.

Impact:
- Extensionless DOCX/XLSX/PPTX now identified in a single ML call instead of requiring ZIP inspection.
- EPUB no longer confused with plain ZIP by libmagic.
- Tests that exercise python-magic or mimetypes layers must patch `_MAGIKA_AVAILABLE=False` for isolation.

## 2026-05-25 — Extraction: MIME detection uses python-magic + mimetypes fallback

Status: Superseded by 2026-05-28 entry
Source: commit 0ec5226; src/services/extraction/mime_detector.py

## 2026-05-25 — Extraction: OCR and Legacy Office are feature-flagged off by default

Status: Active
Source: commit 0ec5226; src/shared/config.py

Decision:
- `ENABLE_OCR=false` — requires `tesseract-ocr` + `poppler-utils` in PATH and `pip install tomorrowland[ocr]`.
- `ENABLE_LEGACY_OFFICE=false` — requires LibreOffice (`soffice`) in PATH.
- `ENABLE_LANGUAGE_DETECTION=true` — on by default; failures never block extraction (caught with `None` return).
- `ExtractorRegistry` accepts `enable_ocr` and `enable_legacy_office` constructor flags; `runner.py` passes `settings.enable_ocr` / `settings.enable_legacy_office`.

Impact:
- No Docker image changes required for base deployment.
- OCR and LibreOffice extractors lazily import deps inside methods — missing deps degrade to empty string, not exception.

## 2026-05-25 — Extraction: PlainExtractor is charset-aware (UTF-8 → charset-normalizer → latin-1)

Status: Active
Source: commit 0ec5226; src/services/extraction/plain.py

Decision:
- Three-step decode: UTF-8 first; on `UnicodeDecodeError`, try `charset_normalizer.from_path()` (best-match detection); final fallback latin-1 (never raises).
- `charset-normalizer` is already a transitive dependency (via `requests`); no new required dep.
- Latin-1 fallback ensures non-UTF-8 files always produce non-empty text rather than silently returning `""`.

Impact:
- Windows-1252, latin-1, and other legacy encodings now produce readable text instead of empty strings.

## 2026-05-25 — Extraction: language auto-detection uses langdetect (min 100 chars, 0.80 confidence)

Status: Active
Source: commit 0ec5226; src/services/extraction/language.py, src/services/pipeline/worker.py

Decision:
- `LanguageDetector.detect()` uses `langdetect` with `DetectorFactory.seed = 0` (reproducible results).
- Returns `None` for texts under 100 chars or confidence below 0.80.
- Wired into `PipelineWorker._run()` between extraction and translation: if `doc.source_language is None` and detection succeeds, `update_source_language()` is called and `doc` updated in-memory for the rest of the pipeline.
- `documents.language_detected` bool column (migration `v6w7x8y9z0a1`) distinguishes auto-detected from connector-supplied languages.

Impact:
- Documents without a declared source language now get auto-detected language used for chunking and translation.
- Translation quality improves when LibreTranslate receives a known source language vs. "auto".

## 2026-05-24 — BM25 search failures degrade gracefully (no 500)

Status: Active
Source: commit 4ec9bc5 on main; src/services/api/routers/search.py

Decision:
- Both the Meilisearch and Elasticsearch BM25 exception handlers log a warning and continue with `bm25_results=[]` — they do NOT re-raise.
- Result: any transient BM25 backend failure produces vector-only results, not HTTP 500.
- The 400 "input length exceeds" path in the encoder still raises ValueError (job-level error, not request-level).

Impact:
- Search view always loads for users even when Meilisearch or ES is temporarily unavailable.

## 2026-05-24 — Embedding token estimation ratio lowered to 2.0

Status: Active
Source: commit 0347f1c on main; src/services/chunking/splitter.py, src/services/search/encoder.py

Decision:
- `_TOKEN_ESTIMATE_RATIO` in `splitter.py` changed from 4.0 to 2.0. Conservative for all scripts: Hebrew/Arabic/CJK can be 1–2 chars/token; the old 4.0 ratio let oversized chunks pass the `_ensure_max_tokens` gate and exceed Ollama's `num_ctx`.
- `OllamaEmbeddingEncoder._embed_batch()` uses `chunk_text(text, max_tokens=self._max_tokens)` (not naive char split) as a last-resort safety net when a text still exceeds the limit at encode time. Sub-chunk vectors are mean-pooled back to one vector per input text.
- `EMBEDDING_MAX_TOKENS` raised 1024→2048 in `.env` to match `nomic-embed-text`'s training context and give 2× headroom before truncation fires.

Impact:
- Ollama "input length exceeds the context length" errors eliminated for all supported scripts.
- English chunks slightly smaller (up to 50%) but well within model context.

## 2026-05-24 — SearchResults wrapper for meili_provider.search()

Status: Active
Source: commit 8dfa896 on `claude/refine-local-plan-ohFc5`

Decision:
- `meili_provider.search()` returns `SearchResults(results: list[SearchResult], facets: dict[str, dict[str, int]])` instead of a bare list.
- Callers unpack: `bm25_results = meili_results.results`, `meili_facets = meili_results.facets`.
- Short-circuit path (no-group user, `needs_acl_short_circuit`) returns `SearchResults(results=[], facets={})`.
- `SearchResponse` (API schema) carries `facets` with `default_factory=dict` so the field is always present.

Impact:
- Any future caller of `meili_provider.search()` must use `.results` not direct iteration.
- Facets are available in the API response without a separate endpoint.

## 2026-05-24 — Meilisearch highlight rendering via dangerouslySetInnerHTML

Status: Active
Source: commit 8dfa896 on `claude/refine-local-plan-ohFc5`

Decision:
- `ResultRow` renders `title` and `snippet` with `dangerouslySetInnerHTML` + `highlightHtml()` sanitizer.
- `highlightHtml()` strips all HTML tags except `<mark>` and `</mark>` via regex: `raw.replace(/<(?!\/?mark\b)[^>]*>/gi, "")`.
- Meilisearch is configured with `highlightPreTag: "<mark>"` / `highlightPostTag: "</mark>"`. Only these tags are trusted; all other tags from the search index are stripped.
- `mark` styled in CSS: `background: oklch(97% 0.15 90)`, `border-radius: 2px`, `padding: 0 1px`.

Impact:
- Any component rendering Meilisearch `_formatted.*` fields must use `highlightHtml()` before injecting HTML.
- Do not use `dangerouslySetInnerHTML` on raw Meilisearch output without `highlightHtml()` first.

## 2026-05-23 — Pipeline efficiency optimizations

Status: Active
Source: OpenCode session (chat summary)

Decision:
- Embedding encoding: collect all chunk texts → single `encode_batch()` call (was per-chunk HTTP call). Reduces N Ollama round-trips to 1 per document.
- Intelligence tasks: `ThreadPoolExecutor` runs summarize, entities, tags, key_points concurrently (was sequential for-loop). Each task is independent on same content.
- Map-reduce summarization: chunk summaries parallelized via ThreadPoolExecutor (max 4 workers).
- Ollama cache: `KEEP_ALIVE=4h`, `MAX_LOADED_MODELS=2` — both mistral and nomic-embed-text stay in memory, eliminating model swap latency (30-90s per cycle).
- Timeouts: generate 300s, embed 180s (was 120s/60s) — models need time to load on first request.
- Error visibility: `_sanitize_error` now includes first line of `str(exc)` alongside class name.
- Summary empty fallback: uses first sentence of document when LLM returns empty/whitespace.

Impact:
- Document processing wall-clock reduced: embedding batch (~N× faster), intelligence tasks (~3× faster), map-reduce (~4× faster).
- No model swapping between chat and embedding requests — both loaded simultaneously.
- Admin UI now shows actionable errors like `ReadTimeout: timed out` instead of just `ReadTimeout`.

## 2026-05-23 — UI full-width layout

Status: Active
Source: OpenCode session (chat summary)

Decision:
- Admin pages (Sources, Detail, Edit, Hub): `max-width` removed, `width: 100%` — fills screen.
- Expertise, History, Notifications: `max-width` removed.
- Search results: `max-width` bumped to 1200px.
- Document table columns: Title 42%, Type 8%, Lang 6%, Progress 18%, State auto.
- Duration column ticks live every 1s for running jobs.

## 2026-05-23 — LLM prompt quality improvements

Status: Active
Source: OpenCode session (chat summary)

Decision:
- Summarization prompt: structured JSON format with `summary`, `bullets`, `language`, `document_type` fields.
- Entity extraction prompt: explicit `{name, type}` format with valid types listed.
- Auto-tag prompt: example tags added (`["contract law", "data privacy", "vendor risk"]`), instruction to avoid generic labels.

## 2026-05-23 — Boolean-integer SQL guard + PostgreSQL CI test job

Status: Active
Source: OpenCode session (chat summary)

Decision:
- Boolean columns (`is_private`, `is_latest`, `is_admin`, etc.) must use `true`/`false` literals or bound boolean params in raw SQL — never `0`/`1`.
- `scripts/check-boolean-int-sql.py` AST-checks all `sa.text()` calls for the pattern; runs in CI quality job.
- New `tests-postgres` CI job runs full test suite against PostgreSQL 16 (PGTEST=1).
- `conftest.py` reads `PGTEST` env var to switch from SQLite to PostgreSQL.

Impact:
- SQLite integration tests previously masked PostgreSQL type errors.
- Lint check catches the pattern at dev time; PostgreSQL job catches at CI time.

## 2026-05-23 — Related documents show structured reasons (#482)

Status: Done
Source: issue #482

Decision:
- `RelatedService.related_documents()` computes `reasons` array per candidate: semantic_similarity, shared_entities, shared_tags, same_source.
- Relation score = 0.60×semantic + 0.15×entities + 0.10×tags + 0.10×metadata (reused `RELATED_OVERLAP_BONUS_PER_MATCH`/`CAP` constants).
- Frontend shows compact reason pills + expandable "Why related?" panel with entity/tag lists.

Impact:
- Users can see why documents are related instead of trusting an opaque score.
- Pre-existing `RelatedRepository.get_document_tags_and_entities()` wired in (was dead code).

## 2026-05-23 — Python tooling migrated to uv

Status: Active
Source: OpenCode session (chat summary)

Decision:
- All Python commands use `uv run` prefix. `uv.lock` generated from `pyproject.toml`.
- Dockerfile copies uv binary from `ghcr.io/astral-sh/uv:latest` and uses `uv pip install --system`.
- CI workflows use `astral-sh/setup-uv@v5` action; `cache: pip` removed; all `pip install` → `uv pip install --system`.

Impact:
- Resolution time: 15ms vs ~30s for pip. Lockfile ensures reproducible installs.
- Docker build no longer upgrades pip first. CI cache handled by setup-uv.

## 2026-05-23 — Admin source documents view with pipeline state

Status: Active
Source: OpenCode session (chat summary)

Decision:
- `GET /admin/sources/{source_id}/documents` joins documents + pipeline_jobs aggregation, returns per-document counts + individual job list.
- Frontend shows progress bar (green/yellow/red), expandable rows with per-job details (type, status, attempts, stage, error).
- Auto-refresh every 10s via TanStack Query `refetchInterval`.
- `POST /admin/documents/{document_id}/requeue` resets dead-letter jobs to pending.
- `DELETE /admin/documents/{document_id}` and `DELETE /admin/sources/{source_id}` cascade-delete.

Impact:
- Admin can monitor pipeline progress per source without checking worker logs.
- Failed documents can be requeued from the UI instead of using CLI/DLQ admin.

## 2026-05-23 — Chat feature flags default to True

Status: Active
Source: OpenCode session (chat summary)

Decision:
- All 6 `feature_document_chat_*` settings default to `True` in `shared/config.py`. Chat is now on by default; env vars can opt-out.
- `/qa` route removed from frontend (nav + routes). Chat replaces Q&A.

Impact:
- No env vars needed for basic chat, streaming, query rewrite, reranker, metadata search, or translated text.
- Backend `/qa` route still exists but is unreachable from UI.

Next action:
- Remove backend `/qa` route when chat is proven stable.

## 2026-05-23 — Qdrant collection auto-creates on search

Status: Active
Source: OpenCode session (chat summary)

Decision:
- `create_collection_if_not_exists()` called at the start of `search()` and `search_filtered()` in `QdrantSearchClient`. Previously only called during `upsert_chunks()`, causing queries to fail before first document was indexed.

Impact:
- RAG/chat/search no longer return "Collection doesn't exist" on fresh deployments.
- Collection is created lazily on first query (same dimension as the encoder).

## 2026-05-23 — SSE streaming uses manual connection management

Status: Active
Source: OpenCode session (chat summary)

Decision:
- `create_message_stream()` in `chat.py` uses `engine.connect()` + `connection.begin()` instead of `with engine.begin()`. The `try/finally` in the generator closes the connection after streaming completes.
- Pattern: synchronous setup uses the connection; generator captures closures; cleanup in `finally` block.

Impact:
- `ResourceClosedError` no longer occurs when SSE generator tries to persist the assistant message on the `done` event.
- Non-streaming endpoint unchanged (sync flow works fine with `with` block).

## 2026-05-23 — Admin source schedule field (cron, stored only)

Status: Active
Source: OpenCode session (chat summary)

Decision:
- `schedule` column (TEXT, nullable) added to `ingestion_sources`. Accepts cron expressions.
- Backend: `UpdateSourceRequest` includes `schedule`; list/get/update all handle it.
- Frontend: edit page shows cron input; detail page displays schedule value.
- No scheduler runner yet — field is stored for future execution.

Impact:
- Sources can be assigned cron schedules. Execution follow-up required.

Next action:
- Build scheduler runner (pipeline or separate worker) that reads `schedule` and triggers `sync-now`.

## 2026-05-21 — Virtualization uses react-window v2 with List + ARIA tables

Status: Active
Source: issue #450, PR #464

Decision:
- Use `react-window@2` for text/table virtualization. v2 API: `List` (not `FixedSizeList`), `rowCount`/`rowHeight`/`rowComponent` props, `rowProps={{}}` required.
- Virtualized TablePreview uses ARIA role-based table (`role="table"`, `role="rowgroup"`, etc.) instead of native `<table>` elements, because react-window renders flat `div` children.
- Always pass `rowProps={{}}` to `List` — v2 crashes with `Object.values(null)` if rowProps is undefined.

Impact:
- Non-virtualized TablePreview path (<1K rows) keeps native `<table>` for semantics.
- Virtualization threshold: 10K lines for TextPreview, 1K rows for TablePreview.
- Test setup must mock `ResizeObserver` globally (jsdom compat).

Next action:
- Consider browser-based virtualization verification (#451).

## 2026-05-21 — TextPreview is API-driven via docId prop

Status: Active
Source: issue #441, PR #455

Decision:
- `TextPreview` accepts an optional `docId` prop. When provided, it fetches full text from `GET /documents/{document_id}/text` in 10K chunks instead of using the `preview.snippet` field.
- The `text` prop is kept as an optional static fallback for backward compat and tests.
- `PreviewPane` passes `docId={preview.document_id}` for all text-based MIME dispatches.

Impact:
- New text-based renderers should follow the same `docId`-driven fetch pattern.
- Do not pass `text={preview.snippet}` to `TextPreview` from `PreviewPane` — that bypasses the full-text API.

Next action:
- When #443 adds a fidelity mode switcher, thread `translationVersionId` and `showOriginal` through PreviewPane → TextPreview.

## 2026-05-21 — Document viewer branching strategy

Status: Active
Source: docs/design/document-viewer-implementation-guardrails.md, issue #441

Decision:
- #440 targets `main` directly (security fix).
- #441–#451 target `feature/document-viewer` integration branch.
- #446 (Office conversion) should use a sub-branch `feature/document-viewer/office-conversion`.
- Git does not allow a branch named `feature/document-viewer/X` while `feature/document-viewer` also exists — use flat names like `feat/442-pdfjs-viewer` instead.

Impact:
- All document-viewer PRs must target `feature/document-viewer`, not `main`.
- Sub-branch naming: prefer `feat/<issue>-<short-name>` over path-style names.

Next action:
- Keep enforcing until the feature branch merges to `main`.

## 2026-05-21 — Document Chat: TanStack Query v5 message seeding pattern

Status: Active
Source: issue #473, `feature/document-chat`; ChatWindow.tsx

Decision:
- TanStack Query v5 removed `onSuccess`/`onError`/`onSettled` from `useQuery` options. Use `useEffect` instead.
- Chat message state is seeded once from the query result using a ref guard (`seededForSession = useRef<string | null>(null)`). The ref stores the last session ID for which messages were seeded.
- After seeding, messages are managed entirely in local React state to allow optimistic updates without query invalidation.
- Session change resets both input and the ref guard via a separate `useEffect` on `session.id`.
- `staleTime: 5 * 60_000` on the chat-session query prevents background refetch from overwriting locally-appended messages during an active chat.

Impact:
- Any future query-driven local state that allows offline mutations must follow this seed-once pattern.
- Never use `queryClient.setQueryData` to append optimistic chat messages — that would break the seed-once guard.

Next action:
- Phase C streaming changes should preserve the seed-once guard.

## 2026-05-21 — Document Chat: backend DELETE returns 200 JSON (not 204)

Status: Active
Source: issue #473, `src/services/api/routers/chat.py`

Decision:
- `DELETE /chat/sessions/{id}` returns `{"ok": true}` with HTTP 200, not 204 No Content.
- `deleteChatSession()` in `api/chat.ts` is typed as `Promise<{ ok: boolean }>`, not `Promise<void>`.
- This differs from the standard REST convention used by other delete endpoints in the codebase.

Impact:
- If the backend is ever normalized to 204, update `deleteChatSession` return type and callers.

## 2026-05-21 — Document Chat: dual-gate feature flag in tests

Status: Active
Source: issue #473, `tests/integration/test_chat_api.py`, `src/shared/feature_flags.py`

Decision:
- Every `/chat` route checks **two** guards: `Settings.feature_document_chat` AND `system_config.feature.document_chat` in the DB. Both must be `True` or every endpoint returns 404.
- The foundation migration seeds `feature.document_chat = False` in `system_config` (production safety default).
- Integration tests must override **both**: pass `feature_document_chat=True` to `Settings(...)` AND run `INSERT OR REPLACE INTO system_config (key, value) VALUES ('feature.document_chat', 'true')` in the test setup fixture.
- `.env` sets `FEATURE_MEILISEARCH_SEARCH=true`; `_settings()` helpers must explicitly override `feature_meilisearch_search=False` to prevent test workers attempting a Docker-DNS connection to `meilisearch:7700`.

Impact:
- Any new feature with a similar dual-gate pattern must be handled the same way in tests.
- Skipping either override produces 404 on every request — a confusing failure mode when the feature code itself is correct.

Next action:
- Document this pattern in `docs/context/chat.md` if a context file is created for Phase C.

## 2026-05-21 — Document Chat: typed UUID path params

Status: Active
Source: issue #473, `src/services/api/routers/chat.py`

Decision:
- Route handlers that accept a resource ID path param must type it as `UUID` (not `str`) in FastAPI.
- FastAPI validates the param on entry and returns 422 for malformed input; manual `UUID(hex=str_param)` would raise unhandled `ValueError` → 500.
- The pattern: `def get_session(session_id: UUID, ...)` with no manual conversion; pass `session_id` directly to repository methods that accept `UUID`.

Impact:
- All 4 chat route handlers (`get_session`, `update_session`, `delete_session`, `create_message`) follow this pattern.
- Apply the same pattern to any new route with a UUID path segment.

## 2026-05-29 — Citation grounding: text-search chunk location mapping

Status: Active
Source: PR #556, issue #530

Decision:
- Chunk-to-location mapping uses `resolve_chunk_locations()` — searches for normalized chunk text within the original document text — rather than modifying the chunker to track source segment indices.
- Location data is stored in a new `extraction_metadata` TEXT (JSON) column on `document_payloads`, separate from `content_text`.
- Translated chunks carry no location metadata (sentence boundaries differ between languages).

Reason:
- `chunk_text()` operates on sentence-split tokens and joins with `" "`; modifying it to track per-chunk origin segments would change the chunking internals and risk breaking existing behavior.
- `extraction_metadata` is a nullable additive column — existing rows are unaffected.
- Translation preserves semantic meaning but not exact character offsets; location metadata would be misleading.

Impact:
- Cross-boundary chunks (spanning page/slide/paragraph breaks) silently degrade to `(0, 0)` with no location — `_find_chunk_positions` normalizes whitespace but searches in un-normalized original text (documented trade-off).
- Existing documents need a reindex pass after deploy to populate location fields.

---

## 2026-05-20 — Repo memory is the durable record

Status: Active
Source: project manager chat summary

Decision:
- Store durable project memory in `docs/memory/*.md`.
- Use optional indexing only as a retrieval helper.
- Keep important decisions visible in normal code review.

Impact:
- Claude, OpenCode, and Codex should read relevant memory before substantial work.
- New durable decisions should be added here in compact form.

Next action:
- Keep this file short and update stale entries when decisions change.
