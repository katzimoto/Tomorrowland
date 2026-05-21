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
