# Phase 08d: Document Detail And Q&A

## Prerequisite

Phase 08c review gate passed. The `/doc/:documant_id` stub route must exist in
`src/app/routes.tsx` (committed by the 08c agent) before this phase begins.

## Branch

`developer/phase-08d-document-detail`

## Stack

React 19 + TypeScript + Vite + TanStack Router + TanStack Query + React Hook
Form + Zod + CSS modules. See `docs/implementation/phase-08b-frontend-ui.md` Chosen
Stack section for constraints. Do not introduce additional frameworks.

## API Availability

All endpoints required by this phase are available from the backend. No mock
adapters are needed. See `docs/implementation/phase-08b-frontend-ui.md` API
Availability Map for the full table.

Endpoints used in this phase:
- `GET /preview/{documant_id}` (with optional `?translation_version_id=`)
- `GET /download/{documant_id}`
- `GET /documents/{documant_id}/translation-versions`
- `POST /documents/{documant_id}/translate`
- `GET /documents/{documant_id}/summary`
- `GET /documents/{documant_id}/entities`
- `GET /documents/{documant_id}/tags`
- `GET /documents/{documant_id}/related`
- `POST /qa`

## Auth UX Contract

Follow the Auth UX Contract in `docs/implementation/phase-08b-frontend-ui.md`
precisely. `403` responses render a permission state without leaking source
names, hidden counts, or document titles.

## Shared Interface Contract (First Commit)

Before implementing any feature content, commit `insightPaneTabs.ts` so the
08e agent can begin in parallel:

```typescript
// frontend/src/features/documents/insightPaneTabs.ts
export type InsightPaneTab =
  | "summary"       // owned by this phase (08d)
  | "qa"            // owned by this phase (08d)
  | "related"       // owned by this phase (08d)
  | "comments"      // owned by phase 08e
  | "annotations"   // owned by phase 08e
  | "subscriptions"; // owned by phase 08e
```

`InsightPane.tsx` renders the `Tabs` primitive with one tab per value. Tabs
owned by 08e are rendered as stubs (empty panel or `Skeleton`) until the 08e
branch is merged. Do not leave them as broken imports.

## Scope — UI Phase 02: Document Preview

Replace the `/doc/:documant_id` stub route in `src/app/routes.tsx` with the real
`DocumentPage` component.

Create `src/features/documents/` with:

- `insightPaneTabs.ts` — shared tab type contract (first commit; see above).
- `DocumentPage.tsx` — top-level route component. Reads `documant_id` from route
  params. Fetches preview and document metadata.
- `DocumentPage.module.css`
- `DocumentPage.test.tsx` — includes permission-error test for inaccessible
  document (no title, source label, or snippet rendered).
- `DocumentToolbar.tsx` — title, back-to-search button (preserves query and
  filter state via TanStack Router history), download action, request
  translation action, trust/provenance display.
- `DocumentToolbar.module.css`
- `DocumentToolbar.test.tsx`
- `PreviewPane.tsx` — dispatches to preview mode renderers based on the
  `preview_mode` field returned by `GET /preview/{documant_id}`.
- `PreviewPane.module.css`
- `InsightPane.tsx` — right panel with `Tabs`. Renders tabs for `summary`,
  `qa`, `related`, `comments` (stub), `annotations` (stub),
  `subscriptions` (stub).
- `InsightPane.module.css`
- `TrustDisplay.tsx` — source label, indexed date, translation state. Appears
  in toolbar and in a Details tab within the insight pane.
- `TrustDisplay.test.tsx`
- `TranslationVersionSelector.tsx` — dropdown in toolbar listing versions from
  `GET /documents/{documant_id}/translation-versions`. Selecting an available
  version calls `GET /preview/{documant_id}?translation_version_id=...`. Pending
  and failed versions are labelled and not selectable as preview content.
- `TranslationVersionSelector.test.tsx`
- `RequestTranslationDialog.tsx` — dialog triggered from toolbar. Submits
  `POST /documents/{documant_id}/translate`. Shows pending state after submission.
- `RequestTranslationDialog.test.tsx`

Preview mode renderers in `src/features/documents/renderers/`:

- `TextPreview.tsx` — pre-formatted text content with wrapping.
- `TextPreview.test.tsx` — fixture test.
- `HtmlPreview.tsx` — sanitized HTML rendered in an iframe or with
  DOMPurify. Never render unsanitized HTML.
- `HtmlPreview.test.tsx`
- `TablePreview.tsx` — scrollable table from structured preview data.
- `TablePreview.test.tsx`
- `SlidesPreview.tsx` — slide-by-slide navigation for presentation content.
- `ImagePreview.tsx` — single image with zoom controls.
- `ArchivePreview.tsx` — filename listing for archive members.
- `ArchivePreview.test.tsx`
- `EmailPreview.tsx` — from/to/subject header + body for email content.
- Fallback renderers (no test needed beyond presence check):
  - `UnsupportedPreview.tsx` — "Preview not available for this file type" +
    download action if available.
  - `ExtractionFailedPreview.tsx` — "Text extraction failed" + download action.
  - `FileMissingPreview.tsx` — "File not found".
  - `LoadingTimeoutPreview.tsx` — "Preview is taking longer than expected" +
    retry action.

Intelligence display in the insight pane summary tab:

- Query `GET /documents/{documant_id}/summary`, `/entities`, `/tags` via TanStack
  Query. These are best-effort; render gracefully when data is absent.
- Display summary text, entity list (grouped by type), and tag chips.

Related documents in the insight pane related tab:

- Query `GET /documents/{documant_id}/related`. Render as a compact result list
  (title + source label). Empty state if no related documents.

Create `src/api/documents.ts`:
- `getPreview(docId, translationVersionId?)` — `GET /preview/{documant_id}`
- `getTranslationVersions(docId)` — `GET /documents/{documant_id}/translation-versions`
- `requestTranslation(docId)` — `POST /documents/{documant_id}/translate`
- `downloadDocument(docId)` — `GET /download/{documant_id}` triggering browser file save
- `getDocumentSummary(docId)` — `GET /documents/{documant_id}/summary`
- `getDocumentEntities(docId)` — `GET /documents/{documant_id}/entities`
- `getDocumentTags(docId)` — `GET /documents/{documant_id}/tags`
- `getRelatedDocuments(docId)` — `GET /documents/{documant_id}/related`

## Scope — UI Phase 03: Q&A With Citations

Replace the `/qa` stub route in `src/app/routes.tsx` with the real `QAPage`
component.

Create `src/features/qa/` with:

- `QAPage.tsx` — standalone `/qa` route. Contains `QuestionInput` and
  `AnswerPanel`. Allows selecting scope (all accessible documents or a specific
  source).
- `QAPage.module.css`
- `QAPage.test.tsx`
- `QAPanel.tsx` — embeddable panel used in `InsightPane.tsx` `qa` tab. Scoped
  to the current document's source by default.
- `QAPanel.module.css`
- `QAPanel.test.tsx`
- `QuestionInput.tsx` — textarea with scope controls and submit action.
- `QuestionInput.test.tsx`
- `AnswerPanel.tsx` — renders answer text followed by `CitationList`.
- `AnswerPanel.test.tsx`
- `CitationList.tsx` — list of `CitationCard` items.
- `CitationCard.tsx` — document title, chunk excerpt, relevance score, link to
  `/doc/:documant_id`. Citation navigation passes a `return=/qa` param so back
  behavior is preserved.
- `CitationCard.test.tsx`

States required:
- Loading: spinner or skeleton in answer area.
- No-context: "No relevant documents found for your question."
- Model-unavailable: "Q&A service is currently unavailable." (backend returns
  error when Ollama is unreachable).
- Partial-failure: answer with reduced citation count and a warning label.

Grounding language: include "Based only on documents you have access to." near
the question input or answer header.

Create `src/api/qa.ts`:
- `askQuestion({ question, topK?, sourceFilter? })` — `POST /qa`
- Response type covering `answer`, `citations` (array of `{ documant_id, chunk,
  score, title }`).

## Do Not Start Criteria

Do not begin this phase if:

- Required backend endpoints are ambiguous and no disabled-state plan exists.
- Phase 08c has unresolved Reviewer blockers.
- The route would require revealing inaccessible document metadata.
- The feature depends on a backend phase that has not defined a stable response
  contract.

## New Files

```
frontend/src/features/documents/
  insightPaneTabs.ts
  DocumentPage.tsx + .module.css + .test.tsx
  DocumentToolbar.tsx + .module.css + .test.tsx
  PreviewPane.tsx + .module.css
  InsightPane.tsx + .module.css
  TrustDisplay.tsx + .test.tsx
  TranslationVersionSelector.tsx + .test.tsx
  RequestTranslationDialog.tsx + .test.tsx
  renderers/
    TextPreview.tsx + .test.tsx
    HtmlPreview.tsx + .test.tsx
    TablePreview.tsx + .test.tsx
    SlidesPreview.tsx
    ImagePreview.tsx
    ArchivePreview.tsx + .test.tsx
    EmailPreview.tsx
    UnsupportedPreview.tsx
    ExtractionFailedPreview.tsx
    FileMissingPreview.tsx
    LoadingTimeoutPreview.tsx
frontend/src/features/qa/
  QAPage.tsx + .module.css + .test.tsx
  QAPanel.tsx + .module.css + .test.tsx
  QuestionInput.tsx + .test.tsx
  AnswerPanel.tsx + .test.tsx
  CitationList.tsx
  CitationCard.tsx + .test.tsx
frontend/src/api/documents.ts
frontend/src/api/qa.ts
frontend/tests/e2e/document.spec.ts
frontend/tests/e2e/qa.spec.ts
```

## Modified Files

```
frontend/src/app/routes.tsx   — implement /doc/:documant_id with DocumentPage; implement /qa with QAPage
```

## Validation

```bash
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

Playwright workflows required:

- Clicking a search result opens `/doc/:documant_id`.
- Browser back from document returns to search with query and filter state
  intact.
- Preview renders for at least one text fixture document.
- Unsupported MIME type renders the unsupported fallback.
- Permission error for inaccessible document renders permission state (no
  title, no source label, no snippet).
- Translation version selector lists available versions; selecting one
  re-renders the preview.
- Pending translation version is labelled and not selectable.
- Request translation dialog appears, submits, and shows pending state.
- Download control triggers browser file download.
- Q&A: submit question, receive answer with citation cards.
- Q&A: clicking a citation card navigates to `/doc/:documant_id`.
- Q&A: inaccessible citation data is never rendered.
- All four Playwright viewports: 320×720, 768×1024, 1024×768, 1440×900.

## Review Artifacts

Each PR must include (see `docs/implementation/phase-08b-frontend-ui.md` Review
Artifacts Per UI PR for the full checklist):

- Screenshots or Playwright trace links at all four viewports.
- Keyboard navigation notes.
- Accessibility check results.
- Viewport validation notes covering preview pane and insight pane layout.
- API contract notes.
- Auth/session behavior notes.

## Acceptance Criteria

- Preview never blocks document metadata from rendering.
- Unsupported and failed previews still offer download when the file is
  available.
- Document title, source, translation state, and indexed date are visible.
- Selected translation version is visible and does not replace the preview
  while a new request is pending.
- Q&A answers never render without citations unless the response is explicitly
  a no-context answer.
- Citation navigation preserves return path to `/qa`.
- Text and controls do not overlap at mobile viewport.
- `insightPaneTabs.ts` is committed as the first substantive commit so the 08e
  agent can begin its work in parallel.

Stop for Reviewer-agent review.
