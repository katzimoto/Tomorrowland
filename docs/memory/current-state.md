# Tomorrowland Current State

Canonical shared memory for active project state. Keep this file compact and factual.

## 2026-05-21 — Document viewer track in progress

Status: Active
Source: issues #440–#449, #453; PRs #454–#462

Finding:
- Document viewer MVP track (parent #453) is underway.
- #440 (HTML sandbox) — Done. PR #454 merged to `main`.
- #441 (full text API) — Done. PR #455 merged to `feature/document-viewer`.
- #442 (PDF.js viewer) — Done. PR #456 merged to `feature/document-viewer`.
- #443 (view mode switcher + fidelity bar) — Done. PR #457 merged to `feature/document-viewer`.
- #444 (image viewer) — Done. PR #458 merged to `feature/document-viewer`.
- #445 (metadata Details tab) — Done. PR #459 merged to `feature/document-viewer`.
- #447 (code/syntax viewer) — Done. PR #460 merged to `feature/document-viewer`.
- #448 (media viewer) — Done. PR #461 merged to `feature/document-viewer`.
- #449 (in-document search) — Done. PR #462 merged to `feature/document-viewer`.
- `feature/document-viewer` integration branch exists on remote.
- TextPreview fetches full text via `GET /documents/{document_id}/text` in 10K chunks.
- ViewModeSwitcher drives activeMode (original/extracted/translation) in DocumentPage.
- FidelityStatusBar renders between toolbar and viewer body.
- ImageViewer replaces ImagePreview; zoom state lifted to DocumentPage.
- DetailsTab: `<dl>` component in InsightPane "Details" tab; uses PreviewResponse new fields.
- CodeViewer: highlight.js bundled syntax viewer; dispatches JSON/XML/YAML/source MIMEs from PreviewPane.
- MediaPreview: native audio/video with byte-range backend support; transcript from snippet.
- In-document search: Ctrl+F/Cmd+F opens DocumentSearchBar; match highlights via `<mark>` in TextPreview/CodeViewer; match count reported by PdfViewer; cell highlight in TablePreview.

Impact:
- PreviewPane accepts `activeMode`, `selectedVersionId`, `imageZoom`, `onImageZoomChange`, `searchQuery`, `activeSearchIndex`, `onMatchCountChange`.
- DocumentToolbar shows image zoom controls when `showImageControls=true`; shows search toggle button when `searchable=true`.
- InsightPane accepts `preview?: DocumentPreview` prop for DetailsTab.
- Backend PreviewResponse extended: `source_language`, `target_language`, `status`, `content_sha256`, `created_at`, `updated_at`.
- `Element.prototype.scrollIntoView = vi.fn()` added to `frontend/src/test/setup.ts` (jsdom compat).

Next action:
- Check parent issue #453 for remaining MVP child issues after #449.

## 2026-05-20 — Shared agent skills setup

Status: Active
Source: project manager chat summary

Finding:
- Add a shared `.claude/skills/` skill library for Claude Code and OpenCode.
- Add project-local OpenCode agent definitions under `.opencode/agents/`.
- Add repo-owned Markdown memory under `docs/memory/`.

Impact:
- Future agent work should load only the relevant skills and memory files before broad repo exploration.
- Project memory should be easy to review in git.

Next action:
- Finish wiring skills, memory files, and OpenCode agent definitions.
