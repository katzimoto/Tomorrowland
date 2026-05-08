# Frontend UI Implementation Plan

## Goal

Build the user-facing Neverland interface described in
`docs/design/user-ui-spec.md` as reviewable frontend phases. The UI should feel
native on first use: search-first, fast, dense-but-clear, accessible, and
grounded in source documents.

## Source Specs

- `docs/design/user-ui-spec.md`
- `docs/design/document-comments-spec.md`
- `docs/design/translation-versions-spec.md`
- `docs/logical-spec.md`
- `docs/implementation/phase-03e-search-apis.md`
- `docs/implementation/phase-05-preview-enrichment.md`
- `docs/implementation/translation-versions-plan.md`
- `docs/implementation/document-comments-plan.md`
- `docs/implementation/phase-07-rag-ui-features.md`

## Chosen Stack

Use this stack for the first production UI implementation. Do not introduce a
parallel routing, styling, or state framework without updating this plan first.

- React + TypeScript.
- Vite for local development and build.
- TanStack Query for API state, caching, loading states, and retries.
- TanStack Router for typed route-level navigation and URL search params.
- React Hook Form plus Zod for forms and request validation.
- Lucide icons for icon buttons and navigation.
- CSS modules backed by global `tokens.css`, `base.css`, and `utilities.css`.
  Avoid Tailwind, CSS-in-JS, and heavy component frameworks for the MVP.
- Vitest and Testing Library for unit/component tests.
- Playwright for browser workflow, responsive layout, and screenshot checks.
- axe-based accessibility checks through Playwright or Testing Library.

Design principle: build a small Neverland design system first, then compose
pages from it. Do not style each page independently.

## Frontend File Layout

Expected root after UI scaffold:

```text
frontend/
|-- package.json
|-- index.html
|-- vite.config.ts
|-- tsconfig.json
|-- playwright.config.ts
|-- src/
|   |-- app/
|   |   |-- App.tsx
|   |   |-- routes.tsx
|   |   `-- providers.tsx
|   |-- api/
|   |   |-- client.ts
|   |   |-- auth.ts
|   |   |-- search.ts
|   |   |-- documents.ts
|   |   |-- qa.ts
|   |   `-- generated-or-shared-types.ts
|   |-- components/
|   |   |-- primitives/
|   |   |-- layout/
|   |   |-- feedback/
|   |   `-- data-display/
|   |-- features/
|   |   |-- auth/
|   |   |-- search/
|   |   |-- documents/
|   |   |-- qa/
|   |   |-- annotations/
|   |   |-- subscriptions/
|   |   |-- notifications/
|   |   `-- history/
|   |-- styles/
|   |   |-- tokens.css
|   |   |-- base.css
|   |   `-- utilities.css
|   `-- test/
|       |-- fixtures/
|       `-- render.tsx
`-- tests/
    `-- e2e/
```

## API Availability Map

Classify API usage before each UI phase starts.

| Surface | Backend State | UI Behavior |
|---|---|---|
| Auth login/me/logout | Available from Phase 02 | Use real API |
| Search | Available from Phase 03e | Use real API |
| Preview metadata/basic preview | Phase 03e, expanded in Phase 05 | Use real API and feature-detect preview mode fields |
| Download | Available from Phase 03e | Use real API |
| Translation versions/manual request | Phase 05c | Use selector when versions exist; hide request when disabled |
| Q&A | Phase 07 | Use adapter with disabled state before backend exists |
| Annotations | Phase 07 | Use adapter with disabled state before backend exists |
| Document comments | Phase 07a | Hide comments tab or show disabled state before API exists |
| Saved searches | No backend in current phases | Store locally by user ID in browser storage for MVP |
| Subscriptions | Phase 07 | Use adapter with disabled state before backend exists |
| Notifications | Phase 07 | Use adapter with empty state before backend exists |
| History | Phase 07 or later | Use adapter with empty state before backend exists |
| Expertise map | Phase 07 or later | Defer from MVP |
| Admin | Phase 04 and separate admin UI spec | Link only in user shell |

Do not use ad hoc mocks inside production UI code. If a backend endpoint is not
available, hide the feature, show a disabled state, or use a development-only
fixture adapter behind an explicit flag.

## Auth UX Contract

Authentication is part of the UI foundation, not a page-specific concern.

- `/login` is the only public app route in the MVP.
- Protected routes wait for `/auth/me` before rendering navigation or document
  data.
- While the current user is loading, show a centered app loading state or shell
  skeleton with no protected content.
- Store the bearer token behind a small auth storage boundary using
  `sessionStorage` for the MVP. Do not read or write storage directly from
  feature components.
- Attach `Authorization: Bearer <token>` through the API client only.
- On login success, route to the requested return URL when safe, otherwise
  `/search`.
- On invalid credentials, show: `Email or password is incorrect.`
- On any authenticated API `401`, clear the token and route to
  `/login?expired=1` with copy: `Your session expired. Sign in again.`
- Logout calls `/auth/logout` when available, clears local auth state even if
  the request fails, and returns to `/login`.
- `403` responses render a permission state without leaking source names,
  hidden counts, or document titles.
- Admin navigation is visible only when the current user payload marks the user
  as an admin.

## UI Phase 00: Scaffold And Design System

Branch: `developer/ui-00-frontend-foundation`

### Scope

- Add `frontend/` project scaffold.
- Add routing, app providers, API client shell, and auth token storage boundary.
- Add design tokens from `docs/design/user-ui-spec.md`.
- Add primitive components:
  - Button.
  - IconButton with tooltip.
  - TextInput and SearchInput.
  - Select/Menu.
  - Checkbox/Switch.
  - Tabs.
  - Badge/Chip.
  - Dialog/Drawer.
  - EmptyState.
  - Skeleton.
  - Toast.
  - AppShell and NavRail.
- Add responsive layout utilities.
- Add test setup: Vitest, Testing Library, Playwright, axe checks.

### Validation

- Unit tests for primitive interaction states.
- Accessibility tests for app shell, buttons, inputs, tabs, dialogs.
- Playwright screenshots at 320 x 720, 768 x 1024, 1024 x 768, and
  1440 x 900.
- `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`.

### Acceptance Criteria

- App shell renders with no backend dependency.
- Navigation is keyboard accessible.
- Tokens are centralized and documented in CSS.
- No page-specific styling is needed for primitive components.
- Mobile layout has no overlap at 320 px width.

Stop for Reviewer-agent review.

## UI Phase 01: Auth And Search Workspace

Branch: `developer/ui-01-search-workspace`

### Scope

- Login flow using real auth endpoints.
- Authenticated app shell with current-user state.
- Session-expired, logout, and forbidden states from the Auth UX Contract.
- Search page route.
- Search input with clear action, submit, recent-search placeholder state.
- Hybrid search results against Phase 03e search endpoint.
- Result rows with title, snippet/chunk text, source/type metadata, tags, score,
  translation state, and result actions.
- Filter panel with UI state for source, file type, date, tags, language, and
  translation. Only send filters that backend supports; keep unsupported filters
  disabled or local-only until API support lands.
- Loading, empty, error, and no-access-safe states.
- Saved search UI using local browser persistence scoped to current user ID.

### Validation

- Component tests for SearchInput, filters, result rows, empty/error states.
- API client tests for auth and search request/response parsing.
- Playwright workflow: login, search, view results, clear query, use filters,
  logout, and expired-session redirect.
- Screenshot checks at 320 x 720, 768 x 1024, 1024 x 768, and 1440 x 900.
- Accessibility: result count announcement and focus preservation after filters.

### Acceptance Criteria

- First screen after login is search.
- Search state is reflected in URL query params.
- Protected routes never flash private content before `/auth/me` resolves.
- Permission-filtered zero results do not reveal hidden source names or counts.
- Loading states reserve stable row heights.
- Search is usable with keyboard only.

Stop for Reviewer-agent review.

## UI Phase 02: Document Preview

Branch: `developer/ui-02-document-preview`

### Scope

- Document route `/doc/:doc_id`.
- Back-to-search behavior preserving query and filters.
- Preview shell with toolbar, main preview pane, and right insight pane.
- Translation version selector and request translation dialog when endpoints
  exist.
- Preview renderers for available backend modes:
  - text.
  - html.
  - table.
  - slides.
  - image.
  - archive.
  - email.
- Fallback states:
  - unsupported preview.
  - extraction failed.
  - file missing.
  - loading timeout.
  - translation unavailable.
- Download action.
- Request translation action when endpoint exists.
- Version switching without leaving the document route.
- Trust/provenance display in toolbar and details tab.

### Validation

- Fixture component tests for each preview mode.
- Component tests for translation version selector, pending/failed states, and
  request dialog.
- Permission error test for inaccessible document.
- Playwright workflow: search result opens preview, back returns to search state,
  download/request translation controls render correctly, and version selection
  preserves document context.
- Screenshot checks for preview at desktop and mobile.
- Accessibility checks for tabs, toolbar buttons, and preview landmarks.

### Acceptance Criteria

- Preview never blocks document metadata from rendering.
- Unsupported or failed previews still offer available safe actions.
- Document title, source, translation state, and indexed date are visible.
- Selected translation version is visible and does not replace the preview while
  a new request is pending.
- Text and controls do not overlap at mobile sizes.

Stop for Reviewer-agent review.

## UI Phase 03: Q&A With Citations

Branch: `developer/ui-03-qa-citations`

### Scope

- `/qa` route.
- Embedded Q&A panel on document preview.
- Question input with scope controls.
- Answer panel with required citations.
- Citation cards linking to document previews.
- No-context, model-unavailable, loading, and partial-failure states.
- Grounding language: answers are based only on accessible documents.

### Validation

- Component tests for answer states and citation rendering.
- API client tests for Q&A response parsing.
- Playwright workflow: ask question, inspect citations, open cited document.
- Permission test: inaccessible citation data is never rendered.
- Accessibility: citations are meaningful links and answer updates are announced.

### Acceptance Criteria

- Q&A answers never render without citations unless the response is explicitly
  a no-context answer.
- Scope controls are visible and understandable.
- Citation navigation preserves return path to Q&A.

Stop for Reviewer-agent review.

## UI Phase 04: Document Comments And Annotations

Branch: `developer/ui-04-comments-annotations`

### Scope

- Shared document comment list in document insight pane.
- Comment composer with long text, line breaks, and emoji support.
- Create, edit, delete comment flows.
- Creator/admin action visibility for comments.
- Annotation list in document insight pane.
- Text/region selection affordance per preview mode.
- Create, edit, delete annotation flows.
- Private/shared toggle.
- Inline markers or side markers where the preview mode supports it.
- Privacy labels from the design spec.

### Validation

- Component tests for comment composer, long comment collapse/expand, emoji-only
  comments, edit/delete states, and admin affordances.
- Component tests for annotation editor, list item, privacy labels.
- Preview-mode tests for supported position shapes.
- Playwright workflow: create comment, edit own comment, delete own comment,
  create private note, create shared note, edit, delete.
- Permission tests for own comment, other-user comment, admin comment behavior,
  own annotation, and shared annotation behavior.

### Acceptance Criteria

- Comments are visible to all users with document access and hidden from users
  without document access.
- Comment creators and admins can edit/delete; other users cannot.
- Long comments do not take over the preview pane.
- Private annotations are clearly labeled.
- Shared annotations do not appear for users without document access.
- Comment and annotation actions are keyboard accessible.

Stop for Reviewer-agent review.

## UI Phase 05: Subscriptions, Notifications, And History

Branch: `developer/ui-05-alerts-history`

### Scope

- Subscriptions list and create/edit form.
- Saved search to subscription conversion flow.
- Notification center with unread/read state.
- History page with recently viewed documents, searches, Q&A, and annotations.
- Privacy help menu for history/audit-sensitive behavior.

### Validation

- Component tests for subscription form, notification item, history rows.
- Playwright workflow: create subscription, read notification, open document.
- Empty-state tests for no subscriptions, no notifications, and no history.
- Accessibility checks for lists, switches, dialogs, and notification actions.

### Acceptance Criteria

- Saved searches and subscriptions remain visually distinct.
- Notification unread count is visible in the shell.
- History states explain privacy without cluttering the page.

Stop for Reviewer-agent review.

## UI Phase 06: Expertise Map And Power-User Polish

Branch: `developer/ui-06-expertise-polish`

### Scope

- Expertise map route.
- Neutral result language and evidence display.
- Command menu.
- Optional side-peek preview from search results.
- Personalized recent-topic suggestions if backend supports them.
- Final visual polish pass.

### Validation

- Component tests for expertise result reasoning.
- Playwright workflow for command menu and expertise search.
- Screenshot regression sweep for all major routes.
- Accessibility regression sweep.

### Acceptance Criteria

- Expertise map does not look like a leaderboard.
- Command menu does not replace visible navigation.
- All major routes pass responsive screenshot checks.

Stop for Reviewer-agent review.

## Cross-Phase Design System Rules

- Use lucide icons for actions where available.
- Prefer icon buttons for common commands: download, clear, close, copy, mark
  read, request translation.
- Every icon-only button has a tooltip and accessible name.
- Cards are only for repeated result items, dialogs, and genuinely framed tools.
- Do not nest cards inside cards.
- Avoid decorative orbs, bokeh, gradients, or marketing composition.
- Text must not overlap at 320 px, 768 px, 1024 px, or 1440 px widths.
- Loading states preserve final layout dimensions.
- Empty states include a next action when one is available.
- Permission filtering never reveals inaccessible document names, source names,
  or counts.

## Review Artifacts Per UI PR

Each frontend PR should include:

- Screenshots or Playwright trace links for changed routes at 320 x 720,
  768 x 1024, 1024 x 768, and 1440 x 900.
- Keyboard navigation notes.
- Accessibility check results.
- Viewport validation notes covering clipping, overlap, horizontal scroll, focus
  visibility, and whether the primary action remains reachable.
- Visual regression results. Once screenshot baselines exist, unexpected pixel
  diffs above 0.5% require reviewer sign-off.
- API contract notes listing real, disabled, or fixture-backed endpoints.
- Auth/session behavior notes when protected routes, API client code, or shell
  navigation changes.
- Updated docs when UI behavior changes from this plan.

## Global Validation Commands

Expected frontend commands after UI Phase 00:

```bash
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

Expected repository commands:

```bash
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev mypy src --strict
uv run --extra dev pytest
docker compose config
```

## Do Not Start Criteria

Do not begin a UI phase if:

- Required backend endpoints are ambiguous and no disabled-state plan exists.
- The previous UI phase has unresolved Reviewer blockers.
- The route would require revealing inaccessible document metadata.
- The feature depends on a backend phase that has not defined a stable response
  contract.
