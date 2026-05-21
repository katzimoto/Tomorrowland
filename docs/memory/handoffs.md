# Tomorrowland Handoffs

Shared record for concise cross-agent handoffs that remain useful after a chat or tool session ends.

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

## 2026-05-21 — Document Chat Phase C backend scope-aware chat complete

Status: Done
Source: issue #474, commit d7ab8e8 on feature/document-chat

What changed:
- `src/services/chat/models.py` — `ChatScope` model: `Literal` scope_type, `list[str]` scope_ids, pydantic model_validator for cardinality rules.
- `src/services/rag/service.py` — `build_qdrant_filter(scope, group_ids, allow_all) -> Filter | None`: builds combined permission+scope Qdrant filter. Returns None for admin+all_accessible. Imported into RagService._retrieve_chunks as the scope path.
- `src/services/search/qdrant.py` — `search_filtered(vector, query_filter, limit)`: new method for pre-built filter; existing `search()` unchanged (preserves /qa compat).
- `src/services/api/routers/chat.py` — scope validation on every message: builds ChatScope from session, checks revoked access (409) for single_document/selected_documents/current_search_results, returns 400 for folder scope (deferred), passes scope to RagService.
- `tests/unit/test_chat_service.py` — 17 new tests for ChatScope validation and build_qdrant_filter conditions.
- `tests/integration/test_chat_api.py` — 8 new scope integration tests.

Key decisions:
- `build_qdrant_filter` returns `None` (not empty Filter) for admin+all_accessible; Qdrant treats None as "no filter".
- `folder` scope rejected at router level (400) — Qdrant payload has no folder field.
- `source` scope: filter by `source_id` works; revocation validation deferred (group filter applied for safety).
- Revocation check uses `AuthRepository.document_source_id()` + `user_can_access_source()`.
- Admin (is_admin=True) bypasses revocation check entirely.

Verification:
- `pytest tests/unit/test_chat_service.py tests/unit/test_chat_repository.py tests/integration/test_chat_api.py --no-cov` — **68 passed**
- `pytest tests/unit/test_rag_retrieval_eval.py tests/unit/test_rag_reranker.py --no-cov` — **17 passed** (RAG eval unbroken)
- `ruff check` + `ruff format` — clean
- `mypy src/services/chat/models.py src/services/search/qdrant.py src/services/rag/service.py src/services/api/routers/chat.py --strict` — no issues

Open risks:
- `source` scope revocation validation not implemented (TODO in code) — group filter still prevents data leakage.
- Meilisearch BM25 results (when Meili enabled) are not scope-filtered at the document level — pre-existing gap, not in Phase C scope.
- Frontend vitest blocked by Node 20.9.0 locally; CI is sole gate.

Frontend Phase C can start — backend scope API is complete and tested.

Next agent prompt:
- Phase C frontend: ScopeBadge, ScopeSelector, InsightPane Chat tab migration (use existing ChatWindow + ChatScope data from session).

## 2026-05-21 — Document Chat Phase B7 lifecycle tests complete

Status: Done
Source: issue #473, commit 553c263 on feature/document-chat

What changed:
- `src/services/api/routers/chat.py` — typed `session_id` path params as `UUID` (all 4 route handlers); FastAPI now validates on entry (422 on bad input, not 500).
- `tests/integration/test_chat_api.py` — fixed `_settings()` to disable Meilisearch flags; fixed `_setup_users()` to seed `feature.document_chat = true` in system_config; fixed invalid-UUID test fixture; added 8 new lifecycle tests (cross-user 403, empty content 422, invalid UUID 422, citations field shape, messages gone after delete, no cross-user session leakage, degraded RAG fallback).
- `tests/unit/test_chat_repository.py` — added 3 tests: citations JSON round-trip, retrieval_trace round-trip, archive/unarchive semantics.
- `frontend/src/features/chat/ChatPage.test.tsx` — added 5 tests: citation legacy/new field fallback, session load spinner, input disabled while pending, input cleared after send, session load error.

Key discoveries:
- **Dual-gate feature flag**: `/chat` routes check `Settings.feature_document_chat` AND `system_config.feature.document_chat`. Foundation migration seeds the DB key as `False` (production default). Tests must override both.
- **Meilisearch env leakage**: `.env` sets `FEATURE_MEILISEARCH_SEARCH=true`; `_settings()` must explicitly override to `False` or tests fail trying to connect to `meilisearch:7700`.
- **Citation field duality**: ChatCitationCard supports both `doc_title`/`chunk_text` (legacy) and `document_title`/`text_excerpt` (new). Both paths are now test-covered.

Verification:
- `pytest tests/integration/test_chat_api.py tests/unit/test_chat_repository.py` — 43 passed
- `ruff check` + `ruff format` — clean
- `mypy src/services/chat/ src/services/api/routers/chat.py --strict` — no issues
- `tsc --noEmit` — exit 0
- Frontend vitest blocked by Node 20.9.0 (requires 22+) — CI will verify

Open risks:
- Frontend test suite not run locally — CI is sole gate for ChatPage.test.tsx changes
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
- Vitest blocked by pre-existing Node 20.9 / Node 22 gap — CI will run
- `npm run lint` — same Node gap blocks formatter output

Open risks:
- Vitest/ESLint need Node 22 to run locally — CI is the only test gate for now
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
- Frontend vitest unavailable locally (Node 20.9.0, needs 22+) — pre-existing env issue

Open risks:
- Frontend test suite not run locally due to Node version gap — CI will verify

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

Status: Active
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

Status: Active
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

## 2026-05-20 — Agent skills and memory branch

Status: Active
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
