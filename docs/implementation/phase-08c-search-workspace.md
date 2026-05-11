# Phase 08c: Search Workspace

## Prerequisite

Phase 08b review gate passed (React frontend foundation complete and merged).
This phase can start immediately in parallel with Phase 08f.

## Branch

`developer/phase-08c-search-workspace`

## Stack

React 19 + TypeScript + Vite + TanStack Router + TanStack Query + React Hook
Form + Zod + CSS modules. See `docs/implementation/phase-08b-frontend-ui.md` Chosen
Stack section for constraints. Do not introduce additional frameworks.

## API Availability

All endpoints required by this phase are available from the backend. No mock
adapters are needed. See `docs/implementation/phase-08b-frontend-ui.md` API
Availability Map for the full table.

Endpoints used in this phase:
- `POST /auth/login`
- `GET /auth/me`
- `POST /auth/logout`
- `POST /search`

## Auth UX Contract

Follow the Auth UX Contract in `docs/implementation/phase-08b-frontend-ui.md`
precisely. Key rules:

- `/login` is the only public route.
- Protected routes wait for `/auth/me` before rendering navigation or document
  data. Show a centered loading skeleton with no protected content while the
  current user resolves.
- Store the bearer token in `sessionStorage` via the existing `authStorage`
  boundary in `src/api/auth.ts`. Feature components must not read or write
  storage directly.
- On login success, route to the requested return URL when safe, otherwise
  `/search`.
- On invalid credentials: `Email or password is incorrect.`
- On any authenticated `401`: clear token and route to `/login?expired=1` with
  copy `Your session expired. Sign in again.`
- Logout calls `POST /auth/logout`, clears local auth state even if the request
  fails, and returns to `/login`.
- `403` responses render a permission state without leaking source names, hidden
  counts, or document titles.
- Admin navigation is visible only when `user.is_admin` is true.

## Scope

### Auth Shell Wiring

- `AppLayout.tsx` already queries `GET /auth/me` via TanStack Query. Finish the
  wiring so `user.display_name` and `user.is_admin` are consumed: display the
  user's name in the NavRail and pass `is_admin` to the admin link visibility
  guard.
- Add a logout action to the NavRail (icon button or menu item) that calls
  `authStorage.logout()` from `src/api/auth.ts`.
- Ensure the loading skeleton in `AppLayout.tsx` renders before any protected
  content; no flash of private data before `/auth/me` resolves.

### Search Page

Replace the `PlaceholderPage` stub at `/search` in `src/app/routes.tsx` with
the real `SearchPage` component.

Create `src/features/search/` with:

- `SearchPage.tsx` — top-level route component. Reads `q`, `mode`, `page`, and
  filter params from TanStack Router search params. On mount, if `q` is set,
  fires the search query.
- `SearchPage.module.css`
- `FilterPanel.tsx` — collapsible panel with controls for source, file type,
  date range, tags, language, and translation state. Only send filters that the
  backend accepts; keep unsupported filters as local-only UI state. Filters are
  reflected in URL params.
- `FilterPanel.module.css`
- `FilterPanel.test.tsx`
- `ResultList.tsx` — renders a list of `ResultRow` items. Handles loading
  (skeleton rows at stable heights), empty (contextual empty state), and error
  (retry action) states.
- `ResultList.module.css`
- `ResultRow.tsx` — displays: title, snippet/chunk text, source label, MIME
  type badge, tags, translation state badge, relevance score, and a row action
  menu (open document, copy link). Clicking a row navigates to `/doc/:doc_id`.
- `ResultRow.module.css`
- `ResultRow.test.tsx`
- `SavedSearches.ts` — browser-storage utility. Stores and retrieves saved
  searches in `localStorage` scoped to the current user ID
  (`tomorrowland_saved_searches_<user_id>`). No backend; local-only per the API
  Availability Map.
- `SavedSearches.test.ts`
- `SearchPage.test.tsx`

Extend `src/api/search.ts` with:
- Pagination parameters (`page`, `page_size`).
- Filter parameter types matching the backend `POST /search` contract.
- Response type covering `results`, `total`, and `took_ms`.

Pre-define the `/doc/:doc_id` stub route in `src/app/routes.tsx` (render a
`PlaceholderPage` with title "Document") so that `ResultRow` links are valid
and 08d can replace the component without modifying the route registration.

Add `frontend/tests/e2e/search.spec.ts` with the Playwright workflows listed
under Validation.

### States Required

- **Loading**: skeleton rows at stable heights (use `Skeleton` primitive).
- **Empty — no query**: welcome state with search tip.
- **Empty — no results**: "No documents matched your search." without revealing
  whether documents exist at all.
- **Empty — permission filtered**: same copy as no-results; do not expose
  hidden source names or counts.
- **Error**: error message with retry button.

### URL State

Encode query, mode, filters, and page in TanStack Router search params so the
URL is shareable and the browser back button restores state.

## Do Not Start Criteria

Do not begin this phase if:

- Required backend endpoints are ambiguous and no disabled-state plan exists.
- The previous UI phase (08b) has unresolved Reviewer blockers.
- The route would require revealing inaccessible document metadata.
- The feature depends on a backend phase that has not defined a stable response
  contract.

## New Files

```
frontend/src/features/search/
  SearchPage.tsx
  SearchPage.module.css
  SearchPage.test.tsx
  FilterPanel.tsx
  FilterPanel.module.css
  FilterPanel.test.tsx
  ResultList.tsx
  ResultList.module.css
  ResultRow.tsx
  ResultRow.module.css
  ResultRow.test.tsx
  SavedSearches.ts
  SavedSearches.test.ts
frontend/tests/e2e/search.spec.ts
```

## Modified Files

```
frontend/src/app/routes.tsx         — replace searchRoute component; add /doc/:doc_id stub route
frontend/src/app/AppLayout.tsx      — wire user display name and is_admin; add logout action
frontend/src/api/search.ts          — extend types for pagination and filters
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

- Login with valid credentials navigates to `/search`.
- Login with invalid credentials shows `Email or password is incorrect.`
- Session expiry (`401` on `/auth/me`) redirects to `/login?expired=1` with
  the session-expired banner.
- Logout returns to `/login`.
- Typing a query and submitting shows result rows.
- Result row displays title, snippet, source label, MIME type badge,
  translation state, and score.
- Filter panel toggles are reflected in URL params.
- Permission-filtered zero results show the empty state without source names or
  counts.
- Saved search survives a page reload.
- Clicking a result row navigates to `/doc/:doc_id` (stub page is acceptable
  for this phase).
- All four Playwright viewports: 320×720, 768×1024, 1024×768, 1440×900.

## Review Artifacts

Each PR must include (see `docs/implementation/phase-08b-frontend-ui.md` Review
Artifacts Per UI PR for the full checklist):

- Screenshots or Playwright trace links at all four viewports.
- Keyboard navigation notes.
- Accessibility check results.
- Viewport validation notes.
- API contract notes listing which endpoints are real vs disabled.
- Auth/session behavior notes.

## Acceptance Criteria

- First authenticated screen is `/search`.
- Search state (query, filters, page) is reflected in URL search params.
- Protected routes never flash private content before `/auth/me` resolves.
- Permission-filtered zero results do not reveal hidden source names or counts.
- Loading states reserve stable row heights.
- Search is usable with keyboard only: login, search, filter, clear, logout.
- Saved searches persist across page reload.

Stop for Reviewer-agent review before 08d or 08e begin using document routes.
