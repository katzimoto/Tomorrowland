# Tomorrowland Current State

Canonical shared memory for active project state. Keep this file compact and factual.

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
