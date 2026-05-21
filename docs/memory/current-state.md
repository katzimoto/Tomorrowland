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

Status: Active
Source: issue #450; PR #464

Finding:
- #450 (a11y, perf, telemetry hardening) — Done. PR #464 targets `feature/document-viewer`.
- A11y: download link aria-label, table aria-label + th scope="col", sr-only status text, focus management on view mode switch and search close.
- Perf: TextPreview virtualized with react-window v2 `List` when >10K lines; TablePreview virtualized with ARIA role-based table when >1K rows.
- Telemetry: viewer.text/pdf/image.load events via named performance timers.
- Backend: X-Content-Type-Options: nosniff on download endpoint.
- react-window v2 key differences from v1: `List` replaces `FixedSizeList`, `rowCount`/`rowHeight`/`rowComponent` props, `rowProps={{}}` required (crashes if undefined).
- ResizeObserver global mock added to test setup (required by react-window v2 in jsdom).

Impact:
- react-window@2.2.7 added to frontend dependencies.
- Virtualized TablePreview uses `role="table"` / `role="rowgroup"` / `role="row"` / `role="columnheader"` / `role="cell"` instead of native `<table>` / `<thead>` / `<tbody>` / `<tr>` / `<th>` / `<td>` (react-window constraint).
- `src/test/setup.ts` now includes ResizeObserver mock, scrollIntoView mock, HTMLDialogElement mocks.
- Download endpoint returns `X-Content-Type-Options: nosniff` on both full and range responses.

Next action:
- Check parent issue #453 for remaining MVP child issues.
- Consider browser-based virtualization verification (#451 follow-up).

## 2026-05-21 — Document viewer test suite (#451)

Status: Active
Source: issue #451

Finding:
- #451 test suite work started. PR targeting `feature/document-viewer`.
- PreviewPane MIME dispatch tests now cover all renderers (archive, email, unsupported, html, table, slides, audio/ogg, video/webm, text/csv, DOCX, RTF).
- Zip bomb backend unit test added to archive extraction tests.

Impact:
- 372 frontend tests (was 359).
- 8 backend archive extraction tests.

Next action:
- Complete remaining #451 items: security tests (HTML injection, iframe sandbox), integration tests (corrupt PDF, corrupt ZIP, file missing), mobile/layout tests.

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
