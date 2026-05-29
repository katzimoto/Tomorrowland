# Tomorrowland Current State

Canonical shared memory for active project state. Keep this file compact and factual.

## 2026-05-29 — feat(extraction): Markdown Office extraction — merged PR #533

Status: Done — commit f6fbebb on main
Source: PR #533, issue #526

Native DOCX/PPTX/XLSX → Markdown converters added and enabled by default (`enable_markitdown=True`).
Preserves headings, tables, slide titles, bullets, and sheet structure for improved RAG chunking.
Each converter wraps the original extractor as fallback on empty output or error.
No new dependencies — implemented with python-docx/python-pptx/openpyxl (already in deps).
Disable with `ENABLE_MARKITDOWN=false`.

Key constraint: markitdown 0.1.x requires `magika<0.7`, conflicting with `magika>=1.0` (core dep).
Decision: implement natively rather than take the package dependency. See decisions.md.

---

## 2026-05-29 — test(extraction): pre-benchmark fixture corpus — merged PR #535

Status: Done — PR #535 merged to main
Source: PR #535, issue #527

Fixture corpus and assertion layer built as prerequisite for Onyx benchmark comparison:
- 5 fixture files added to `tests/fixtures/`: `sample-with-headings.docx`, `sample-multisheet.xlsx`, `wrong-extension.docx` (PPTX rename), `corrupt.pdf`, `encrypted.pdf`
- 15 unit tests in `tests/unit/test_extraction_fixture_corpus.py` covering extraction shape, failure-modes, and `has_extractor` boundary
- 1 integration test in `tests/integration/test_chunk_index_pipeline.py` verifying every Qdrant chunk payload has non-null integer `chunk_index`
- `PdfExtractor` now catches `FileNotDecryptedError` so encrypted PDFs return empty text instead of crashing

---

## 2026-05-29 — feat(intelligence): LLM provider abstraction — issue #528

Status: Done — PR open, pending merge
Source: issue #528, Claude Code session

`LLMProvider` protocol + `OpenAICompatibleLLMProvider` + `build_llm_provider()` factory added.
- `src/services/intelligence/llm_provider.py` — protocol, `OpenAICompatibleLLMProvider`, `parse_json_array()`
- `src/services/intelligence/factory.py` — `build_llm_provider(settings)` reads `LLM_PROVIDER` / `LLM_BASE_URL` / `LLM_MODEL`
- `src/shared/config.py` — 3 new fields (`llm_provider`, `llm_base_url`, `llm_model`)
- `app.state.ollama_client` renamed to `app.state.llm_provider` (eagerly initialized, never None)
- All 9 caller sites updated; `OllamaClient` default path unchanged
- 18 unit tests pass; mypy strict clean

---

## 2026-05-29 — roadmap: issues #526–#532 created from Onyx comparison (#525)

Status: Active
Source: Planning session, issue #525

7 issues opened following Onyx reference architecture comparison planning:
- #526 MarkItDown extraction — DONE (PR #533 merged)
- #527 Pre-benchmark fixture corpus + assertions — DONE (PR #535 merged)
- #528 LLM generation provider abstraction (OpenAI-compatible) — DONE (PR open)
- #529 Ingestion pipeline debug status page (admin UI) — status:next
- #530 Exact-location citation grounding (page/section) — status:next (unblocked by #527)
- #531 Connector credential store — status:deferred
- #532 Canonical metadata sidecar format — status:deferred

Next recommended order: #529 → #530 (citation grounding).

---

## 2026-05-28 — dist: v0.2.0 air-gapped release artifact created

Status: Active — files written, not yet tarred or CI-built
Source: Claude Code session

`dist/tomorrowland-release-v0.2.0/` created from rc3 baseline with these changes:
- `release-manifest.json`: version `v0.2.0`, commit `16ff0ab`, image tags `v0.2.0`, `ollama_data` split into `ollama_llm_data` + `ollama_embed_data`, new `ollama_model_bundles` section for all 3 bundles.
- `docker-compose.airgap.yml`: single `ollama` → `ollama-llm` (port 11434) + `ollama-embed` (port 11435); `EMBEDDING_PROVIDER` defaults to `ollama`; `api` depends_on both.
- `.env.airgap.example`: version stamped, `EMBEDDING_PROVIDER=ollama` set, RC3 comments removed.
- `README-airgap.txt`: all 3 bundles listed with sizes and target containers.
- `docs/air-gapped-deployment.md`: mistral → qwen3.5:35b-a3b throughout; 3-bundle table; per-container load commands; port 11435 for embedding validation; updated Qdrant collection example (`documents_v4096`).
- `docs/air-gapped-upgrade.md` + `docs/production-compose.md`: same model/volume updates.
- `scripts/validate-ollama-model.sh`: default `mistral` → `qwen3.5:35b-a3b`.
- `scripts/load-ollama-model-bundle.sh`: usage updated for `--compose-service` flag.
- `checksums.txt`: regenerated for all changed files.

Three v0.2.0 bundle metadata dirs created:
- `dist/tomorrowland-ollama-bundle-qwen3.5-35b-a3b-v0.2.0/` — model-manifest.json + README (target: `ollama-llm`)
- `dist/tomorrowland-ollama-bundle-qwen3-14b-v0.2.0/` — model-manifest.json + README (target: `ollama-llm`)
- `dist/tomorrowland-ollama-bundle-qwen3-embedding-8b-v0.2.0/` — model-manifest.json + README (target: `ollama-embed`)

Remaining build-time step: CI must rebuild `images/tomorrowland-images.tar` with `v0.2.0` image tags, then `sha256sum images/tomorrowland-images.tar >> checksums.txt`, then produce `tomorrowland-release-v0.2.0.tar.gz` and split image parts.

Key architectural decision: `ollama-llm` and `ollama-embed` are now separate Compose services with separate volumes (`ollama_llm_data`, `ollama_embed_data`). Operators upgrading from rc3 must re-load model weights into both containers.

---

## 2026-05-28 — feat(extraction): Magika ML MIME detection — merged PR #524

Status: Done — ffe2265 on main
Source: PR #524

Google Magika (`magika>=1.0`) added as Layer 1 in `MimeDetector.detect()`.
Threshold 0.80: DOCX/XLSX/PPTX/PDF/EPUB pass; EML/plain text/OLE fall through to python-magic.
Lazy ONNX singleton; `magika` now a core dependency (not optional).
47 tests pass. No follow-up work required.

---

## 2026-05-27 — fix(extraction): office file extraction — 3 bugs fixed

Status: Done — uncommitted on main
Source: Claude Code session

3 bugs fixed in office file extraction:

1. **`.xls` (Excel 97-2003) never extracted** — `application/vnd.ms-excel` had no extractor; fell to `GenericExtractor` which returns `""` for binary files. Fixed: new `XlsExtractor` (`src/services/extraction/xls.py`) using `xlrd` (pure Python, no system deps), registered unconditionally. `xlrd>=2.0` added to `pyproject.toml`.
2. **`parse_worker`, `slow_worker`, `vector_worker` ignored `ENABLE_LEGACY_OFFICE` / `ENABLE_OCR` env vars** — all three `main()` functions created `ExtractorRegistry()` without settings flags. Fixed: all three now pass `enable_ocr=settings.enable_ocr, enable_legacy_office=settings.enable_legacy_office`.
3. **`sample.xls` test fixture** created; 4 new tests in `tests/unit/test_extraction_xls.py`.

Note: `.doc`/`.ppt` (Word/PowerPoint 97-2003 binary) still require `ENABLE_LEGACY_OFFICE=true` + LibreOffice in PATH. Modern `.docx`/`.xlsx`/`.pptx` work without any extra config.

Verification: ruff OK, mypy --strict OK (5 files), 36/36 related tests pass.

---

## 2026-05-27 — fix(ai): 7-bug sweep — RAG, hybrid search, intelligence worker, chat

Status: Done — commit 9e437a3 on main
Source: Claude Code session (codebase analysis)

7 correctness bugs fixed across the AI integration layer:

1. **hybrid.py `merge_results`** — was deduplicating by `document_id`, collapsing all chunks of a multi-chunk document into one result. Now deduplicates by `metadata[chunk_id]`, falling back to `document_id` for doc-level BM25 results. 3 new tests.
2. **rag/service.py `_retrieve_chunks`** — BM25 (Meilisearch) search ignored chat scope (`single_document`, `selected_documents`); out-of-scope chunks reached the context window in hybrid mode. New `_apply_scope_to_bm25()` post-filters each BM25 result list before `merge_results()`.
3. **intelligence/worker.py** — `_extract_entities` / `_auto_tag` propagated exceptions through `_run`, causing `process_document` to raise and kill the pipeline job — contradicting "never block ingestion." Both now have the same try/except+log pattern as `_summarize`. `_run` no longer accumulates an `errors` list.
4. **ollama_client.py `generate_stream`** — dead `tokens` counter incremented but never emitted as a metric. Removed.
5. **OllamaClient._model** — 4 call sites accessed private `_model` attribute. Added public `model` property; all call sites updated.
6. **rag/service.py** — duplicate `# 4.` step comment; generation is now `# 5.`.
7. **chat.py `create_message_stream`** — `stream_settings` alias pointed to same object as `settings`, mixed in RagService constructor. Removed alias.

Verification: ruff OK, mypy --strict OK (5 files), 839/839 non-infrastructure unit tests pass.

Watch: `source`-scope BM25 filtering still not applied (Meilisearch payloads don't index `source_id`). Qdrant enforces it on vector side. Low risk.

---

## 2026-05-27 — feat: original file storage + Download Original (Tier 1 + Tier 2)

Status: Done — implemented on main, not yet committed/pushed
Source: Claude Code session

Two-tier implementation for persisting connector-downloaded files and exposing a "Download Original" button in the UI:

**Tier 1 — move-before-create (scheduler + sync-now)**
- New module: `src/services/pipeline/original_store.py` — `move_to_originals(path, mime_type, files_root)`.
  Skips audio/video, skips files already inside `files_root`, renames (O(1) on same FS, copy+delete cross-device).
- Scheduler (`_sync_source`) and sync-now route now call `move_to_originals()` before `doc_repo.create()`.
  `doc.path` in DB always points to a persistent `files_root/originals/{uuid}{ext}` file.

**Tier 2 — direct-write connectors (no tmp intermediary)**
- `ConnectorDocument.fetch_documents()` Protocol gains `storage_root: Path | None = None`.
  When provided, connectors write files directly to `storage_root` (skipping tempfile entirely).
- Updated: SMB, Atlassian (Confluence/Jira), Folder (no-op — already persistent), NiFi (event-driven, no files).
- Scheduler + sync-now pass `originals_root = files_root / "originals"` as `storage_root`.
  Tier 1 move_to_originals still runs as a safety net (idempotent for files already inside files_root).

**Frontend**
- `PreviewResponse` + `DocumentPreview` TS interface gain `has_file: bool`.
- `DocumentToolbar` download button label: "Download" when `has_file`, "Download text" when text-only.
- Text-only fallback: download route returns `content_text` from `document_payloads` as `.txt` instead of 404.
- i18n: `downloadText` added to EN + HE.

**Verification:** ruff clean, mypy strict clean, tsc clean, 48/48 connector + original_store tests pass.

Next action: git commit and push.

---

## 2026-05-26 — fix/office-extraction-empty-text — 3-bug sweep merged (PR #521)

Status: Done — merged to main
Source: Claude Code session

PPTX/DOCX/XLSX showing no extracted text in the app — three separate bugs all contributed:
1. `PreviewService._generate_snippet` skipped `document_payloads.content_text` and went straight to file re-extraction; temp-file connectors (SMB/Atlassian) delete the file after the pipeline, so snippets were always empty. Fixed: read payload row first.
2. `consumer_base.py` manual retry path (attempt ≥ retry_limit) rebuilt message JSON without `content_text`; translate/embed/index workers all received `""`. Fixed: `get_payload()` + include in retry body.
3. `PptxExtractor` / `DocxExtractor` didn't catch `zipfile.BadZipFile` or `ValueError`; corrupted files propagated unhandled exceptions. Fixed: widened exception tuple.

8 regression tests (17 total across 4 files). Ruff + mypy clean.

---

## 2026-05-26 — pipeline connector parity — 6-bug sweep complete

Status: Done — committed to main
Source: Claude Code session

6 logical bugs fixed across pipeline ingestion paths (sync-now API + scheduler + worker):
temp file lifecycle (SMB/Atlassian), RabbitMQ scheduler publish gap, generator iteration guard,
unreachable `sync_outcome = "failed"`, and NiFi missing from error classification.
See `handoffs.md` for full detail.

---

## 2026-05-26 — annotations router — 2 security bugs fixed, ACL MEDIUM items still open

Status: Active
Source: Claude Code session (graphify codebase analysis)

**Fixed — committed to main (direct push, no open branch):**
1. `DELETE /annotation-replies/{reply_id}` — was missing `assert_doc_access` entirely; a revoked user could delete their own replies by knowing the UUID. Fixed: fetch reply → fetch parent annotation → `assert_doc_access` before ownership check.
2. `GET /annotations/{annotation_id}/replies` — only checked doc-level access, not annotation visibility. Non-owner with doc access could enumerate replies on a private annotation by knowing its ID. Fixed: 404 if `is_private && user != owner && !admin`.

**Structural change:** `_get_annotation_or_404_with_access()` helper extracted in router — all 4 per-annotation endpoints now route through it, preventing future endpoints from accidentally skipping the access check.

**Still open — ACL audit HIGH items (`docs/context/acl-audit.md`):**
- `/search` admin path returns no results (broken bypass)
- `/expertise` admin path broken
- Stub `SearchResultItem` in `/search` (data leak risk)
- `get_effective_group_ids` transitive-group expansion missing
- `/expertise` subscription leak

**Still open — ACL audit MEDIUM items:**
- `/me/activity` and `/notifications` not filtered by current doc-access
- Per-version ACL on `/documents/{id}/versions`
- Sensitive key masking in `GET /admin/config`

**Next action:** Pick up ACL HIGH items (D2 PR blocker) or MEDIUM ACL items.

## 2026-05-26 — fix/extractor-bugs — 15-bug sweep across extractors + translation pipeline

Status: Done — merged to main (squash commit from PR #520)
Source: Claude Code session

15 bugs found and fixed across three passes.

**Pass 1 — extractor correctness**
1. `html.py` — nested skip-tag depth counter (was boolean, leaked text from `<nav><style>` etc.)
2. `html.py` — latin-1 encoding fallback (ISO-8859-1/Win-1252 HTML was silently empty)
3. `rtf.py` — latin-1 encoding fallback (most RTF files are Win-1252, were silently empty)
4. `xml_extractor.py` — strip XML tags via `ET.itertext()` (was sending raw markup to translator)
5. `xml_extractor.py` — use `ET.parse()` for encoding-aware parsing (declared encoding respected)
6. `docx.py` — deduplicate merged cells by `_tc` identity (merged cell text appeared N times)
7. `msg_extractor.py` — `msg.close()` in `finally` for both `extract()` + `extract_attachments()`
8. `xlsx.py` — `wb.close()` in `finally` block (was skipped on any exception)
9. `registry.py` — removed self-alias `x-tar → x-tar` (no-op)
10. `registry.py` — removed dead `x-zip-compressed` direct registration (alias already routes it)

**Pass 2 — translation pipeline + extractor quality**
11. `translation_worker.py` — empty `content_text` now skips gracefully (previously raised ValueError → retried → dead-lettered valid docs with no text)
12. `slow_worker.py` — `type(exc).__name__` in enrich-loop error log (was always `"type"`)
13. `epub.py` — `re.DOTALL` on tag regex (multiline HTML attributes left tag fragments in text)
14. `eml.py` — prefer filename-guessed MIME when declared type is default `text/plain` and no `Content-Type` header present (PDFs named `report.pdf` were extracted as plain text)

**Pass 3 — RabbitMQ translate path**
15. `translate_worker.py` — `TranslateConsumer` hardcoded `target_lang="en"` in three call sites; now uses `(doc.target_language or "en")` — non-English configured targets are actually translated

**Verification:** 28/28 targeted tests pass. 28 pre-existing failures in `test_compose_volumes.py` unrelated (airgap compose YAML shape).

**Watch:**
- `.doc`/`.xls`/`.ppt` (legacy Office) still return empty unless `ENABLE_LEGACY_OFFICE=true`.
- Scanned PDFs still need `ENABLE_OCR=true` for any text extraction.
- Consider a backfill job to re-extract documents with previously empty `extracted_text` (XML, RTF, HTML).

## 2026-05-26 — fix: translation read-path + 6-bug sweep + TOCTOU race

Status: Done — main, commits 263171c + e0c74fb + ab3e3ac
Source: Claude Code session

All translation-related bugs found and fixed across three commits.

**Commit 263171c — read-path no-op guard (repository + preview service)**
- `list_versions`: LEFT JOIN `document_payloads`; excludes `available` versions where `translated_text IS NOT DISTINCT FROM content_text` — old DB records created before no-op detection no longer surface in the translation tab.
- `get_translated_text`: same `IS DISTINCT FROM` guard added to all three lookup branches (specific version, latest version, payload fallback).

**Commit e0c74fb — 6-bug sweep**
1. `slow_worker._run_versioned`: added no-op + empty translation guard (matches `runner.py`). Marks version `"failed"` instead of `"available"` for no-ops, so `translation_quality` stays unchanged and the "Request Translation" button is not hidden.
2. `request_translation` API: now publishes to RabbitMQ when enabled (was silently skipping push; auto-enrich did publish). Fixed `"Manual None"` label when `doc.target_language` is `None`.
3. Download endpoint: new `translation_version_id` param; `get_translated_text` now respects it. Frontend `DocumentToolbar` passes `selectedVersionId` so download matches the viewed version.
4. Frontend polling: added `"processing"` to `hasInProgressVersions` in `TranslationVersionSelector` and `DocumentPage` — was missing from the in-progress check, causing polling to stop early.
5. XLSX extractor: `data_only=True` (values not formulas), `read_only=True`, `wb.close()`, catches `InvalidFileException` + `BadZipFile`. Macro-enabled XLSX MIME aliases added to registry.
6. `ExtractorRegistry.has_extractor()`: new method; `_process_attachments` now uses it instead of `get()-is-None` so attachments with uncommon `text/*` MIME types reach translation instead of being silently dropped.

**Commit ab3e3ac — TOCTOU race fix (migration + preview service)**
- Migration `x8y9z0a1b2c3`: `CREATE UNIQUE INDEX idx_dtv_one_active_per_type ON document_translation_versions (document_id, request_type) WHERE status IN ('pending', 'running')`.
- `_maybe_auto_enrich`: replaced racy SELECT-then-INSERT with single atomic `INSERT ... SELECT ... ON CONFLICT (document_id, request_type) WHERE status IN ('pending', 'running') DO NOTHING`. `rowcount == 0` → bail without duplicate job enqueue or RabbitMQ publish.

**Invariant:** A translation version is only surfaced when `translated_text` is non-empty AND `IS DISTINCT FROM content_text`. No-ops are marked `failed`, not `available`. One active `auto_enrich` job per document at a time, enforced at DB level.

**Operator action required:** Run migration `x8y9z0a1b2c3` on next deploy. Set `source_language` on each ingestion source (e.g. `"he"` for Hebrew) — without it LibreTranslate auto-detect silently fails for many binary types.

**Watch:** Attachment files under `files_root/attachments/` accumulate indefinitely — no GC yet. Cleanup job needed when documents are deleted.

## 2026-05-25 — fix: translation no-op detection + download JSON bug

Status: Superseded by 2026-05-26 entry above (EML/archive fallback section updated)
Source: Claude Code session

Two bugs fixed:

**Translation (all file types incl. PDF):**
- `ProcessResult` now carries `translation_quality: str | None` — `"fast"` only when LibreTranslate returned a non-empty result different from input; `None` otherwise.
- `runner.py` skips creating a `document_translation_versions` record when translation was a no-op (translated == extracted). Previously a misleading `quality="fast"` version was created even when LibreTranslate returned the original text unchanged. ~~EML/archive fallback preserved~~ (removed in 2026-05-26 fix — fallback caused original-language text to appear in translation view).
- `worker.py` logs `WARNING` when `source_language` is `None` before translation (auto-detect will be used) and when translation returned unchanged text.
- `ingestion.py` logs `WARNING` when documents are ingested without `source_language`.

**Download (PDF and attachment files):**
- `DocumentToolbar.tsx` download handler now checks `r.ok`; shows `showToast("error", t.document.downloadError)` instead of silently downloading the JSON error body.
- `PipelineWorker` accepts `attachment_store: Path | None`. When set, `_process_attachments` saves attachment files to `attachment_store/{sha256[:2]}/{sha256}{ext}` (persistent, inside `files_root`) instead of `/tmp/` (deleted after pipeline). Files in `/tmp/` are outside `files_root` and were blocked by the path-traversal check → 400 JSON → downloaded as "PDF".
- `runner.py` passes `attachment_store=settings.files_root / "attachments"` to `PipelineWorker`.
- `downloadError` i18n key added to en.ts and he.ts.

## 2026-05-25 — feat: parsers architecture — full file-type extraction & translation coverage

Status: Done — commit 0ec5226, merged to main
Source: Claude Code session; plan at `.claude/plans/design-the-parsers-architecture-curried-nova.md`

5 phases implemented and merged:
- **Phase 1**: `mime_detector.py` (python-magic content-sniffing + mimetypes fallback); registry alias map; removed `octet-stream → PlainExtractor` (was returning binary garbage); connectors use `detect_mime_type()`
- **Phase 2**: `opendocument.py` (OdsExtractor + OdpExtractor); `epub.py` (ebooklib); charset-aware `plain.py` (UTF-8 → charset-normalizer → latin-1)
- **Phase 3**: `language.py` (LanguageDetector, langdetect, ≥100 chars, 0.80 confidence); wired into `worker.py` after extraction; `update_source_language()` on DocumentRepository; migration `v6w7x8y9z0a1` adds `language_detected` bool column
- **Phase 4**: `ocr.py` (OcrExtractor, pytesseract + Pillow); `pdf.py` OCR fallback (`ENABLE_OCR=false` by default)
- **Phase 5**: `legacy_office.py` (LegacyOfficeExtractor, LibreOffice subprocess, 30s timeout; `ENABLE_LEGACY_OFFICE=false` by default)

New core deps: charset-normalizer, ebooklib, langdetect, python-magic
New optional dep group: `[ocr]` = pytesseract + Pillow + pdf2image
New feature flags in Settings: `enable_ocr`, `enable_legacy_office`, `enable_language_detection`
54 unit tests added/updated; mypy strict clean.

Next action:
- Smoke-test by ingesting `.ods`, `.epub`, and a scanned PDF via folder connector; confirm `document_translation_versions.status = 'available'` in DB.
- Consider backfill job to re-process documents with empty `extracted_text` due to previously unregistered MIME types.

## 2026-05-25 — Fix: auto-enrich unconditional call removed from index_worker

Status: Done — committed to main
Source: Claude Code session

`index_worker.py` called `publish_enrich()` for every indexed document. Removed.
Auto-enrich is now only triggered by `PreviewService._maybe_auto_enrich()` (view threshold)
or manual `POST /documents/{document_id}/translate`. Config: `auto_enrich_threshold` (default 5)
reads from `system_config` table key `auto_enrich.threshold`.

## 2026-05-25 — Unit test suite cleanup (21 → 0 failures)

Status: Done — commits f4217a5, a8106d0, 09c300e on main
Source: Claude Code session

Result: **660 passed / 0 failed** (was 638 / 21). 108 ERRORs remain — integration tests
requiring `migrated_engine` fixture (testcontainers + real Postgres); not run in local dev.

Fixes applied (all test-only except alert_consumer):
- `test_consumer_base` — `handle_message` stubs missing `content_text`/`translated_text` kwargs that `_on_message` now passes.
- `test_search_regression` — `alert_consumer.py::main()` used `DeterministicTestEncoder()` directly; replaced with `build_encoder(settings)`.
- `test_rabbit_config`, `test_request_id_middleware`, `test_api_runtime`, `test_api_observability_logging`, `test_metrics_foundation` — `Settings()` loaded `.env` which sets `FEATURE_MEILISEARCH_SEARCH=true`/`RABBITMQ_URL`; fixed with `_env_file=None` in all test `Settings(...)` calls.
- `test_pipeline_worker` — `_FakeDocumentRepositoryWithCreate` lacked `_connection`; `DocumentRelationshipRepository` not patched. Added `_connection = None` + `@patch`.
- `test_meili_rollback`, `test_meili_rollout` — patch target `services.api.main.meilisearch.Client` fails because `meilisearch` is imported lazily inside `create_app()`; changed to `meilisearch.Client`.
- `test_compose_volumes` — `STANDARD_VOLUMES` and `test_standard_compose_defaults` still expected `ollama_data`; updated to `ollama_llm_data` + `ollama_embed_data` following the Ollama split.

Recurring pattern to watch: any test that calls `Settings()` without `_env_file=None` will load the project `.env` file and inherit container values (`RABBITMQ_URL`, `FEATURE_MEILISEARCH_SEARCH`, `EMBEDDING_URL`, etc.). Always add `_env_file=None` to isolate unit tests.

Next action:
- No open items from this work. Pick up next issue from release queue in AGENTS.md.

## 2026-05-25 — feat/400-remaining-slices merged (d6d73d4)

Status: Done — merged to main
Source: Claude Code session; branch feat/400-remaining-slices

Changes (branch-unique files, taken as-is):
- `src/services/vault/service.py` — group-scoped Markdown zip export with wikilink resolution and tag index
- `src/services/api/routers/vault.py` — vault export + tag-index endpoints
- `src/services/api/routers/documents.py` — `/key_points` and `/intelligence` projection endpoints
- `src/services/search/meili_provider.py` — `search_rag_metadata()`, `search_rag_translated()`; duplicate `search_rag()` removed
- `src/services/pipeline/slow_worker.py` — passes `language` to `chunk_text`
- Tests: expanded retrieval eval, chunking language cases

Conflicts (all resolved → keep main — main was superset in every case):
- `reranker.py`, `service.py`, `splitter.py`, `vector_worker.py`, `worker.py`, `main.py`, `documents.py`, `qa.py`

Verification: 61 tests pass, ruff clean.

Deferred items (do not pick up without explicit promotion):
- Meilisearch native embedder — plan at docs/superpowers/plans/2026-05-24-meilisearch-native-embedder.md; sub-issues A–F; branch feature/meili-native-embedder not started.
- Rust vector worker — issue #511, sub-issues #501–#510; branch feature/rust-vector-worker not started; chunker parity is highest risk.

## 2026-05-25 — Search + infra hardening sprint (all merged)

Status: Done — all commits on main
Source: Claude Code session

Changes:
- **Search 504:** `encoder.encode()` blocked 180 s > nginx 110 s. Added `SEARCH_EMBEDDING_TIMEOUT=5 s`; `build_encoder()` accepts `timeout=` override; search path uses 5 s cap so BM25 fallback fires within nginx window. Pipeline indexing timeout unchanged. (7da68a5)
- **Expertise UI:** Removed stale `Comments` signal row — not in backend `ExpertiseSignals` shape. (0a86bf6)
- **`_map_sort` camelCase fix:** Built `"updated_at:desc"` vs valid-set `"updatedAt:desc"` — all date sorts silently returned relevance. Now uses `_MEILI_SORT_MAP` to resolve camelCase field before appending direction. (051a6bd)
- **Test env isolation:** `test_factory_ollama_falls_back_to_ollama_url` read `EMBEDDING_URL` from `.env` file, overriding the fallback under test. Fixed with `_env_file=None` + explicit `embedding_url=""`. (f5c27da)
- **Ollama split (#513):** `ollama` → `ollama-llm` + `ollama-embed`. Role-based model routing (utility/reranker) with fallback chain. 17 routing tests. Operator must `docker compose build ollama-llm ollama-embed` on first deploy.

Next action:
- No open items from this sprint. Pick up next issue from release queue in AGENTS.md.

## 2026-05-24 — D2 MEDIUM ACL hardening (#400 Groups 1-3 final work)

Status: Done — commit ad7ff71 on `claude/funny-faraday-bLPiI`, pushed; PR pending
Source: Claude Code session

Finding:
- **Audit of remaining work**: All Group 1-3 workstreams (A2-A6, B2, E1, E2) were already
  implemented in main. The only genuinely missing work was the 4 MEDIUM ACL items from the D1
  audit (docs/context/acl-audit.md items M1-M4).
- **M1 — /me/activity stale access**: `PreviewService.get_user_activity()` now accepts
  `group_ids` + `allow_all`; adds source_permissions JOIN for non-admins. Router passes
  effective groups via `get_effective_group_ids`. Revoked docs no longer appear in history.
- **M2 — /admin/config secret masking**: `admin/config.py` imports `_SENSITIVE_CONFIG_KEYS`;
  applies `_mask_config_value()` to GET list + PUT update responses. Keys whose names contain
  token/secret/password/api_key/private_key/client_secret are returned as `••••••••`.
- **M3 — /documents/{id}/versions per-version ACL**: After `list_versions_in_family()`,
  non-admin callers have each version filtered via `auth_repo.user_can_access_source()`.
  Cross-source version reassignment no longer leaks inaccessible versions.
- **M4 — /notifications stale access**: `AlertRepository.list_notifications()` accepts
  `group_ids` + `allow_all`; adds source_permissions JOIN for non-admins. Router passes
  effective groups. Stale notifications for revoked docs are hidden.
- **Tests**: 5 new integration tests in `test_acl_hardening.py`; 2 new tests in `test_admin.py`.
  All 58 targeted tests pass. 6 pre-existing unit failures unrelated to this work.
- **mypy**: 323 errors (unchanged baseline).

Impact:
- All 4 MEDIUM ACL gaps from the D1 audit are closed.
- Issue #400 Groups 1-3 are now fully implemented; tracker can be closed once PR merges.

Next action:
- Open PR from `claude/funny-faraday-bLPiI` targeting main with full handoff.

## 2026-05-24 — Search improvements: facets, highlight rendering, instant search

Status: Done
Source: Claude Code session; commit 8dfa896 on `claude/refine-local-plan-ohFc5`

Finding:
- **Facets**: `meili_provider.search()` was discarding `facetDistribution` — now returned via new `SearchResults(results, facets)` wrapper. `metadata.mime_type` added to the requested facet fields (was missing). `SearchResponse` now includes `facets: dict[str, dict[str, int]]`. `FilterPanel` shows live file-type counts and data-driven Tags + Source checkbox sections (top 10 by count). Source and Tags removed from Advanced; Extension remains.
- **Highlight rendering**: `_map_result()` now prefers `_formatted.title` for highlighted title. `"title"` added to `attributesToHighlight`. `ResultRow` renders title + snippet with `dangerouslySetInnerHTML` + `highlightHtml()` sanitizer (strips all HTML except `<mark>`). Mark styled pale yellow via `oklch(97% 0.15 90)`.
- **Instant search**: `useEffect` debounces `inputValue → setSubmittedQuery` at 350ms (min 2 chars). Does not navigate or reset preview state. Explicit Enter/button submit unchanged.
- **Test updates**: 2 meili_provider tests updated for `SearchResults` wrapper (`.results` attribute).

Impact:
- Filter panel is now data-driven instead of static; users see counts and real tag/source options.
- Search highlights appear visually in results without XSS risk.
- Results appear ~350ms after typing without pressing Enter.

Next action:
- Branch `claude/refine-local-plan-ohFc5` ready for PR when approved.

## 2026-05-24 — Frontend code splitting, Ollama num_ctx fix, issue board cleanup, #480

Status: Done
Source: Claude Code session; commits 64a70ad, 4929569 on main

Finding:
- **Frontend initial bundle**: was 1,146 kB (340 kB gz). All 18 page imports in `routes.tsx` were static. Fixed with React.lazy() + Suspense in AppLayout's Outlet + Vite manualChunks. Initial bundle now 30.5 kB (10.2 kB gz). pdfjs-dist (122 kB gz) and highlight.js (17 kB gz) only load on /doc/* routes.
- **Ollama num_ctx warning**: `nomic-embed-text` Modelfile bakes in `PARAMETER num_ctx 8192` but `n_ctx_train=2048`. Modelfile beats `OLLAMA_CONTEXT_LENGTH` env var. Fixed: `OllamaEmbeddingEncoder._embed_batch()` now passes `"options": {"num_ctx": self._max_tokens}` at request level (highest priority in Ollama). Ollama v0.23.2. 2 new unit tests.
- **#480 Enter to submit**: Both `CommentComposer` and `AnnotationEditor` now submit on Enter, insert newline on Shift+Enter. Hint text shown. 4 new unit tests.
- **Issue board**: #365 (RabbitMQ mission) closed — all 8 sub-issues shipped. #482 closed — "Why related?" already implemented (badges + expandable panel in InsightPane RelatedTab). Labels added to #480, #481, #482, #438, #511.
- **#481 threaded comment replies**: Backend comments router has NO reply support (no parent_id, no routes). Correctly deferred. Needs migration + backend + frontend before picking up.

Impact:
- UI loads ~3× faster on first visit (on fast connection, 10 kB shell vs 340 kB monolith).
- Ollama warning gone; no wasted KV-cache memory on embedding calls.
- Enter-to-submit UX parity across all annotation and comment inputs.

Next action:
- Pick up #481 only after adding comment reply DB migration + backend routes.
- Remaining AI workstreams for #400 (groups 1–3): A2–A6, B2, D2 remainder, E1–E2.

## 2026-05-24 — Download 500 on non-ASCII filenames + three user-facing issues

Status: Done
Source: OpenCode session (chat summary)

Finding:
- **Download 500**: `UnicodeEncodeError: 'latin-1' codec can't encode characters` when `doc.path` contains non-ASCII characters. Content-Disposition headers used raw `filename="{name}"` which fails because HTTP headers must be latin-1 encodable. Fixed all 3 occurrences in `documents.py` with `_content_disposition()` helper that uses RFC 5987 `filename*=UTF-8''<url-encoded>` + ASCII `filename=` fallback.
- **"original shows translated version"**: Not a code bug — both `content_text` and `translated_text` contain the same value when translation silently returns the original text (LibreTranslate unavailable or returns same text). The frontend Original/Translation tabs both show the same text.
- **"translated version doesnt translate the name"**: The pipeline only translates `content_text`, never `doc.title`. Title translation is not implemented — would require adding title to the translation message and storing a translated title field.
- Same vault.py pattern (`filename="vault-{group_id}.zip"`) is safe because `group_id` is always ASCII (UUID).

Impact:
- Download works for documents with non-ASCII filenames (e.g. accented characters, CJK).
- Title translation is a missing feature, not a bug.
- `npm run build` passes cleanly (vite v8, 1986 modules, 861ms). No errors — only chunk-size advisory warning.

Next action:
- Consider adding title translation to the pipeline: pass `title` in translate message, store `translated_title` on documents table, display in translation view mode.

## 2026-05-24 — TranslateConsumer fixes + frontend stage view separation

Status: Done
Source: OpenCode session (chat summary)

Finding:
- **TranslateConsumer early return skipped stage update**: When `content_text` was empty (no extractable text), TranslateConsumer returned before `mark_running_stage("translated")`, leaving stage at "parsed" while downstream workers (embed, index) advanced it to "embedded"/"indexed". Frontend showed translate as "waiting" but later stages "done". Fixed by adding `mark_running_stage(job_id, "translated")` before the early return.
- **source_language read from wrong table**: TranslateConsumer read `source_language` from `document_payloads` (via `get_payload`) which has no such column — only `content_text`, `content_path`, `content_sha256`, `translated_text`. `source_language` is on the `documents` table. Fixed by reading `doc.source_language` via `doc_repo.get_by_id()` instead. This ensures LibreTranslate uses the known source language instead of always defaulting to "auto".
- **Frontend**: In the expanded pipeline stage view, "waiting" status now renders as a muted `—` instead of a neutral badge, making it visually distinct from "done" (green success badge).
- Same `source_language` issue exists in `EnrichConsumer` but requires adding `doc_repo` parameter — deferred.

Impact:
- Pipeline stage progression is now monotonic even when content_text is empty.
- Translation uses the actual source language from the documents table.
- Frontend expanded view clearly separates pending stages (muted dash) from completed stages (green badge).

Next action:
- Fix `EnrichConsumer` source_language lookup if enrich worker is active.

## 2026-05-23 — RabbitMQ stage-based job bus (#432) merged to main

Status: Done — all 7 sub-issues complete, PR #512 merged, branch deleted
Source: OpenCode session (chat summary)

Finding:
- RabbitMQ stage-based job bus (#432) fully implemented and merged to main.
- 7-stage pipeline: parse → translate → embed → index → intelligence/alert (parallel) + enrich.
- 20+21+21 = 62 RabbitMQ queues (7 stage + 7 DLQ + 7 retry per stage × 3 exchanges).
- 6 Docker compose services: parse, translate, embed, index, intelligence, alert, enrich workers.
- `RABBITMQ_ENABLED=true` (default) with DB-poll fallback. Zero impact when false.
- Admin monitoring: GET /admin/rabbit/queues (live depth), GET /admin/jobs, POST retry.
- Air-gap support: validate script, compose service, image manifest, CHANGELOG entry.
- CI: PostgreSQL test job (20min timeout), SQL boolean-int lint script.
- 13 unit tests passing (rabbit config, client, publisher, consumer base, admin routes).

## 2026-05-23 — Document quality-of-life improvements

Status: Done
Source: OpenCode session (chat summary)

Finding:
- Related documents (#482): structured reasons (semantic, entities, tags, source) with expandable "Why related?" panel.
- Translation auto-detect: TranslateConsumer now passes `None` to LibreTranslate (auto-detect). Admin source default no longer forces "en".
- Download: supports both original file and translated text (.txt). Works for all connectors (NiFi, Atlassian, SMB). Clear error messages for missing files.
- EnrichConsumer: high-quality re-translation via RabbitMQ for frequently viewed documents (auto_enrich threshold).
- Pipeline efficiency: embedding batching (encode_batch), intelligence task parallelism (ThreadPoolExecutor), map-reduce parallelism, model caching (OLLAMA_KEEP_ALIVE=4h, MAX_LOADED_MODELS=2).
- Error visibility: _sanitize_error includes error message, not just class name.
- Boolean-int SQL fixes: 5 instances fixed (is_private, is_latest); lint script prevents recurrence; PostgreSQL CI test.
- UI: full-width admin pages, live duration ticking, 7-stage pipeline order, reason pills on related docs.
- Ollama: better prompts (JSON format, examples), temperature 0.2, embedding timeout 180s.
- Download: fetch() with JWT auth replaces raw <a> link (was downloading 401 JSON). Supports original + translated.
- TranslateConsumer: creates document_translation_versions records so frontend shows translation view mode.
- DB-poll split: when RABBITMQ_ENABLED=true, process_document job marked succeeded immediately — only RabbitMQ pipeline processes documents (no duplicate work).
- CI: ruff/mypy clean on 141 files; PostgreSQL 20min timeout; pytest + Alembic migrations passing.

Next action:
- Sub #501: Cargo workspace scaffold + CI for Rust vector worker.

## 2026-05-23 — Chat defaults + Qdrant bootstrap + SSE fix + Edit Source page

Status: Done
Source: OpenCode session (chat summary)

Finding:
- Chat feature flags (`feature_document_chat*`) now default to True in `src/shared/config.py`.
- Qdrant collection now auto-created on first search (not just on upsert), fixing "Collection doesn't exist" error.
- SSE streaming endpoint fixed: manual connection management replaces `with engine.begin()` so connection stays alive during streaming generator.
- `/qa` removed from nav rail and routes; chat replaces it.
- Admin Edit Source page created at `/admin/sources/$sourceId/edit` with full form (name, language, connector fields, path, enabled, schedule).
- Cron schedule field added: migration (`schedule TEXT`), backend schema + routes, frontend types + edit form + detail display.
- Node.js default bumped to v22 (was v20.9.0) to fix vitest/ESLint `styleText` compat.

Impact:
- Chat works out-of-box. Qdrant auto-creates collections. SSE streaming persists messages.
- Sources have edit page + cron schedule + document pipeline view + delete.
- All Python tooling uses `uv` (fast resolution, reproducible lockfile).
- Mistral + nomic-embed-text coexist in 6g Ollama container (keep_alive=4h, max_models=2).
- Related documents show structured reasons (#482). Boolean-int SQL bugs fixed + lint guard + PG CI.
- Pipeline embedding batched (N HTTP calls → 1), intelligence tasks parallelized, map-reduce parallel.
- Error messages visible in admin UI (sanitize now includes first line of error text).
- Ollama timeouts: generate 300s, embed 180s. Summary empty fallback uses first sentence.
- UI uses full screen width on admin/expertise/history/notifications pages (max-width removed).

Next action:
- None. All tasks from this session complete.

## 2026-05-22 — Document details & advanced search track complete (#483–#489)

Status: Done — all 7 issues implemented
Source: PRs #493–#499; plan at `docs/implementation/document-details-and-search.md`

Finding:
- All 7 issues in the track complete:
  - #485 Markdown preview
  - #486 User-managed private/public document tags
  - #487 Comments unified into annotations with threaded replies
  - #488 Document relationships table + pipeline wiring
  - #483 Expanded details panel with grouped collapsible sections
  - #484 Advanced search filter pipeline + URL-driven filter state
  - #489 Clickable detail values linking to pre-populated search
- Integration PR merged; feature branch `feature/document-details-and-search` → `main` complete.

## 2026-05-22 — Document viewer MVP complete (#453 closed)

Status: Done
Source: issues #440–#451; PRs #454–#465; integration PR #466 merged to `main`

Finding:
- All 12 document viewer child issues implemented and merged to `main` via PR #466.
- Parent issue #453 closed. All child issues (440-451) closed.

## 2026-05-21 — Resource safety guards (#463)

Status: Done
Source: issue #463; PR #467

Finding:
- Added Compose resource limits (cpus, mem_limit, mem_reservation, pids_limit) to 9 services: api, pipeline-worker, vector-worker, ollama, libretranslate, elasticsearch, qdrant, meilisearch, postgres — all via env vars.
- Ollama safety defaults: OLLAMA_CONTEXT_LENGTH=2048, OLLAMA_MAX_LOADED_MODELS=1, OLLAMA_NUM_PARALLEL=1, OLLAMA_MAX_QUEUE=8, OLLAMA_KEEP_ALIVE=1m.
- Workers already process one job per loop iteration (built-in backpressure); no Python code changes needed.
- Docs: Resource Safety Guards section in production-compose.md with per-RAM-tier guidance, capacity warning, overload response procedure.
- Baseline total: ~15 GB memory limit, ~4 GB reservation for all services at 1 replica.
- Merged to main via PR #467.

## 2026-05-21 — Python dependency audit fix

Status: Done
Source: Security CI failure on PR #466

Finding:
- pip-audit found PYSEC-2025-183 in pyjwt 2.12.1 (no fix version available).
- pip CVEs (CVE-2025-8869, CVE-2026-1703, CVE-2026-3219, CVE-2026-6357) are infrastructure-only — CI runner already has pip 26.1.1.
- Fix: added `--ignore-vuln PYSEC-2025-183` to pip-audit command in security.yml.

## 2026-05-22 — Vector embedding context-length safety (#468)

Status: Done
Source: issue #468; commit 30bc196 merged to `main`

Finding:
- `chunk_text()` accepts `max_tokens` param; oversized chunks split via token-estimate heuristic (chars/4).
- OllamaEmbeddingEncoder validates text token count before API call, catches 400 as ValueError.
- ValueError dead-letters immediately in vector_worker (permanent error).
- PipelineWorker threads `embedding_max_tokens` to chunking calls.
- New config: `EMBEDDING_MAX_TOKENS` (default 1024).
- Verified: ruff check, ruff format, mypy (strict) — all clean.
- Tests: 19 chunking + 32 encoder/worker tests pass.

Impact:
- Oversized chunks are recursively split before reaching the encoder.
- Encoder validates each text's estimated token count before API call.
- ValueError (context-length exceeded) dead-letters immediately instead of retrying 5 times.

## 2026-05-22 — Document Chat Phase C frontend complete (#474)

Status: Done
Source: issue #474; commits d352ed2 + 8fa4f95 on `feature/document-chat`

Finding:
- ScopeBadge, ScopeSelector, DocumentChatPanel, InsightPane Chat tab migration complete.
- `single_document` scope auto-created via DocumentChatPanel; `all_accessible_documents` switchable via ScopeSelector.
- Document Page InsightPane's "QA" tab replaced with "Chat" tab using DocumentChatPanel.
- `feature.document_chat` removed from SYSTEM_CONFIG_DEFAULTS (env-var is correct gate).
- Sidebar, message list, citations, empty/loading/error states all tested.

Next action:
- Verify CI on `feature/document-chat`; open PR targeting `main`.

## 2026-05-22 — In-document search fix verified + closed (#469)

Status: Done
Source: issue #469; commit 2927a50 on `main`

Finding:
- Fix commit 2927a50 covers all 7 renderers: PreviewPane passes search props to DOCX/RTF TextPreview, TablePreview, ArchivePreview, EmailPreview, SlidesPreview, PdfViewer, CodeViewer.
- PdfViewer: per-page text extraction + page-jump navigation via activeSearchIndex.
- TextPreview virtualized: per-line cumulative match offsets for correct global active-match navigation.
- Missing tests added (commit 48153a9): 8 test files covering all AC #5 criteria — PreviewPane prop routing, PdfViewer page nav, virtualized global index, DocumentPage Ctrl+F toggle, EmailPreview/SlidesPreview/ArchivePreview/TablePreview search.
- TypeScript check clean. Issue closed.

## 2026-05-22 — Document Chat Phase D — query rewrite (#475)

Status: Done
Source: issue #475; design §9

Finding:
- D1: `rewrite_query()` — `src/services/chat/message_service.py`. Handles
  history window (last 4 user+assistant pairs), skip on first turn, fallback on Ollama error.
- D2: Wired into router — `POST /chat/sessions/{id}/messages` loads prior messages,
  calls `rewrite_query` when `FEATURE_DOCUMENT_CHAT_QUERY_REWRITE=true`, passes
  `rewritten_query` to the persisted assistant message.
- D3: 6 unit tests covering all rewrite behaviors.
- D4: Admin debug panel — collapsed `<details>` block in assistant message bubble
  shows `rewritten_query` when present. 6 component tests.
- Bugfix: `rag.answer(question=body.content)` → `question=question` (used raw
  input instead of possibly-rewritten query).
- Feature flag: `FEATURE_DOCUMENT_CHAT_QUERY_REWRITE` (default `false`).
- Verified: ruff, ruff format, mypy strict — clean. 44 unit + 28 frontend tests pass.
- Issue #475 closed.

Next action:
- Phase E (#476): retrieval quality (hybrid, metadata, translations, reranker).

## 2026-05-22 — Document Chat Phase F — Citation UX (#477)

Status: Done
Source: issue #477; commits on `feature/document-chat`

Finding:
- F1: `page_number`, `section_heading`, `language`, `translated_from` in backend Citation model, Qdrant/Meili metadata, router response.
- F2: `ChatCitationCard` displays `p. N · Section Name` when present.
- F3: Citation `<Link>` includes `?page=N&chunk=M`, opens in new tab.
- F4: `DocumentPage` reads `?page=N` search param via `useSearch`, `scrollIntoView` on mount.
- F5: "Translated from [language]" italic indicator on translated citations.
- 7 new `ChatCitationCard.test.tsx` tests.
- Verified: 423 frontend + 124 backend tests pass.

## 2026-05-22 — Document Chat Phase G — Streaming and polish

Status: Done
Source: Phase G table in document-chat-design.md; commits on `feature/document-chat`

Finding:
- G1: SSE streaming endpoint `POST /chat/sessions/{id}/messages/stream` — Ollama streaming via `generate_stream()`, `RagService.answer_stream()` yielding `(event, data)` tuples, `StreamingResponse` SSE formatting. Behind `FEATURE_DOCUMENT_CHAT_STREAMING` flag.
- G2: Frontend streaming UI — `sendChatMessageStream()` SSE reader in `api/chat.ts`, phase indicators ("Searching"/"Reading sources"/"Generating") in `ChatInput`, incremental message rendering in `ChatWindow`.
- G3: `StarterQuestions` component — scope-aware question suggestions when session is empty.
- G5: `autoFocus` on `ChatInput` when session loads, `aria-busy` on `MessageList` during streaming, 6 `StarterQuestions` tests.
- G4: Grafana panel — human task, not yet started.
- Verified: 429 frontend tests (61 files), 44 backend chat unit tests, `tsc --noEmit` clean.

## 2026-05-22 — Document Chat merged to main (#492)

Status: Done
Source: PR #492; commit e299390 on `main`

Finding:
- `feature/document-chat` branch merged to `main` via squash commit e299390.
- All prior issues (#473–#477) closed.
- Final CI: Frontend CI, Container CI, Docs CI all green. 429 frontend tests, 44 backend chat unit tests. `npm run build` passes. `npm run lint`: 0 errors. `npm run typecheck`: clean. `ruff check` clean, `mypy --strict` clean.
- Feature branch deleted. All automated phases complete.

## 2026-05-22 — Sign-out button added to NavRail (#490)

Status: Done
Source: Issue #490; commit 2a239ae

Finding:
- User identity (display_name + email) and Sign out button added to NavRail sidebar bottom section.
- `NavRail` receives `userDisplayName`/`userEmail` from `AppLayout` → `AppShell`.
- Clicking Sign out calls existing `logout()` (API + token clear), clears TanStack Query cache via `queryClient.clear()`, navigates to `/login`.
- Button disabled during sign-out. User info hidden on mobile (same as other bottom items).
- 6 new NavRail tests cover: nav items, admin item, user info, sign-out button, click behavior, disabled state.
- Verified: 62 test files / 435 tests pass, `tsc --noEmit` clean, `npm run lint` 0 errors.

## 2026-05-22 — Admin Users UI (#491)

Status: Done
Source: Issue #491; commit a5c56b6

Finding:
- Backend: PATCH /admin/users/{user_id} with UpdateUserRequest (display_name, is_admin). Last-admin guard prevents removing admin from the sole admin.
- Frontend: AdminUsersPage with user table (email, display_name, admin badge, auth source). AdminUserDetailPage with editable display_name, is_admin toggle, group membership list.
- AdminHubPage: added Users card linking to AdminUsersPage.
- Integration tests: 51 passing (5 new for PATCH — last-admin, role change, display name, bad user_id, invalid payload).
- Unit tests: 34 passing (6 AdminUsersPage + 6 AdminUserDetailPage).
- Verified: ruff check, ruff format, mypy --strict, npm run lint (0 errors), npm run typecheck — all clean.

## 2026-05-20 — Shared agent skills setup

Status: Done
Source: project manager chat summary

Finding:
- Shared `.claude/skills/` skill library added for Claude Code and OpenCode.
- Project-local OpenCode agent definitions added under `.opencode/agents/`.
- Repo-owned Markdown memory live under `docs/memory/`.

Impact:
- Agents read relevant skills and memory before broad repo exploration.

Next action:
- None. Setup complete.
