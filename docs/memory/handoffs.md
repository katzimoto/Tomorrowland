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
