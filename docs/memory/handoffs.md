# Tomorrowland Handoffs

Shared record for concise cross-agent handoffs that remain useful after a chat or tool session ends.

## 2026-05-26 — fix: translation sweep — read-path, 6 bugs, TOCTOU race, xlsx, attachments

Status: Done — main, commits 263171c + e0c74fb + ab3e3ac
Source: Claude Code session

All translation bugs found in a systematic audit and fixed across three commits.

**Changed files:**
- `src/services/preview/service.py` — read-path IS DISTINCT FROM guard in all 3 `get_translated_text` branches; atomic INSERT ON CONFLICT in `_maybe_auto_enrich`
- `src/services/documents/repository.py` — `list_versions` LEFT JOIN + no-op exclusion
- `src/services/pipeline/slow_worker.py` — no-op + empty guard in `_run_versioned`
- `src/services/api/routers/documents.py` — `request_translation` RabbitMQ publish + `target_lang or "en"` label fix; download endpoint accepts `translation_version_id`
- `src/services/extraction/xlsx.py` — `data_only=True`, `read_only=True`, broad exception catch
- `src/services/extraction/registry.py` — macro-enabled XLSX aliases; `has_extractor()` method
- `src/services/pipeline/worker.py` — `_process_attachments` uses `has_extractor()` not `get()-is-None`
- `frontend/src/api/documents.ts` — `getDownloadUrl` accepts `translationVersionId`
- `frontend/src/features/documents/DocumentToolbar.tsx` — passes `selectedVersionId` to download
- `frontend/src/features/documents/DocumentPage.tsx` — `"processing"` in polling check
- `frontend/src/features/documents/TranslationVersionSelector.tsx` — `"processing"` in `hasInProgressVersions`
- `migrations/versions/x8y9z0a1b2c3_dtv_unique_active_per_type.py` — partial unique index
- `tests/unit/test_pipeline_worker.py` — `has_extractor()` added to `_FakeExtractorRegistry`

**Verification:** 124 backend unit tests pass; `tsc --noEmit` clean; `ruff check` clean.

**Deploy note:** Migration `x8y9z0a1b2c3` must run before restart — adds partial unique index.

**Remaining watch items:**
- Attachment GC: `files_root/attachments/` grows without bound on doc delete.
- `request_translation` duplicate guard: uses `find_pending_or_running` SELECT then INSERT — not atomic. Lower risk than auto-enrich (user-triggered, not concurrent) but the same partial index now enforces uniqueness at DB level as a backstop.

## 2026-05-26 — fix: translation mode shows original-language text + octet-stream preview

Status: Done — branch feat/design-system-update, commits 0c10cca + 0947937 (pushed)
Source: Claude Code session

Three translation bugs fixed and one preview improvement made:

**1. Navigation reset (frontend — DocumentPage.tsx, TranslationVersionSelector.tsx)**
- `selectedVersionId` was not cleared on `docId` change; `TranslationVersionSelector` `if (selectedVersionId !== undefined) return` guard blocked auto-selection on every doc after the first.
- Fix: reset `selectedVersionId(undefined)` + `hadInProgressRef.current` in docId effect; add docId-keyed effect in selector resetting `initialSelectDoneRef` + `hadInProgressRef`.

**2. Empty-translation fallback (backend — src/services/pipeline/runner.py)**
- `_version_text = translated or extracted` — when translation returned `""`, a version was created with `translated_text = extracted_text` (original-language text). Translation tab showed source language.
- Fix: `_version_text = translated_text` only; empty → no version → tab hidden. Added info log. Unit test `test_translation_version_skipped_when_translated_is_empty` updated (was asserting buggy behavior).

**3. No-op synthetic version (backend — src/services/api/routers/documents.py)**
- After df93072 no-op detection, `document_payloads.translated_text = content_text` for no-op docs; synthetic fallback had no guard → translation tab appeared with original text.
- Fix: `AND dp.translated_text IS DISTINCT FROM dp.content_text` in fallback WHERE clause.

**4. application/octet-stream preview (frontend — PreviewPane.tsx, GenericPreview.tsx)**
- "Cannot be previewed" error wall replaced with extension-based routing (CODE_EXTENSIONS, TEXT_EXTENSIONS, MD_EXTENSIONS) and `GenericPreview` fallback showing extracted text + MIME banner + download link.
- New file: `src/features/documents/renderers/GenericPreview.tsx`.

Verification: `tsc --noEmit` clean; 21 pipeline runner unit tests pass; 5 pre-existing frontend test failures unchanged.

Risks / follow-ups:
- Existing documents in DB with `translated_text = content_text` in `document_translation_versions` (created before df93072) still surface as "available" via the real version record — `get_translated_text` returns original text. A data-cleanup pass or `get_translated_text` guard would close this edge case.
- Attachment GC still missing (files_root/attachments/ grows without bound on doc delete).

## 2026-05-26 — feat: design system update — search + document UI

Status: Done — commit c62094d on feat/design-system-update (pushed, PR ready)
Source: Tomorrowland Design System.zip + Claude Code session

Changed files (all pass tsc + vite build, zero errors):
- `frontend/src/features/search/ResultRow.tsx` — source label moved to left column as `<Badge variant="source">`; tags, overflow count, version, translation quality all use `<Badge>` instead of dot-separated inline spans
- `frontend/src/features/search/ResultRow.module.css` — left column is column-direction to stack mime icon + source badge; snippet expands to 2 lines; meta row uses gap tokens; preview button always visible; highlight marks use oklch amber tint
- `frontend/src/features/search/SearchPage.module.css` — active mode button gets `box-shadow`; keyboard help bar gains `border-bottom`, bg token, `font-size-meta`
- `frontend/src/features/documents/InsightPane.module.css` — section headings get `text-transform: uppercase; letter-spacing: 0.04em`
- `frontend/src/features/documents/DocumentPage.module.css` — insight column `min-width: 360px → 300px` per spec

Design system zip coverage: all 52 zip files now match project. One valid exception: InsightPane.module.css retains `.dotList` / `.dotList .item` / `.dotList .sep` classes used by InsightPane.tsx that the zip snapshot predates.

Known follow-up:
- `.left` column is `width: 36px` with a `white-space: nowrap` source badge — long source labels (e.g. "Confluence") will visually overflow. Widening to `fit-content` or adding `overflow: hidden` is a safe follow-up if it causes layout collisions in practice.

## 2026-05-25 — fix: translation no-op + download JSON

Status: Done — committed to main
Source: Claude Code session

Changed files:
- `src/services/pipeline/worker.py` — `ProcessResult` gets `translation_quality: str | None`; warning logs; `attachment_store: Path | None` param; `_process_attachments` saves to persistent path when store is set
- `src/services/pipeline/runner.py` — version creation gated on `_translation_was_no_op`; passes `attachment_store=settings.files_root/"attachments"` in `__main__`
- `src/services/api/routers/admin/ingestion.py` — `logger` added; warns when `source_language` is None at ingest time
- `frontend/src/features/documents/DocumentToolbar.tsx` — `useToast` + `r.ok` check in download handler
- `frontend/src/i18n/locales/en.ts` / `he.ts` — `downloadError` key added
- `tests/unit/test_pipeline_runner.py` — 3 `ProcessResult` calls updated with `translation_quality`

Key invariant: a `document_translation_versions` record is now only created when `translated_text` is non-empty AND differs from `extracted_text`. The EML/archive fallback (empty translated → use extracted) is kept but no longer for same-text no-ops.

Remaining risk:
- `files_root/attachments/` files not GC'd on document delete
- `PdfViewer` loads via `pdfjsLib.getDocument(url)` without Bearer token — PDF in-viewer rendering still fails for auth-protected endpoint (separate issue)
- Scanned PDFs still need `ENABLE_OCR=true` for any text extraction

## 2026-05-25 — feat: parsers architecture — full file-type extraction & translation coverage

Status: Done — commit 0ec5226 on main
Source: Claude Code session

What changed:
- `src/services/extraction/mime_detector.py` — **new** MimeDetector (python-magic + mimetypes fallback)
- `src/services/extraction/opendocument.py` — **new** OdsExtractor + OdpExtractor
- `src/services/extraction/epub.py` — **new** EpubExtractor (ebooklib)
- `src/services/extraction/ocr.py` — **new** OcrExtractor (pytesseract + Pillow; `ENABLE_OCR=false`)
- `src/services/extraction/legacy_office.py` — **new** LegacyOfficeExtractor (LibreOffice subprocess; `ENABLE_LEGACY_OFFICE=false`)
- `src/services/extraction/language.py` — **new** LanguageDetector (langdetect; `ENABLE_LANGUAGE_DETECTION=true`)
- `src/services/extraction/registry.py` — alias map; ODS/ODP/EPUB registered; removed `octet-stream` fallback; feature-flagged OCR/LegacyOffice
- `src/services/extraction/plain.py` — charset-aware 3-step decode
- `src/services/extraction/pdf.py` — `ocr_fallback` flag + `_ocr_pdf()` helper
- `src/services/connectors/folder.py`, `smb.py` — use `detect_mime_type()` instead of `mimetypes.guess_type()`
- `src/services/pipeline/worker.py` — language detection injected; `lang_detector` + `enable_language_detection` constructor params
- `src/services/documents/repository.py` — `update_source_language()` added; `_row_to_model` maps `language_detected`
- `src/services/documents/models.py` — `language_detected: bool = False` on DocumentRow
- `src/shared/config.py` — `enable_ocr`, `enable_legacy_office`, `enable_language_detection` flags
- `src/services/pipeline/runner.py` — passes feature flags to ExtractorRegistry and PipelineWorker
- `migrations/versions/v6w7x8y9z0a1_add_language_detected_flag.py` — **new** `language_detected` bool column on documents
- `pyproject.toml` — added charset-normalizer, ebooklib, langdetect, python-magic; `[ocr]` optional group
- 14 new/updated test files (54 extraction unit tests total)

Verification:
- `ruff check` — clean
- `mypy --strict` — clean (29 source files)
- 54 unit tests — all passed

Open risks:
- `octet-stream` fallback removed — any connector explicitly setting `mime_type=application/octet-stream` now gets no extractor. MimeDetector mitigates this for folder/SMB.
- OCR/LibreOffice off by default; Docker image updates required before enabling.
- Migration `v6w7x8y9z0a1` adds `language_detected` column — additive, safe to roll back.

Next agent prompt:
- No open items. Pick up next issue from release queue in AGENTS.md.
- Optional follow-up: backfill job to re-process documents with empty `extracted_text` (previously unregistered MIME types).

---

## 2026-05-25 — Fix: EML translation version silently skipped on empty translator response

Status: Done — committed to main
Source: Claude Code session

**Bug:** `runner.py::_run_process_job` guarded translation-version creation with
`if process_result.translated_text:`. `LibreTranslateClient.translate()` returns
`str(data["translatedText"])` from the JSON response — if LibreTranslate returns
`{"translatedText": ""}` (empty string) for a document with valid extracted content
(observed with EML files whose English headers bias auto-detection), `translated_text`
was falsy, so no `document_translation_versions` row was ever written and the UI
showed no translation.

**Fix:** One-line guard change in `runner.py`:
```python
_version_text = process_result.translated_text or process_result.extracted_text
if _version_text:
    ...update_version_status(..., translated_text=_version_text)
```
Falls back to `extracted_text` so the UI always receives something. Both empty → skip
(nothing to store). Also added `self._connection = None` to `_FakeJobRepo` so the
version-repo path can be properly patched in unit tests.

**Files changed:** `src/services/pipeline/runner.py`, `tests/unit/test_pipeline_runner.py`

**Verification:** 39 unit tests pass (runner, extraction, pipeline worker).

**Remaining:** Bug 2 (English-header bias in LibreTranslate auto-detection for EML)
is still open — body text should be passed separately from headers to avoid
misidentification. Not addressed in this fix.

---

## 2026-05-25 — Fix: Alembic multiple-heads on startup

Status: Done
Source: Claude Code session

**Symptom:** `migrate-1 | FAILED: Multiple head revisions are present for given argument 'head'`

**Root cause:** `2026_05_23_1200_pipeline_jobs_stage_rabbit.py` (`a1b2c3d4e5f6`) and
`v6w7x8y9z0a1_add_language_detected_flag.py` (`v6w7x8y9z0a1`) both descended from
`u5v6w7x8y9z0` — merged in separate branches without awareness of each other.

**Fix:** `migrations/versions/w7x8y9z0a1b2_merge_rabbit_and_language_flag.py` — empty
merge migration, `down_revision = ("a1b2c3d4e5f6", "v6w7x8y9z0a1")`. No schema changes.
The two forks touch disjoint tables (`pipeline_jobs` vs `documents`), so no conflict.

**Pattern to avoid:** When merging a feature branch that adds a migration, always run
`alembic heads` before the merge and add a merge migration if count > 1.

---

## 2026-05-25 — Fix: EML (and EPUB) parsed with wrong extractor due to libmagic generic result

Status: Done
Source: Claude Code session

**Symptom:** EML files "weren't parsed" (garbled content) and appeared to not exist in
the source documents view. EPUB files similarly could land on `ZipExtractor`.

**Root cause:** `MimeDetector.detect()` returned libmagic's result immediately for anything
non-`application/octet-stream`. libmagic classifies EML as `text/plain` (it's a text format)
and EPUB as `application/zip` (it's a ZIP). This caused `PlainExtractor` / `ZipExtractor`
to be used instead of `EmlExtractor` / `EpubExtractor`, and attachment extraction was
silently skipped (PlainExtractor has no `extract_attachments`).

**Fix:** `src/services/extraction/mime_detector.py` — after libmagic returns a *generic*
type (`text/plain`, `application/zip`, `application/octet-stream`), prefer
`mimetypes.guess_type` when it returns a more specific type for the file extension.
Non-generic libmagic results (e.g. `application/pdf` for a `.txt` file) are still trusted.

**Files changed:**
- `src/services/extraction/mime_detector.py` — `_GENERIC_TYPES` frozenset + fallback logic
- `tests/unit/test_extraction_mime_detector.py` — 2 new tests (EML and EPUB cases)

**Follow-up for "doesn't appear":** Likely dedup — EML docs were synced before the fix
with `mime_type=text/plain` and empty/garbled content. Delete those rows or trigger a
re-sync with content changes so SHA256 differs and `doc_repo.create()` re-creates them.

---

## 2026-05-25 — Fix: MIME alias/detection gaps for .yaml, .msg, .rst, .py, .js, .ts, .log, .toml

Status: Done
Source: Claude Code session — follow-up audit of EML fix

**Root cause:** Two complementary gaps:
1. `_ALIASES` in `registry.py` was missing several types that stdlib `mimetypes` emits
   (e.g. `application/yaml` for .yaml, `text/prs.fallenstein.rst` for .rst) and libmagic
   compound-document types for .msg (`application/CDFV2`, `application/x-ole-storage`).
2. `mimetypes` stdlib has no entry for `.msg`, `.log`, `.ini`, `.conf`, `.toml` — these
   fell to `application/octet-stream` when libmagic was unavailable.

**Files changed:**
- `src/services/extraction/registry.py` — 9 new aliases added to `_ALIASES`
- `src/services/extraction/mime_detector.py` — 5 `mimetypes.add_type()` calls at module
  init to patch stdlib gaps (.msg → application/vnd.ms-outlook, .log/.ini/.conf → text/plain,
  .toml → application/toml)

**Intentional non-coverage:** `.7z`, `.rar`, `.odg`, `.odf`, `.gif` — no extractor exists
and adding one is out of scope. `.gz` (standalone, no .tar prefix) and `.bz2` similarly.

---

## 2026-05-25 — Feat: GenericExtractor fallback for unrecognised file types

Status: Done — commit dc02c66 on main
Source: Claude Code session

`ExtractorRegistry.extract()` now falls back to `GenericExtractor` instead of returning
`""` when no specific extractor matches. `GenericExtractor` tries UTF-8 then
charset-normalizer; it deliberately omits the latin-1 final step used by `PlainExtractor`
so binary files (images, executables) still produce `""` rather than garbage in the index.
`registry.get()` is unchanged — still returns `None` for unregistered types (used by
attachment extraction gating in `worker.py`).

**Files:** `src/services/extraction/generic.py` (new), `registry.py` (fallback wired in),
`tests/unit/test_extraction_registry.py` (updated + binary-safety test).

---

## 2026-05-25 — Fix: original document view showed translated content

Status: Done — commit 69c8aa3 on main
Source: Claude Code session

**Bug:** `PreviewPane.tsx` only threaded `showOriginal` in its first `if`-block
(extracted/translation/original+HTML). Plain text, CSV, Word, RTF, Markdown, and
code files fell through to per-mime branches that called `TextPreview`, `CodeViewer`,
and `MarkdownPreview` without the flag. Backend defaults `show_original=False`, so
those renderers silently returned translated content even when `activeMode === "original"`.

**Fix:** Pass `showOriginal={activeMode !== "translation"}` at every `TextPreview`,
`CodeViewer`, and `MarkdownPreview` callsite in `PreviewPane`. Added `showOriginal`
prop + `queryKey` slot to `CodeViewer` and `MarkdownPreview`. 88 unit tests pass.

**Files changed:** `PreviewPane.tsx`, `CodeViewer.tsx`, `MarkdownPreview.tsx`

---

## 2026-05-25 — Fix: auto-enrich fired on every document at index time

Status: Done — committed to main
Source: Claude Code session

**Bug:** `index_worker.py` called `publisher.publish_enrich()` unconditionally for every
document after indexing, bypassing the `auto_enrich_threshold` (default 5 views) entirely.

**Fix:** Removed 3 lines from `src/services/pipeline/index_worker.py` — the unconditional
`publish_enrich()` call after `publish_alert()`.

**Correct paths:**
- Auto-enrich: `PreviewService._maybe_auto_enrich()` fires from the `/preview/{document_id}`
  endpoint when `view_count >= threshold` and quality is not already `high`/`pending_high`.
- Manual enrich: `POST /documents/{document_id}/translate` → enqueues `enrich_document` job directly.

**Verification:** 31 unit tests pass (index worker, slow worker, rabbit client).

Next agent prompt:
- No open items from this session. Pick up next issue from AGENTS.md release queue.

## 2026-05-25 — Unit test suite cleanup

Status: Done — commits f4217a5, a8106d0, 09c300e on main
Source: Claude Code session

Result: 660 passed / 0 failed unit tests (was 638 / 21).

Key pattern established: **always pass `_env_file=None` to `Settings(...)` in unit tests**.
The project `.env` sets `FEATURE_MEILISEARCH_SEARCH=true`, `RABBITMQ_URL`, `EMBEDDING_URL`
and other container values — without `_env_file=None` these leak into every `Settings()` call
and break tests that expect code defaults or deleted env vars.

Other fixes:
- `alert_consumer.py::main()` now uses `build_encoder(settings)` instead of `DeterministicTestEncoder()`.
- Patch targets for lazily-imported modules must use the module path directly (e.g. `meilisearch.Client` not `services.api.main.meilisearch.Client`).
- Test fakes that back prod code accessing `_connection` must expose `_connection = None`.
- `STANDARD_VOLUMES` in `test_compose_volumes.py` updated to `ollama_llm_data` + `ollama_embed_data`.

Next agent prompt:
- Pick up next issue from release queue in AGENTS.md — no open items from this session.

## 2026-05-25 — Search + infra hardening sprint

Status: Done — all merged to main
Source: Claude Code session

What changed:
- `docker/ollama-llm.Dockerfile`, `docker/ollama-embed.Dockerfile` — new; split LLM and embed containers
- `docker-compose.yml` — `ollama` removed; `ollama-llm` + `ollama-embed` added with correct `depends_on`
- `src/shared/config.py` — `ollama_utility_model`, `ollama_reranker_model`, `effective_utility_model`, `effective_reranker_model`, `search_embedding_timeout`
- `src/services/search/factory.py` — `build_encoder(..., *, timeout=None)` override
- `src/services/api/routers/search.py` — pass `search_embedding_timeout` to encoder; fix `_map_sort` to resolve camelCase via `_MEILI_SORT_MAP` before appending direction
- `src/services/intelligence/worker.py`, `message_service.py`, `reranker.py`, `chat.py`, consumers — role-based model routing (utility/reranker)
- `frontend/src/api/expertise.ts`, `ExpertiseResult.tsx` — removed stale `comments` signal
- `tests/unit/test_model_routing.py` — 17 routing tests
- `tests/unit/test_search_factory.py` — 4 timeout override tests; `_env_file=None` fix
- `tests/unit/test_search_sort.py` — 10 parametrised `_map_sort` tests (new)
- `.env.example`, `.env.airgap.example` — `SEARCH_EMBEDDING_TIMEOUT`, split Ollama vars

Verification:
- All new tests pass. Pre-existing coverage-threshold noise only.

Open risks:
- Operator must `docker compose build ollama-llm ollama-embed` on first deploy after the split.
- `ollama_data` volume not migrated automatically (models must be re-pulled).

Next agent prompt:
- Pick up next issue from release queue in AGENTS.md — no open items from this sprint.

## 2026-05-24 — Search improvements: facets, highlight rendering, instant search

Status: Done
Source: Claude Code session; commit 8dfa896 on `claude/refine-local-plan-ohFc5`

What changed:
- `src/services/search/models.py` — Added `SearchResults(results, facets)` frozen dataclass
- `src/services/search/meili_provider.py` — `search()` returns `SearchResults`; added `metadata.mime_type` to facets list; added `"title"` to `attributesToHighlight`; `_map_result()` prefers `_formatted.title`; extracts `facetDistribution` from raw response
- `src/services/api/schemas.py` — `SearchResponse.facets: dict[str, dict[str, int]] = Field(default_factory=dict)`
- `src/services/api/routers/search.py` — Unpacks `meili_results.results` / `.facets`; passes `facets=meili_facets` to `SearchResponse`
- `tests/unit/test_meili_provider.py` — Updated 2 tests: `len(response)` → `len(response.results)`, `response[0]` → `response.results[0]`
- `frontend/src/api/search.ts` — `SearchResponse.facets?: Record<string, Record<string, number>>`
- `frontend/src/features/search/FilterPanel.tsx` — Added `facets` prop; file type checkboxes show live counts; Tags + Source sections with facet-driven checkboxes (top 10); Source+Tags removed from Advanced (Extension stays)
- `frontend/src/features/search/SearchPage.tsx` — `useEffect` debounce 350ms on `inputValue`; passes `data?.facets ?? {}` to FilterPanel
- `frontend/src/features/search/ResultRow.tsx` — `highlightHtml()` sanitizer; `dangerouslySetInnerHTML` on title + snippet
- `frontend/src/features/search/ResultRow.module.css` — Mark highlight styles

Verification:
- Backend: 31/31 unit tests pass (`test_meili_provider`, `test_meili_search_path`) — no-cov
- Frontend: 28/28 tests pass (`FilterPanel.test.tsx`, `SearchPage.test.tsx`)
- `tsc --noEmit` — clean; `npm run build` — clean (756ms, 64 chunks)

Open risks:
- FilterPanel existing tests do not cover new Tags/Source sections (no test data for facets) — low risk since prop is optional and sections hidden when empty
- Instant search doesn't navigate (URL not updated until explicit submit) — by design

Next agent prompt:
- Open PR from `claude/refine-local-plan-ohFc5` targeting `main` if not already done.
- Consider adding a FilterPanel test that passes mock facets and asserts Tags/Source sections appear.

## 2026-05-24 — Frontend code splitting, Ollama fix, issue board cleanup, #480

Status: Done
Source: Claude Code session; commits 64a70ad, 4929569 on main

What changed:
- `frontend/src/app/routes.tsx` — all 18 static page imports → React.lazy()
- `frontend/src/app/AppLayout.tsx` — Outlet wrapped in `<Suspense fallback={null}>`
- `frontend/vite.config.ts` — manualChunks: vendor-react, vendor-router, vendor-query, vendor-pdf, vendor-highlight, vendor-markdown
- `src/services/search/encoder.py` — `_embed_batch()` passes `options.num_ctx = self._max_tokens` to Ollama /api/embed; 2 new unit tests in `test_search_ollama_encoder.py`
- `frontend/src/features/comments/CommentComposer.tsx` — Enter submits, Shift+Enter newline, hint text
- `frontend/src/features/annotations/AnnotationEditor.tsx` — same; handleSubmit extracted as onSubmit
- CSS modules (Comments.module.css, Annotations.module.css) — `.hint` class appended
- 4 new frontend tests covering Enter/Shift+Enter in both composers
- Issues: #365 closed, #482 closed, labels added to #480/481/482/438/511

Verification:
- `npm run build` — clean, 64 chunks, no errors
- `npm run typecheck` — clean
- `vitest run` (comments + annotations) — 8/8 passed
- Backend encoder unit tests — 10/10 passed

Open risks:
- `fallback={null}` on Suspense: brief blank flash on first visit to a route chunk (imperceptible on fast connection; can swap to skeleton if needed)
- #481 (threaded replies in comments) needs backend first: parent_id migration, repository, routes, then frontend. Do not start frontend-first.

Next agent prompt:
- Resume #400 AI workstreams: start A2 (hybrid RAG retrieval) — A1 already merged.
- Or pick up #501 (Rust workspace scaffold) — all sub-issues #501–#510 are `status:next`.

## 2026-05-23 — RabbitMQ job bus merged + QoL improvements

Status: Done
Source: OpenCode session; issues #425–#432, #482

What changed:
- RabbitMQ job bus (#432) merged to main via PR #512: 7-stage pipeline, 6 workers, admin monitoring, retry tiers, air-gap support
- Related documents (#482): structured reasons with expandable "Why related?" panel
- Translation auto-detect: TranslateConsumer passes None to LibreTranslate; admin source default no longer forces "en"
- Download: fetch() with JWT auth replaces raw <a> link (was downloading 401 JSON). Supports original + translated text with clear error guidance
- TranslateConsumer: creates document_translation_versions records so frontend shows translation view mode
- EnrichConsumer: RabbitMQ stage for auto_enrich high-quality re-translation
- Pipeline efficiency: batch encoding (encode_batch), ThreadPoolExecutor for intelligence + map-reduce, model caching (OLLAMA_KEEP_ALIVE=4h, MAX_LOADED_MODELS=2)
- DB-poll split: when RABBITMQ_ENABLED=true, process_document job marked succeeded immediately — only RabbitMQ pipeline processes documents (no duplicate work)
- Ollama: better prompts (JSON format, examples), temp 0.2, embedding timeout 180s, model caching
- Boolean SQL fixes: 5 instances fixed + lint script + PostgreSQL CI job
- UI: full-width, live duration, 7-stage pipeline order, reason pills
- CI: ruff/mypy clean, 13 rabbit unit tests, CI split for PostgreSQL

Open risks:
- PostgreSQL CI job 20min timeout — may need further splitting if test suite grows
- Old pipeline_worker test removed (test_index_worker.py) — new workers have no unit tests
- SMB original file download broken when temp files deleted after sync (translated .txt works)

Next agent prompt:
- Sub #501: Cargo workspace scaffold + CI for Rust vector worker

## 2026-05-23 — Pipeline optimizations, UI full-width, prompt improvements

Status: Done
Source: OpenCode session

What changed:
- `src/services/pipeline/vector_worker.py` — batch encoding via `encode_batch()`
- `src/services/pipeline/worker.py` — batch encoding via `encode_batch()`; `_FakeEncoder` mock updated
- `src/services/intelligence/worker.py` — ThreadPoolExecutor for tasks + map-reduce; better fallback prompts; empty summary fallback to first sentence
- `src/services/pipeline/jobs.py` — `_sanitize_error` includes first line of `str(exc)`
- `src/services/intelligence/ollama_client.py` — timeout 120→300s
- `src/services/search/encoder.py` — embed timeout 60→180s, configurable via `embedding_timeout`
- `src/shared/config.py` — `embedding_timeout` field added
- `src/services/search/factory.py` — passes `embedding_timeout` to encoder
- `.env` — `OLLAMA_KEEP_ALIVE=4h`, `OLLAMA_MAX_LOADED_MODELS=2`

- Frontend CSS: admin pages/expertise/history/notifications — `max-width` removed, `width: 100%`
- Search results: `max-width` 980→1200px
- Document table columns: 42%/8%/6%/18%/auto for full-width
- Duration column: live ticking via 1s interval
- `src/features/admin/AdminSourceDetailPage.tsx` — `useRef` ticker for live duration

Verification: ruff clean, 12/12 intelligence tests, 12/13 pipeline worker (1 pre-existing), typecheck clean, build passes

## Handoff template

```md
## YYYY-MM-DD — Short title

Status: Active | Done | Watch
Source: issue | PR | commit | chat summary

What changed:
- ...

Verification:
- ...

Open risks:
- ...

Next agent prompt:
- ...
```

Status: Done
Source: OpenCode session (no issue)

What changed:
- `src/shared/config.py` — all 6 `feature_document_chat_*` flags → True
- `src/services/search/qdrant.py` — `create_collection_if_not_exists()` in `search()` + `search_filtered()`
- `src/services/api/routers/chat.py` — SSE: manual connection mgmt; `data.get("answer")` fallback; generator exception handler
- `src/services/api/routers/qa.py` — **deleted**
- `src/services/api/main.py` — removed qa_router
- `src/services/pipeline/scheduler.py` — **new** cron scheduler worker
- `src/services/api/routers/admin/sources.py` — schedule in CRUD; `GET /admin/sources/{id}/documents` with job aggregation; `DELETE /admin/sources/{id}`; `DELETE /admin/documents/{id}`
- `src/services/api/routers/admin/dlq.py` — `POST /admin/documents/{id}/requeue`
- `src/services/api/schemas.py` — `UpdateSourceRequest.schedule`
- `migrations/versions/u5v6w7x8y9z0_add_source_schedule.py` — `schedule TEXT` on ingestion_sources
- `docker/backend.Dockerfile` — `uv pip install --system` from ghcr.io/astral-sh/uv
- `.github/workflows/backend.yml`, `security.yml`, `release.yml` — `astral-sh/setup-uv@v5` replacing pip cache + pip install
- `pyproject.toml` → `uv.lock` — generated lockfile (98 packages)
- `AGENTS.md` — all dev commands prefixed with `uv run`
- `.env` — `OLLAMA_MEM_LIMIT=5g`, `OLLAMA_CONTEXT_LENGTH=1024`, chat flags enabled
- `.bashrc` — `nvm use 22` + Node 22 bin in PATH; `.nvmrc` created
- `frontend/src/api/admin.ts` — `SourceDocument`, `PipelineJob`, `SourceDocumentsResponse` types; `getSourceDocuments`, `requeueDocument`, `deleteDocument`, `deleteSource` methods
- `frontend/src/features/admin/AdminSourcesPage.tsx` — delete source button
- `frontend/src/features/admin/AdminSourceDetailPage.tsx` — Edit Source → edit page; `SourceDocumentsSection` with progress bar, expandable job rows, auto-refresh, rerun, delete per document; delete source button
- `frontend/src/features/admin/AdminEditSourcePage.tsx` — **new** dedicated edit page
- `frontend/src/app/routes.tsx` — removed qaRoute; added `adminEditSourceRoute`
- `frontend/src/components/layout/NavRail.tsx` — removed /qa; removed `MessageSquare`
- `frontend/src/components/feedback/CommandMenu.tsx` — /qa → /chat

Verification:
- Backend: 51/51 admin tests, 30/30 chat tests, ruff + mypy clean
- Frontend: 34/34 admin tests, 1/1 CommandMenu test, `tsc --noEmit` clean, `npm run build` passes
- `uv run` verified: ruff, pytest, mypy all functional

Open risks:
- None remaining in scope.

Next agent prompt:
- (All tasks from this session complete.)

## 2026-05-22 — In-document search fix tests verified and closed (#469)

Status: Done
Source: issue #469; commits 2927a50 (fix) + 48153a9 (tests) on feature/document-chat + main

What changed:
- Verified existing fix (2927a50): all renderers receive search props, PdfViewer page-jump, virtualized cumulative offsets.
- Added missing tests (48153a9):
  - PreviewPane: search prop passing verified for all renderer paths (text/plain, DOCX/RTF, extracted, PDF, table, archive, email, slides, code)
  - PdfViewer: activeSearchIndex navigates to page containing the match
  - ArchivePreview: match highlighting + count via onMatchCountChange
  - EmailPreview (new file): match highlighting + count
  - SlidesPreview (new file): cross-slide match count
  - TablePreview: cell highlighting + match count
  - TextPreview: virtualized global active-match index stability
  - DocumentPage: Ctrl+F opens search for text, suppressed for image/audio/video

Verification:
- `tsc --noEmit` — clean
- `ruff check`, `mypy` — backend unaffected (frontend-only change)

Open risks:
- Frontend test suite not run locally (Node 20.9.0) — resolved: Node 22 default as of 2026-05-23
- SQLite does not enforce FK cascade (messages persist after session delete in test DB); documented in test comment; Postgres enforces correctly in production

#473 recommendation: **Ready to close** — Phase B backend + frontend + tests are complete. B7 added router hardening, lifecycle coverage, cross-user isolation tests, and degraded RAG fallback. No Phase C/D/E/F scope was touched.

Next agent prompt:
- Phase C: scope model, `ChatScope` filter UI, `ScopeBadge` component, InsightPane migration from legacy QAPanel to ChatWindow. Branch off `feature/document-chat`.

## 2026-05-21 — Document Chat Phase B6 frontend complete

Status: Done
Source: issue #473, commit e95f696 on feature/document-chat

What changed:
- `frontend/src/api/chat.ts` — typed API client for all /chat/* endpoints
- `frontend/src/features/chat/` — ChatPage, ChatSidebar, ChatWindow, ChatInput,
  MessageList, MessageBubble, ChatCitationCard, ChatCitationList (all new)
- `frontend/src/app/routes.tsx` — `/chat` route added
- `frontend/src/components/layout/NavRail.tsx` — "Chat" nav item (MessagesSquare icon)
- `frontend/src/i18n/locales/en.ts` + `he.ts` — nav.chat + full chat section strings
- `frontend/src/features/chat/ChatPage.test.tsx` — 11 test cases

Key design decisions:
- Session messages managed in local state after initial query seed (prevents refetch flash)
- Seeded once per session via ref guard; staleTime=5m on session query
- User message optimistically added; replaced by server user+assistant turn on success
- citation_id used as React key (fallback: `${document_id}-${chunk_index ?? idx}`)
- TanStack Query v5: useEffect used instead of onSuccess on useQuery

Verification:
- `tsc --noEmit` — exit 0
- (Node 20.9.0 resolved globally 2026-05-23: nvm default → v22)
- `npm run lint` — same Node gap blocks formatter output

Open risks:
- Vitest/ESLint now work on Node 22; CI must use compatible version
- `MessagesSquare` icon from lucide-react — confirm it exists in the pinned version at CI time
- Phase C InsightPane migration not yet done; InsightPane still shows legacy QAPanel

Next agent prompt:
- B7 integration tests: full session lifecycle, cross-user 403, degraded Qdrant fallback
- Then Phase C: scope model, ChatScope filter, ScopeBadge, InsightPane migration

## 2026-05-21 — Phase B1-B2 chat_sessions + chat_messages migrations

Status: Done
Source: issue #473

What changed:
- Created `k1l2m3n4o5p6_add_chat_sessions_table.py` — `chat_sessions` with id, user_id (FK CASCADE), title, scope_type, scope_ids (JSON as Text), created_at, updated_at, archived_at, metadata (JSON as Text). Indexes on user_id and updated_at.
- Created `q7r8s9t0u1v2_add_chat_messages_table.py` — `chat_messages` with id, session_id (FK CASCADE to chat_sessions), role, content, rewritten_query, citations (JSON as Text), retrieval_trace, model, latency_ms, created_at, metadata. Index on (session_id, created_at).
- JSON fields use `sa.Text()` with JSON-serialized defaults for SQLite compat (project convention — no CheckConstraints, app-layer validation).

Verification:
- `ruff check` + `ruff format` — passed
- `pytest tests/test_migrations.py` — 5 passed (all existing migration smoke tests + new tables created successfully)

Open risks:
- JSON-in-Text fields need app-layer encoding/decoding (ChatRepository handles this)
- No check constraint on `role` — app-layer validation required

Next mission:
- B3 ChatRepository

## 2026-05-21 — Document Chat Phase A foundation complete

Status: Done
Source: issue #472

What changed:
- Added `citation_id` UUID to backend `Citation` model (auto-generated via `uuid4` default factory).
- Included `citation_id` in `/qa` response serialization.
- Added `chunk_index`, `source_id`, `citation_id` to `QACitation` TypeScript type.
- Fixed `CitationList` React key collision: `key={c.citation_id ?? `${c.document_id}-${c.chunk_index ?? idx}`}`.
- Replaced 1-sentence grounding prompt with 8-rule prompt per Document Chat design spec.

Verification:
- `ruff check` + `ruff format` — passed
- `mypy` — 3 source files, no issues
- `pytest tests/unit/test_rag_retrieval_eval.py tests/unit/test_rag_reranker.py` — 18 passed
- `tsc --noEmit` — exit 0
- (Node 20.9.0 resolved globally 2026-05-23)

Open risks:
- Frontend test suite now runs locally on Node 22; CI should confirm

Next agent prompt:
- Phase B (persistent chat sessions) after PR #472 merges.

## 2026-05-21 — #449 in-document search complete

Status: Done
Source: issue #449, PR #462

What changed:
- Added `DocumentSearchBar.tsx` (`type="search"` input for `searchbox` ARIA role): debounced query, N of M counter, Prev/Next nav, Escape closes, Shift+Enter → Prev, `aria-live="polite"` counter.
- Added `highlightMatches.tsx`: shared utility returning `{nodes, count}` with `<mark data-match-index>` elements; active match gets distinct CSS class. `countMatches()` for non-rendered count (PDF).
- `DocumentPage`: Ctrl+F/Cmd+F toggles search bar; 200ms debounce; `searchable` computed (excludes image/audio/video/archive); search state threaded to PreviewPane.
- `DocumentToolbar`: search toggle button with `aria-pressed`; shown when `searchable && onSearchToggle`.
- `TextPreview` + `CodeViewer`: highlight matches inline, scroll active mark into view.
- `PdfViewer`: extracts text from all pages via `getTextContent()`, reports match count via `onMatchCountChange`.
- `TablePreview`: CSS class on matching cells.
- `frontend/src/test/setup.ts`: added `Element.prototype.scrollIntoView = vi.fn()` for jsdom.

Verification:
- 77/77 targeted tests (DocumentSearchBar 13, DocumentToolbar 14, TextPreview, CodeViewer, PdfViewer). TypeScript clean.

Open risks:
- `scrollIntoView` for active match not verified in real browser; jsdom mock confirms call path only.
- PdfViewer match highlighting is count-only (no visual marks in canvas-rendered PDF).

Next agent prompt:
- Check parent issue #453 for remaining MVP child issues after #449.

## 2026-05-21 — #448 media viewer complete

Status: Done
Source: issue #448, PR #461

What changed:
- Added `MediaPreview.tsx`: native `<audio controls>` / `<video controls>` (16:9 container). `onError` → `UnsupportedPreview`. Metadata row (title, MIME). Transcript section (`<h3>`) shown when `snippet` non-empty.
- Backend download route: added `Accept-Ranges: bytes`, `Range` request parsing, 206 Partial Content response. `Content-Disposition` changed to `inline` for browser playback.
- PreviewPane: `audio/*` and `video/*` prefix dispatch added before image branch.

Verification:
- 16/16 MediaPreview tests. 2 new PreviewPane dispatch tests. 185/185 full suite. TypeScript clean.

Open risks:
- Backend byte-range handling not covered by existing tests; only manually verified via code review.
- `Content-Disposition: inline` change affects non-media downloads too (all MIME types now inline).

Next agent prompt:
- Merge PR #461 into `feature/document-viewer`.
- Start #449 (In-document search). Branch `feat/449-in-document-search` from `feature/document-viewer`.

## 2026-05-21 — #447 code/syntax viewer complete

Status: Done
Source: issue #447, PR #460

What changed:
- Added `CodeViewer.tsx` using highlight.js core (bundled; json, xml, yaml, python, js, ts, bash, sql languages registered). Fetches via `getDocumentText` with limit 50,000.
- Line numbers in a sticky-left `aria-hidden` gutter. Copy button (`aria-label="Copy code"`). Raw toggle, word-wrap toggle.
- Truncation notice shown when `data.truncated=true`.
- Language detection: MIME lookup → file extension from `title` → `"plaintext"` fallback (skips hljs).
- Container `role="region"` + `aria-label="Code: {title}"`.
- PreviewPane: `application/json` moved from TextPreview to CodeViewer; `CODE_MIMES` set added covering xml/yaml/source types; `text/plain`/`text/markdown` remain on TextPreview.

Verification:
- 19/19 CodeViewer tests. 3 new PreviewPane dispatch tests. 167/167 full suite. TypeScript clean.

Open risks:
- highlight.js GitHub theme (github.min.css) is always light; no dark-mode variant wired.
- Gutter line-count comes from splitting raw text by "\n"; a file without a trailing newline has one fewer gutter line than the tokenized output.

Next agent prompt:
- Merge PR #460 into `feature/document-viewer`.
- Start #448 (Media viewer). Branch `feat/448-media-viewer` from `feature/document-viewer`.

## 2026-05-21 — #445 metadata Details tab complete

Status: Done
Source: issue #445, PR #459

What changed:
- Extended `PreviewResponse` (backend) with `source_language`, `target_language`, `status`, `content_sha256`, `created_at`, `updated_at` (all `str | None`).
- Added those fields as optional to `DocumentPreview` TypeScript interface.
- Created `DetailsTab.tsx` — `<dl>` component with 25+ MIME label mappings, file size (B/KB/MB), source/path from metadata, languages, translation quality badge, status badge, version + latest marker, timestamps, SHA-256 (12-char truncated + copy button).
- Created `DetailsTab.module.css` with badge, code, hashGroup, copyBtn styles.
- Added `"details"` to `InsightPaneTab` union; added `tabDetails` i18n key to en + he locales.
- Updated `InsightPane` to accept `preview?: DocumentPreview` and render DetailsTab.
- Updated `DocumentPage` to pass `preview` to InsightPane.
- Deleted `DetailsPanel.tsx` (unused).

Verification:
- 19/19 DetailsTab tests passed. Full documents suite 145/145. TypeScript clean.

Open risks:
- None critical. SHA-256 copy feedback is a 2-second "Copied" flash — no fallback for clipboard API denial.

Next agent prompt:
- Merge PR #459 into `feature/document-viewer`.
- Start #447 (Code/syntax viewer). Branch `feat/447-code-viewer` from `feature/document-viewer`.

## 2026-05-21 — #444 image viewer complete

Status: Done
Source: issue #444, PR #458

What changed:
- Added `ImageViewer.tsx` with zoom 25%–400%, pan, keyboard controls (+/-/0/arrows), Ctrl+scroll, double-click fit reset.
- TIFF → UnsupportedPreview; load error → ExtractionFailedPreview; SVG as `<img>` (no inline SVG).
- Image info bar shows dimensions + zoom level.
- Keyboard help in visually-hidden `<p>`.
- Zoom state lifted to DocumentPage (`imageZoom`, `setImageZoom`); toolbar shows zoom controls when `showImageControls=true`.
- PreviewPane now passes `imageZoom`/`onImageZoomChange` to ImageViewer.
- ImagePreview.tsx deleted.

Verification:
- 264/264 tests passed (50 test files). TypeScript clean.

Open risks:
- Ctrl+scroll preventDefault called on React synthetic event — needs browser test to verify scroll is suppressed in the container.
- Pan boundary clamping not implemented; image can be panned off-screen.

Next agent prompt:
- Merge PR #458 into `feature/document-viewer`.
- Start #445 (Metadata Details tab). Branch `feat/445-metadata-tab` from `feature/document-viewer`.

## 2026-05-21 — #443 view mode switcher complete

Status: Done
Source: issue #443, PR #457

What changed:
- Added `ViewModeSwitcher.tsx` — segmented button group (original/extracted/translation); hidden when ≤1 mode available.
- Added `FidelityStatusBar.tsx` — single-line strip with colour dot + accessible aria-label + fidelity text; sits between toolbar and viewer body in `DocumentPage`.
- `DocumentPage`: replaced `showOriginal` state with `activeMode` (ViewMode); derives showOriginal; defaults to `translation` if available translations exist; resets on docId change.
- `DocumentToolbar`: added `availableModes`/`activeMode`/`onModeChange` props; renders ViewModeSwitcher in controls.
- `PreviewPane`: added `activeMode`/`selectedVersionId` props; extracted/translation modes override MIME dispatch to TextPreview; HTML and images always rendered natively.

Verification:
- 236/236 tests passed (49 test files). TypeScript clean.
- New tests: 6 ViewModeSwitcher + 10 FidelityStatusBar + 4 new PreviewPane + 5 new DocumentPage.

Open risks:
- FidelityStatusBar doesn't cover red/grey dot states (file unavailable, no preview) — those require server flag not yet available.
- `converted` preview mode wired to #446; skipped per issue spec.

Next agent prompt:
- Merge PR #457 into `feature/document-viewer`.
- Check #453 for the next remaining child issue in the MVP track.

## 2026-05-21 — #442 PDF.js viewer complete; #443 view mode switcher next

Status: Done
Source: issue #442, PR #456

What changed:
- Added `PdfViewer.tsx` using `pdfjs-dist` with canvas rendering, page nav, zoom, loading state, and `ExtractionFailedPreview` on failure.
- Worker configured via `pdfjs-dist/build/pdf.worker.min.mjs?url` — local bundled asset, no CDN.
- `PreviewPane` dispatches `application/pdf` to `PdfViewer` (was TextPreview).
- Added `PreviewPane.test.tsx` and `PdfViewer.test.tsx`.

Verification:
- Frontend: 18/18 tests passed. TypeScript clean.
- jsdom logs canvas `getContext` not-implemented warnings — expected, guarded in component.

Open risks:
- Page/zoom controls are inside `PdfViewer` for this PR; #443 may want to move them to `DocumentToolbar`.
- Text layer not enabled yet (canvas-only rendering); browser find-in-page won't work until added.
- Canvas rendering is not verified in jsdom tests — needs manual/browser test.

Next agent prompt:
- Branch `feat/443-view-mode-switcher` from `feature/document-viewer` after PR #456 merges.
- Read mission for issue #443 (`docs/agents/missions/` if it exists).
- If moving PDF controls to DocumentToolbar, thread state up from PdfViewer via ref or callback.

## 2026-05-21 — #441 full text API complete; #442 PDF.js viewer next

Status: Done
Source: issue #441, PR #455, issue #442

What changed:
- Added `GET /documents/{document_id}/text` (offset/limit pagination, show_original, translation_version_id).
- Added `PreviewService.get_full_text()` in `src/services/preview/service.py`.
- Added `getDocumentText()` in `frontend/src/api/documents.ts`.
- Updated `TextPreview` to fetch in 10K chunks with loading state and "Load more".
- Updated `PreviewPane` to pass `docId` to `TextPreview` for all text dispatches.
- Created `feature/document-viewer` integration branch on remote.

Verification:
- Backend: 9/9 integration tests passed (`tests/integration/test_document_text_api.py`).
- Frontend: 9/9 unit tests passed (`TextPreview.test.tsx`). TypeScript clean.

Open risks:
- PDF dispatch in PreviewPane still goes to TextPreview; #442 must change it to PdfViewer.
- `TextPreview` `text` prop is now optional — any caller not on `docId` path still works via static fallback.
- Coverage floor (90%) only enforced on full suite run; targeted test runs will show coverage failure.

Next agent prompt:
- Branch `feat/442-pdfjs-viewer` from `feature/document-viewer` after PR #455 merges.
- Read mission `docs/agents/missions/issue-442-pdfjs-viewer.md`.
- Verify #441 is present on `feature/document-viewer` before starting (check `getDocumentText` exists in `frontend/src/api/documents.ts`).
- PR must target `feature/document-viewer`, not `main`.

## 2026-05-21 — #450 a11y, performance, and telemetry hardening complete

Status: Done
Source: issue #450, PR #464

What changed:
- A11y: download link aria-label in DocumentToolbar; table aria-label + th scope="col" in TablePreview; sr-only status text in FidelityStatusBar; focus management on view mode switch and search close in DocumentPage.
- Perf: TextPreview virtualized with react-window v2 `List` when >10K lines (22px row height, max 600px); TablePreview virtualized with ARIA role-based table when >1K rows (32px row height).
- Telemetry: viewer.text/pdf/image.load event names added to performanceTelemetry.ts; named timers in TextPreview/PdfViewer/ImageViewer.
- Backend: X-Content-Type-Options: nosniff on both full and range download responses.
- Test infrastructure: ResizeObserver global mock added to test setup (react-window v2 requirement); archive traversal unit tests for ZIP/TAR ".." paths; nosniff integration test.

Verification:
- 359/359 frontend tests passed (54 files). TypeScript clean.
- 7/7 archive extraction tests passed. 1 nosniff integration test passed.
- Lint: no new errors (only pre-existing).

Open risks:
- Virtualization tests limited in jsdom (no layout measurement) — browser-based verification deferred to #451 follow-up.
- Virtualized TablePreview uses ARIA roles instead of native `<table>` — tradeoff required by react-window.

Next agent prompt:
- Check parent issue #453 for remaining MVP child issues.
- If picking up #451 (browser-based test verification), note that virtualization rendering can only be verified in a real browser with layout.

## 2026-05-22 — #488 document relationships complete

Status: Done
Source: issue #488; PR #496 (targeting feature/document-details-and-search); commit c3cd4a0 on 488-document-relationships

What changed:
- Migration: `document_relationships` table with unique constraint on (parent, child).
- `DocumentRelationshipRepository`: create_relationship (idempotent), get_relationships (UNION both directions).
- Pipeline: worker records `email_attachment` or `archive_child` relationships after child doc creation.
- PreviewResponse extended with `relationships` field.
- DetailsTab: "Source context" section with parent/child badges + linked titles.

Verification:
- ruff/mypy/tsc clean; 7 unit + 3 integration tests pass.
- Branch targets feature/document-details-and-search.

Open risks:
- Relationship population only happens for newly ingested docs (no retroactive backfill).
- (Node 20.9.0 resolved globally 2026-05-23)

Next agent prompt:
- Pick up #483 (expand details panel) or #484 (advanced search).

## 2026-05-22 — #487 unify comments into annotations complete

Status: Done
Source: issue #487; PR #495 (targeting feature/document-details-and-search); commit aa5f32e on 487-unify-comments-annotations

What changed:
- Migration: `annotation_replies` table + INSERT comments as document-level annotations (position=NULL).
- Annotation replies: list_replies, create_reply, delete_reply (soft), can_modify_reply; reply_count in list_annotations.
- Reply API: GET/POST /annotations/{id}/replies, DELETE /annotation-replies/{id}.
- Comments router: all endpoints return 410 Gone.
- Frontend: removed comments tab from InsightPane; AnnotationItem gains inline reply list/composer.

Verification:
- ruff/mypy clean; 9 unit + 11 integration + 9 existing + 5 migration = 34 backend tests pass; tsc clean.

Open risks:
- Comment i18n keys are now dead (no harm).
- Branch targets feature/document-details-and-search.
- (Node 20.9.0 resolved globally 2026-05-23)

Next agent prompt:
- Pick up #488 (document relationships) or #483 (expand details panel).

## 2026-05-22 — #486 user-managed private/public document tags complete

Status: Done
Source: issue #486; PR #494 (targeting feature/document-details-and-search); commit a9dc372 on 486-user-tags

What changed:
- Migration: `user_document_tags` table with indexes on (document_id, user_id) and (document_id, is_private).
- `UserDocumentTagRepository`: list_tags (own private + all public), create_tag (max 50/user/doc, dup check), delete_tag (ownership or admin).
- API: GET/POST/DELETE `/documents/{id}/user-tags` — all behind `assert_doc_access`.
- `UserTagEditor` component: chip list (private dim, public accent-tinted), inline input + Add, Enter support, Private/Public radio, delete on owned tags, error state.
- Wired into `DetailsTab` as "My Tags" section; `docId` from `InsightPane`.

Verification:
- `ruff check` + `ruff format` — clean
- `mypy --strict` — no issues (3 source files)
- `pytest tests/unit/test_user_document_tags.py --no-cov` — 16 passed
- `pytest tests/integration/test_user_tags_api.py --no-cov` — 17 passed
- `pytest tests/test_migrations.py --no-cov` — 4 passed
- `tsc --noEmit` — clean
- (Node 20.9.0 resolved globally 2026-05-23)

Open risks:
- Frontend vitest not run locally — CI is sole gate for UserTagEditor.test.tsx.
- Branch targets `feature/document-details-and-search`, not `main`.

Next agent prompt:
- Pick up #487 (unify comments into annotations) or #488 (document relationships).

## 2026-05-22 — #485 Markdown preview complete

Status: Done
Source: issue #485; PR #493 (targeting feature/document-details-and-search); commit 3b5a592 on 485-markdown-preview

What changed:
- `MarkdownPreview` renderer: fetches via `getDocumentText` (100K limit), marked + DOMPurify sanitization, Raw/Rendered toggle, Copy button, loading/error/fallback states.
- Wired into `PreviewPane`: MIME dispatch + extension fallback for `.md`/`.markdown`/`.mdown`.
- 13 MarkdownPreview tests + updated PreviewPane dispatch tests.

Verification:
- `tsc --noEmit` — clean
- (Node 20.9.0 resolved globally 2026-05-23)

Open risks:
- Frontend vitest now runnable locally on Node 22.

## 2026-05-20 — Agent skills and memory branch

Status: Done
Source: project manager chat summary

What changed:
- Started branch `chore/add-agent-skill-pack`.
- Added shared Claude/OpenCode skills under `.claude/skills/`.
- Added shared memory policy and seed memory files.

Verification:
- File creation verified through GitHub connector commit responses.

Open risks:
- OpenCode agent definitions still need final creation and review.
- No local runtime validation was run.

Next agent prompt:
- Review branch `chore/add-agent-skill-pack` for skill discoverability, OpenCode agent syntax, and memory policy clarity.
