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
