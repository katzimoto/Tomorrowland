# Tomorrowland Current State

Canonical shared memory for active project state. Keep this file compact and factual.

## 2026-05-21 — Document viewer track in progress (#440–#449)

Status: Superseded
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

## 2026-05-21 — Document viewer a11y, perf, telemetry hardening (#450)

Status: Done
Source: issue #450; PR #464

Finding:
- A11y: download link aria-label, table aria-label + th scope="col", sr-only status text, focus management on view mode switch and search close.
- Perf: TextPreview virtualized with react-window v2 `List` when >10K lines; TablePreview virtualized with ARIA role-based table when >1K rows.
- Telemetry: viewer.text/pdf/image.load events via named performance timers.
- Backend: X-Content-Type-Options: nosniff on download endpoint.

Impact:
- react-window@2.2.7 added to frontend dependencies. v2 API: `List`, `rowCount`/`rowHeight`/`rowComponent`, `rowProps={{}}` required.
- Virtualized TablePreview uses ARIA roles instead of native `<table>` (react-window constraint).
- `src/test/setup.ts`: ResizeObserver mock, scrollIntoView mock, HTMLDialogElement mocks.
- Download endpoint returns `X-Content-Type-Options: nosniff` on both full and range responses.

## 2026-05-21 — Document viewer test suite (#451)

Status: Active
Source: issue #451

Finding:
- PreviewPane MIME dispatch tests cover all renderers (archive, email, unsupported, html, table, slides, audio/ogg, video/webm, text/csv, DOCX, RTF, XLSX, PPTX).
- Security: HTML injection verified (srcdoc passthrough, sandbox tokens), iframe sandbox attribute asserted.
- Corrupt PDF unit test: truncated PDF returns empty string.
- File missing fix: download endpoint returns 404 (FileNotFoundError → HTTPException).
- Mobile layout: toolbar renders all primary actions at 375px.
- Zip bomb resilience: ZipExtractor handles large compressed data.
- Nosniff test fixed: files_root override in Settings.

Impact:
- 375 frontend tests (was 359). 25 backend tests (3 PDF + 8 archive + 14 integration).
- Backend bug fix: FileNotFoundError in download endpoint now returns 404 instead of 500.
- Nosniff integration test corrected (files_root override).

Next action:
- Remaining #451: insight pane stacking (needs browser test), full integration tests (PDF end-to-end, translation switching).

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
