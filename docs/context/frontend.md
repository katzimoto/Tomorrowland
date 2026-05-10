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
