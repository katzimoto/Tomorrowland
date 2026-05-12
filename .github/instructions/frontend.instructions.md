---
applyTo: "frontend/**/*.{ts,tsx,js,jsx,css,html,json}"
---

# Frontend instructions

Follow `AGENTS.md` and `frontend/AGENTS.md` first. These rules apply to the React
frontend under `frontend/`.

## Scope and architecture

- Keep changes scoped to the issue and the touched component or feature area.
- Do not redesign the app shell, navigation, branding, or shared layout unless
  the issue explicitly asks.
- Preserve Hebrew/English localization behavior. Do not hardcode user-facing text
  where existing translation dictionaries or localization helpers are used.
- Keep frontend-only polish separate from backend API, release, docs, and
  branding work.

## TypeScript and React

- Prefer explicit types at public boundaries and for non-obvious state.
- Do not silence TypeScript, lint, or accessibility warnings without explaining
  why in the PR.
- Prefer small components and hooks over broad rewrites.
- Preserve existing loading, empty, error, and permission-denied states when
  editing UI flows.
- Avoid introducing new runtime dependencies unless the issue authorizes them.

## Validation

Run the narrowest checks that prove the touched frontend area, then broader
checks when the PR changes shared UI, routing, translations, build config, or API
contracts.

Useful commands from repo root:

```bash
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```
