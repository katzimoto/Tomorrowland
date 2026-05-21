# Tomorrowland Decisions

Shared record for durable architecture, product, and agent workflow decisions.

## 2026-05-21 — TextPreview is API-driven via docId prop

Status: Active
Source: issue #441, PR #455

Decision:
- `TextPreview` accepts an optional `docId` prop. When provided, it fetches full text from `GET /documents/{document_id}/text` in 10K chunks instead of using the `preview.snippet` field.
- The `text` prop is kept as an optional static fallback for backward compat and tests.
- `PreviewPane` passes `docId={preview.document_id}` for all text-based MIME dispatches.

Impact:
- New text-based renderers should follow the same `docId`-driven fetch pattern.
- Do not pass `text={preview.snippet}` to `TextPreview` from `PreviewPane` — that bypasses the full-text API.

Next action:
- When #443 adds a fidelity mode switcher, thread `translationVersionId` and `showOriginal` through PreviewPane → TextPreview.

## 2026-05-21 — Document viewer branching strategy

Status: Active
Source: docs/design/document-viewer-implementation-guardrails.md, issue #441

Decision:
- #440 targets `main` directly (security fix).
- #441–#451 target `feature/document-viewer` integration branch.
- #446 (Office conversion) should use a sub-branch `feature/document-viewer/office-conversion`.
- Git does not allow a branch named `feature/document-viewer/X` while `feature/document-viewer` also exists — use flat names like `feat/442-pdfjs-viewer` instead.

Impact:
- All document-viewer PRs must target `feature/document-viewer`, not `main`.
- Sub-branch naming: prefer `feat/<issue>-<short-name>` over path-style names.

Next action:
- Keep enforcing until the feature branch merges to `main`.

## 2026-05-20 — Repo memory is the durable record

Status: Active
Source: project manager chat summary

Decision:
- Store durable project memory in `docs/memory/*.md`.
- Use optional indexing only as a retrieval helper.
- Keep important decisions visible in normal code review.

Impact:
- Claude, OpenCode, and Codex should read relevant memory before substantial work.
- New durable decisions should be added here in compact form.

Next action:
- Keep this file short and update stale entries when decisions change.
