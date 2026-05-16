# Frontend Context

Use this map for React/Vite UI work, frontend testing, layout, styling, and client-side behavior.

## Main files

- `frontend/` — React 19 / TypeScript / Vite app.
- `frontend/AGENTS.md` — frontend-specific rules. Read it before frontend implementation.
- `frontend/src/` — application source.
- `frontend/tests/` or local frontend test locations, depending on the current structure.

## Common checks

Run from `frontend/` unless the local scripts say otherwise:

```bash
npm run lint
npm run typecheck
npm run test
npm run build
```

Use the package manager and scripts already present in the frontend project.

## Patterns to preserve

- Keep English behavior stable unless the issue explicitly changes language behavior.
- Avoid large visual rewrites for targeted UX tasks.
- Prefer component-level fixes over broad app-level rewrites.
- Keep API assumptions grounded in existing backend routes or explicit issue requirements.
- Include visual evidence for UI behavior changes, or explain why it was not possible.

## Do not touch unless required

- backend service files
- migrations
- `spec.md`
- `spec-v4.pdf`
- unrelated UI surfaces outside the issue scope

## Discovery commands

```bash
rg "<component-or-copy-or-route>" frontend/src frontend/tests
rg --files frontend/src frontend/tests
```

## Document versioning UI

Added in `feature/document-versioning` (#201 / #204 / #205).
Plan: `docs/implementation/document-versioning.md`.

### Version badges (search results)

Each search result card renders a version state badge driven by
`is_latest` and `has_newer_version` from the search payload:

| `is_latest` | Badge copy |
|---|---|
| `true` | `Latest version` |
| `false` | `Older version — newer version available` |

### Older-version warning (preview / document detail)

When `is_latest = false` on the previewed document, show a warning banner:

> _You are viewing an older version of this document. A newer version is available._

The banner provides a link/action to `latest_document_id`.

### Version history panel

A compact list on the preview page showing all versions in the family:
`version_number`, `indexed_at`, `is_latest` marker, and an open/view action.
Data source: `GET /api/documents/{document_id}/versions`.

### `include_older_versions` checkbox

Located near the search input. Default: unchecked.
When checked, sends `include_older_versions: true` in the search request body.
Older-version results must render with the "Older version" badge regardless of
the user's filter state.

### Safety requirements

- Do not display raw exception text or internal file paths to non-admin users.
- Do not leak inaccessible version IDs in version history.
- Avoid calling older content "duplicate"; use "older version" language only.

### Discovery commands

```bash
rg "is_latest\|has_newer_version\|include_older_versions\|VersionBadge\|OlderVersion" frontend/src frontend/tests
npx vitest run --reporter=verbose 2>/dev/null | grep -i version
```
