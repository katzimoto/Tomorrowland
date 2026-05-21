# Tomorrowland Current State

Canonical shared memory for active project state. Keep this file compact and factual.

## 2026-05-21 — Document viewer track in progress

Status: Active
Source: issues #440, #441, #442, #453; PRs #454, #455

Finding:
- Document viewer MVP track (parent #453) is underway.
- #440 (HTML sandbox) — Done. PR #454 merged to `main`.
- #441 (full text API) — Done. PR #455 open, targets `feature/document-viewer`.
- #442 (PDF.js viewer) — Ready to start. Blocked on #441 merging first.
- `feature/document-viewer` integration branch exists on remote (created 2026-05-21).
- TextPreview now fetches full text via `GET /documents/{document_id}/text` in 10K chunks.

Impact:
- #442 must branch from `feature/document-viewer` after #441 merges, not from `main`.
- PreviewPane passes `docId` to TextPreview for all text-based MIME types.
- `application/pdf` still dispatches to TextPreview (changed in #442 to PdfViewer).

Next action:
- Merge PR #455 into `feature/document-viewer`, then start #442.

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
