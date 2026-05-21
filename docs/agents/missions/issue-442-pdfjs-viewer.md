# Claude Mission: Issue #442 — PDF.js Viewer for PDF Documents

## Mission

You are working on the Tomorrowland repo: `katzimoto/Tomorrowland`.

Implement GitHub issue #442:

**PDF.js viewer for PDF documents**

This is the third MVP step for the high-fidelity document viewer track.

- Parent issue: #453
- Direct issue: #442
- Depends on: #441
- Integration branch: `feature/document-viewer`
- Expected PR target: `feature/document-viewer`

Do not target `main` for this issue.

---

## Critical Prerequisite Check

Before implementation, verify that #441 is actually merged into the branch you will target.

#442 depends on #441 because PDF load failures should be able to fall back to extracted text through the full text API.

Required check:

1. Confirm `feature/document-viewer` exists locally or remotely.
2. Confirm the #441 implementation is present on `feature/document-viewer`:
   - `GET /documents/{document_id}/text`
   - frontend `getDocumentText(...)`
   - updated `TextPreview` full-text behavior
3. If `feature/document-viewer` does not exist or does not include #441, stop and report the blocker. Do not open a #442 implementation PR against `main`.

---

## Branch Setup

Expected flow:

```bash
git fetch origin
git checkout feature/document-viewer
git pull --ff-only
git checkout -b feature/document-viewer/pdfjs-viewer
```

If `feature/document-viewer` does not exist remotely, stop and report this. Do not recreate it from `main` unless the project manager explicitly confirms #441 has been integrated another way.

Open the PR against `feature/document-viewer`, not `main`.

---

## Skills and Plugins You Should Use

Use the Tomorrowland project skills/plugins where they help. Prefer the narrowest useful tool for each step.

### Required Claude skills

Use these skills if available in the runtime:

1. `.claude/skills/tomorrowland-project-context/SKILL.md`
   - Load current Tomorrowland architecture, conventions, and terminology.

2. `.claude/skills/shared-memory/SKILL.md`
   - Load durable project memory before planning.
   - Use memory to understand current state, recent document-viewer decisions, and handoffs.
   - Do not update memory unless this issue creates a durable decision or important handoff.

3. `.claude/skills/safe-implementation/SKILL.md`
   - Keep the change scoped, testable, and compatible with existing viewer behavior.

4. `.claude/skills/frontend-uiux-guardian/SKILL.md`
   - Preserve the current document-page layout, toolbar behavior, and user experience while adding PDF rendering.

5. `.claude/skills/bug-debugging-playbook/SKILL.md`
   - Use only if tests fail, PDF.js worker setup breaks, or Vite bundling is unclear.

6. `.claude/skills/agent-handoff/SKILL.md`
   - Use at the end to report changed files, tests, risks, and next steps.

### Optional Claude skills

Use only if needed:

- `.claude/skills/release-pr-review/SKILL.md`
  - Only for final self-review before opening the PR.

Do **not** load unrelated skills.

### Plugins / external tools

You may use:

- GitHub plugin/MCP to read issue #442, parent #453, dependency #441, and open the PR.
- Local shell tools such as `rg`, `sed`, `git diff`, `npm`, and the project test runner.
- Code search for the exact files listed below.

Do **not** use:

- Jira or Confluence plugins.
- Broad web research.
- Cloud services.
- Backend database tools.
- External document-conversion services.

---

## Required Shared Memory

Before planning, use the shared memory skill and read:

- `docs/agents/shared-memory.md`
- `docs/memory/current-state.md`
- `docs/memory/decisions.md`
- `docs/memory/glossary.md`
- `docs/memory/handoffs.md`

Use memory to understand:

- current Tomorrowland architecture
- current document model and frontend viewer assumptions
- recent document-viewer decisions
- branch strategy
- known project constraints
- agent handoff state

Do not rewrite memory unless this mission creates a durable project decision or important handoff.

---

## Required Reading

Read these after shared memory, in this order:

1. `AGENTS.md`
2. `docs/agents/token-efficiency.md`
3. `docs/agents/coding-behavior.md`
4. `docs/design/document-viewer-design.md`
5. `docs/design/document-viewer-implementation-guardrails.md`
6. GitHub issue #442
7. GitHub issue #441 enough to verify the dependency
8. GitHub issue #453 enough to understand parent scope
9. Current frontend files listed under Allowed Source Paths

Do **not** read:

- `spec.md`
- `spec-v4.pdf`
- backend service files unless only checking existing download URL behavior through frontend API usage
- Office conversion files
- unrelated renderers unless an import/test requires it

Use `rg` before opening additional files.

---

## Goal

Add a real PDF viewer using PDF.js so PDF documents render as original pages instead of a 2,000-character extracted-text snippet.

The viewer should load the original PDF bytes from the existing download endpoint and render them in the document viewer area.

---

## Implementation Requirements

### New `PdfViewer` component

Create:

```text
frontend/src/features/documents/renderers/PdfViewer.tsx
```

The component should:

- Use `pdfjs-dist`.
- Load the PDF from `/api/download/{docId}` or the existing frontend helper for that URL.
- Configure the PDF.js worker in a Vite-compatible, air-gapped-compatible way.
- Render PDF pages using PDF.js, not an external iframe viewer.
- Show a loading state while the document loads.
- Show current page number and total page count.
- Support previous/next page navigation.
- Support zoom in/out/reset.
- Enable or prepare the text layer if feasible in this PR.
- Fail gracefully for corrupt/unloadable PDFs.

### PDF.js worker

Use a local/bundled worker configuration. Do not use a CDN.

Preferred direction:

- Import worker URL from `pdfjs-dist` using Vite-compatible syntax, or use the project’s established pattern if one already exists.
- Configure `GlobalWorkerOptions.workerSrc` once, not repeatedly on every render if avoidable.

If PDF.js worker setup is difficult, keep the implementation simple and document the exact approach in the PR.

### `PreviewPane` update

Update PDF dispatch only:

- `application/pdf` should render `PdfViewer` instead of `TextPreview`.
- Non-PDF behavior should remain unchanged.
- If PDF loading fails, show the existing extraction/error fallback with a download button where possible.
- Use #441 full-text API only for fallback behavior; do not reimplement text fetching.

### Toolbar controls

Issue #442 asks for page and zoom controls in `DocumentToolbar` when the active viewer is PDF.

Keep this minimal and do **not** implement the broader #443 view mode switcher.

Acceptable implementation choices:

1. Preferred: keep page/zoom controls inside `PdfViewer` for this PR, then let #443 move/coordinate toolbar-level controls later.
2. If current architecture already supports passing viewer controls into `DocumentToolbar`, wire it minimally without introducing the full mode-switcher design.

Do not build #443 in this PR.

### Accessibility

- Previous/next page buttons must have `aria-label` values.
- Zoom buttons must have `aria-label` values.
- PDF page area should have a meaningful accessible label, such as `aria-label="PDF page N of M"`.
- Keyboard support should include at least previous/next via buttons; arrow/PageUp/PageDown keyboard shortcuts are desirable but not worth a large architectural change.

---

## Scope Limits

Allowed source paths:

- `frontend/src/features/documents/PreviewPane.tsx`
- `frontend/src/features/documents/DocumentToolbar.tsx`
- `frontend/src/features/documents/DocumentToolbar.module.css`
- `frontend/src/features/documents/renderers/PdfViewer.tsx`
- `frontend/src/features/documents/renderers/PdfViewer.test.tsx`
- `frontend/src/features/documents/renderers/renderers.module.css`
- `frontend/src/api/documents.ts`
- `frontend/package.json`
- `frontend/package-lock.json` or lockfile equivalent, only if dependency changes require it

Allowed test paths:

- `frontend/src/features/documents/renderers/PdfViewer.test.tsx`
- `frontend/src/features/documents/PreviewPane.test.tsx`
- existing frontend test setup files only if needed for PDF.js mocking

Do not edit:

- backend code
- `InsightPane.tsx`
- Office conversion code
- non-PDF renderers except for import/type compatibility if strictly needed
- `spec.md`
- `spec-v4.pdf`

---

## Test Requirements

Add or update focused frontend tests.

### `PdfViewer.test.tsx`

Cover:

- loading state appears initially
- PDF.js document load is called with the correct URL
- page count is displayed after load
- previous/next buttons update the page number
- zoom in/out/reset controls update scale or rendered viewport
- load failure shows a graceful error/fallback state
- buttons have accessible labels

Mock PDF.js rather than loading a real PDF in unit tests.

### `PreviewPane.test.tsx`

Cover:

- `application/pdf` dispatches to `PdfViewer`
- PDF previews no longer dispatch to `TextPreview`
- non-PDF dispatch behavior remains unchanged for at least one representative text MIME type

### Commands

Run the narrowest relevant frontend tests.

At minimum:

- focused `PdfViewer` test
- focused `PreviewPane` dispatch test if changed/added
- frontend typecheck if `pdfjs-dist` types or frontend API types changed

Do not run backend tests for this task unless you accidentally touched backend files, which should not happen.

---

## Best Practices

- Keep the PR frontend-only.
- Keep the diff small and reviewable.
- Do not implement the full #443 mode switcher.
- Do not implement Office conversion.
- Do not use CDN assets.
- Do not add a large UI library for PDF viewing.
- Prefer direct PDF.js integration over embedding Mozilla’s full viewer.
- Avoid broad refactors of `DocumentPage` or `DocumentToolbar`.
- Preserve existing download behavior.
- Preserve existing translation controls.
- Document any PDF.js worker limitations clearly in the PR.

---

## Acceptance Checklist

Before opening the PR, confirm:

- [ ] #441 is present on the target branch.
- [ ] `PdfViewer.tsx` exists.
- [ ] `application/pdf` dispatches to `PdfViewer`.
- [ ] PDF bytes are loaded from the existing download URL.
- [ ] PDF.js worker is configured without CDN usage.
- [ ] Loading state exists.
- [ ] Page count/current page is visible.
- [ ] Previous/next page controls exist.
- [ ] Zoom controls exist.
- [ ] PDF load failure has a graceful fallback/error state.
- [ ] Focused frontend tests pass.
- [ ] No backend files changed.
- [ ] PR targets `feature/document-viewer`.

---

## Pull Request Requirements

Open a PR targeting `feature/document-viewer`.

PR title suggestion:

```text
feat: add PDF.js document viewer
```

PR body must include:

```markdown
## Summary

- Added a PDF.js-based `PdfViewer` for PDF documents.
- Updated PDF MIME dispatch to render original PDF pages instead of extracted snippet text.
- Added page navigation, zoom controls, loading state, and graceful load failure handling.

## Compatibility

- Backend routes are unchanged.
- Existing `/api/download/{docId}` behavior is reused.
- Broader view-mode switching remains for #443.

## Tests

- <exact frontend commands run>

Fixes #442
Part of #453
```

---

## Final Response Format

When done, report:

1. Branch name.
2. PR link.
3. Files changed.
4. PDF.js worker configuration summary.
5. PDF viewer behavior summary.
6. Exact tests run and result.
7. Any follow-up needed.

If you cannot complete the implementation, stop and report the exact blocker with the smallest useful next step.
