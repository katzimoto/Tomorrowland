# Claude Mission: Issue #441 — Full Document Text API

## Mission

You are working on the Tomorrowland repo: `katzimoto/Tomorrowland`.

Implement GitHub issue #441:

**Full document text API endpoint (remove 2,000-character snippet limit)**

This is the second MVP step for the high-fidelity document viewer track.

- Parent issue: #453
- Direct issue: #441
- Integration branch: `feature/document-viewer`
- Expected PR target: `feature/document-viewer`

Do not target `main` for this issue.

---

## Branch Setup

Before implementation:

1. Ensure local `main` is up to date.
2. Create `feature/document-viewer` from latest `main` if it does not already exist.
3. Create your implementation branch from `feature/document-viewer`, for example:

```bash
git checkout main
git pull
git checkout -b feature/document-viewer
git checkout -b feature/document-viewer/full-text-api
```

If `feature/document-viewer` already exists remotely, fetch and branch from it instead.

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
   - Use memory to understand current state, decisions, glossary, and handoffs.
   - Do not update memory unless this issue creates a durable decision or important handoff.

3. `.claude/skills/safe-implementation/SKILL.md`
   - Keep the change scoped, testable, and compatible with existing APIs.

4. `.claude/skills/bug-debugging-playbook/SKILL.md`
   - Use only if tests fail or the API behavior is unclear.

5. `.claude/skills/agent-handoff/SKILL.md`
   - Use at the end to report changed files, tests, risks, and next steps.

### Optional Claude skills

Use only if needed:

- `.claude/skills/search-indexing-design/SKILL.md`
  - Only if text-resolution behavior touches indexing/search assumptions. This mission should not modify indexing.

Do **not** load unrelated skills.

### Plugins / external tools

You may use:

- GitHub plugin/MCP to read issue #441, parent #453, comments, and open the PR.
- Local shell tools such as `rg`, `sed`, `git diff`, `pytest`, `npm`, and the project test runner.
- Code search for the exact files listed below.

Do **not** use:

- Jira or Confluence plugins.
- Broad web research.
- Cloud services.
- External document-conversion tools.

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
- current document model and pipeline assumptions
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
6. GitHub issue #441
7. GitHub issue #453 only enough to understand parent scope
8. Current backend route and preview service files listed under Allowed Source Paths
9. Current frontend API/client and text preview files listed under Allowed Source Paths

Do **not** read:

- `spec.md`
- `spec-v4.pdf`
- Office conversion code or Docker files
- unrelated renderers unless a test/import requires it

Use `rg` before opening additional files.

---

## Goal

Add a streaming-friendly full text endpoint so the document viewer can render full extracted or translated document text without relying on the existing 2,000-character `/preview` snippet.

The new endpoint must be additive and backward-compatible.

Do **not** change the existing `/preview` behavior.

---

## Backend Requirements

Add a new route:

```http
GET /documents/{document_id}/text
```

Query params:

- `translation_version_id`: optional UUID
- `show_original`: boolean, default `false`
- `offset`: integer >= 0, default `0`
- `limit`: integer from `1` to `100000`, default `10000`

Response shape:

```json
{
  "text": "...",
  "total_length": 12345,
  "offset": 0,
  "limit": 10000,
  "truncated": true
}
```

### Text resolution rules

Use the same text-resolution priority as the existing preview/translation service:

1. If `show_original=true`, return `document_payloads.content_text` from the original extracted payload.
2. If `translation_version_id` is provided and valid/available, return that translation text.
3. Else return the latest/default available translation, if applicable.
4. Else return legacy/extracted payload text.
5. Else return an empty string.

Important:

- Missing text is not an error.
- If no text exists, return:

```json
{
  "text": "",
  "total_length": 0,
  "offset": 0,
  "limit": <requested limit>,
  "truncated": false
}
```

### Access control

The new route must enforce the same access/permission behavior as existing document preview/download routes.

Return 404 or the project-standard not-found response if the document does not exist or is not accessible.

### Pagination behavior

- Slice by character offset and limit.
- `total_length` is the full resolved text length before slicing.
- `truncated=true` when `offset + limit < total_length`.
- If `offset` is beyond the end of text, return empty `text`, preserve `total_length`, and set `truncated=false`.
- Validate or clamp invalid `offset`/`limit` using the project’s existing API validation style.

### Non-goals

Do not:

- change `/preview`
- change document extraction
- change indexing
- change translation generation
- change document schema
- add conversion/preview worker code

---

## Frontend Requirements

Add a frontend API client function, likely in `frontend/src/api/documents.ts`:

```ts
getDocumentText(docId, options)
```

Options should include:

- `translationVersionId`
- `showOriginal`
- `offset`
- `limit`

Return type should match the backend response.

Update `TextPreview` so plain text, Markdown, and RTF can fetch full text instead of relying only on the 2,000-character snippet.

Expected behavior:

- Fetch initial 10,000 characters.
- Show loading state while fetching.
- Show a "Load more" action when `truncated=true`.
- Append or extend loaded text when loading more.
- Preserve existing text display styling as much as possible.
- Keep compatibility with existing call sites.

If changing `PreviewPane` is required to pass document ID / version / mode props into `TextPreview`, keep the change minimal and limited to this requirement.

---

## Allowed Source Paths

Backend:

- `src/services/api/routers/documents.py`
- `src/services/preview/service.py`
- `src/services/documents/repository.py`

Frontend:

- `frontend/src/api/documents.ts`
- `frontend/src/features/documents/renderers/TextPreview.tsx`
- `frontend/src/features/documents/renderers/TextPreview.test.tsx`
- `frontend/src/features/documents/PreviewPane.tsx`

Tests:

- `tests/unit/test_documents.py`
- `tests/unit/test_document_text_api.py` if creating a focused test file is cleaner
- `tests/integration/test_documents.py`
- relevant frontend component test file(s)

Do not edit outside these paths unless you first prove it is required with `rg` and explain it in the PR.

---

## Test Requirements

### Backend tests

Add or update tests for:

- offset/limit slicing returns the correct substring
- `show_original=true` returns extracted original text even when translation exists
- missing or inaccessible document returns the same project-standard not-found behavior as preview/download
- document with no extracted/translated text returns empty text response, not error
- `limit` validation respects the maximum of 100,000
- `offset` beyond text length returns empty text and `truncated=false`

### Frontend tests

Add or update tests for:

- `getDocumentText` builds the correct API request
- `TextPreview` renders text returned from the full text API rather than only the snippet
- loading state appears while fetching
- "Load more" appears when `truncated=true`
- loading more appends/extends text correctly

### Commands

Run the narrowest relevant backend and frontend tests.

At minimum, run:

- the focused backend test(s) you added/updated
- the focused frontend component/API test(s) you added/updated
- frontend typecheck if frontend types changed

Do not run unrelated full suites unless necessary.

---

## Best Practices

- Keep `/preview` backward-compatible.
- Prefer additive API changes.
- Reuse existing preview service/repository logic instead of duplicating text-resolution rules.
- Keep frontend API naming consistent with existing `documents.ts` conventions.
- Keep the PR small enough to review.
- Do not implement #442, #443, #447, or #449 in this PR.
- Do not add new dependencies unless absolutely necessary.
- Prefer explicit tests over snapshots.
- Document any unavoidable follow-up clearly.

---

## Acceptance Checklist

Before opening the PR, confirm:

- [ ] `GET /documents/{document_id}/text` exists.
- [ ] Endpoint supports `translation_version_id`, `show_original`, `offset`, and `limit`.
- [ ] Endpoint returns `text`, `total_length`, `offset`, `limit`, and `truncated`.
- [ ] `/preview` behavior is unchanged.
- [ ] Access control matches existing document preview/download behavior.
- [ ] Frontend has a typed `getDocumentText` API function.
- [ ] `TextPreview` can load full text in chunks.
- [ ] Focused backend tests pass.
- [ ] Focused frontend tests pass.
- [ ] No unrelated files changed.

---

## Pull Request Requirements

Open a PR targeting `feature/document-viewer`.

PR title suggestion:

```text
feat: add full document text API
```

PR body must include:

```markdown
## Summary

- Added `GET /documents/{document_id}/text` for full extracted/translated text pagination.
- Added frontend `getDocumentText` client support.
- Updated `TextPreview` to load full text chunks instead of relying only on the preview snippet.

## Compatibility

- Existing `/preview` behavior is unchanged.
- Existing snippet consumers remain compatible.

## Tests

- <exact backend commands run>
- <exact frontend commands run>

Fixes #441
Part of #453
```

---

## Final Response Format

When done, report:

1. Branch name.
2. PR link.
3. Files changed.
4. API behavior summary.
5. Exact tests run and result.
6. Any follow-up needed.

If you cannot complete the implementation, stop and report the exact blocker with the smallest useful next step.
