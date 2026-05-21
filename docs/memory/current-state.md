# Tomorrowland Current State

Canonical shared memory for active project state. Keep this file compact and factual.

## 2026-05-21 — Document viewer track in progress

Status: Active
Source: issues #440–#443, #453; PRs #454–#457

Finding:
- Document viewer MVP track (parent #453) is underway.
- #440 (HTML sandbox) — Done. PR #454 merged to `main`.
- #441 (full text API) — Done. PR #455 merged to `feature/document-viewer`.
- #442 (PDF.js viewer) — Done. PR #456 merged to `feature/document-viewer`.
- #443 (view mode switcher + fidelity bar) — Done. PR #457 open, targets `feature/document-viewer`.
- `feature/document-viewer` integration branch exists on remote.
- TextPreview fetches full text via `GET /documents/{document_id}/text` in 10K chunks.
- ViewModeSwitcher drives activeMode (original/extracted/translation) in DocumentPage.
- FidelityStatusBar renders between toolbar and viewer body.

Impact:
- PreviewPane now accepts `activeMode`/`selectedVersionId`; extracted/translation modes override MIME dispatch to TextPreview.
- `showOriginal` is now derived from `activeMode` (not separate state) in DocumentPage.
- DocumentPage.test.tsx now mocks `getDocumentText` in beforeEach.

Next action:
- Merge PR #457 into `feature/document-viewer`, then identify next issue in #453 track.

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
