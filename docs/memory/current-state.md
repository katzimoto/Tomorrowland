# Tomorrowland Current State

Canonical shared memory for active project state. Keep this file compact and factual.

## 2026-05-21 — Document viewer track in progress

Status: Active
Source: issues #440–#445, #453; PRs #454–#459

Finding:
- Document viewer MVP track (parent #453) is underway.
- #440 (HTML sandbox) — Done. PR #454 merged to `main`.
- #441 (full text API) — Done. PR #455 merged to `feature/document-viewer`.
- #442 (PDF.js viewer) — Done. PR #456 merged to `feature/document-viewer`.
- #443 (view mode switcher + fidelity bar) — Done. PR #457 merged to `feature/document-viewer`.
- #444 (image viewer) — Done. PR #458 merged to `feature/document-viewer`.
- #445 (metadata Details tab) — Done. PR #459 open, targets `feature/document-viewer`.
- `feature/document-viewer` integration branch exists on remote.
- TextPreview fetches full text via `GET /documents/{document_id}/text` in 10K chunks.
- ViewModeSwitcher drives activeMode (original/extracted/translation) in DocumentPage.
- FidelityStatusBar renders between toolbar and viewer body.
- ImageViewer replaces ImagePreview; zoom state lifted to DocumentPage.
- DetailsTab: `<dl>` component in InsightPane "Details" tab; uses PreviewResponse new fields.

Impact:
- PreviewPane accepts `activeMode`, `selectedVersionId`, `imageZoom`, `onImageZoomChange`.
- DocumentToolbar shows image zoom controls when `showImageControls=true` (image mime + original mode).
- InsightPane accepts `preview?: DocumentPreview` prop for DetailsTab.
- Backend PreviewResponse extended: `source_language`, `target_language`, `status`, `content_sha256`, `created_at`, `updated_at`.

Next action:
- Merge PR #459 into `feature/document-viewer`, then start #447 (Code/syntax viewer).

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
