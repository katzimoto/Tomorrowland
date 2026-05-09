# Frontend Agent Guide

Scope: everything under `frontend/`.

## Fast orientation

- React 19 + TypeScript + Vite app.
- Routing: TanStack Router.
- Server state: TanStack Query.
- Forms: React Hook Form + Zod.
- Tests: Vitest + Testing Library; E2E config uses Playwright.
- API integration and token/session behavior live under `src/lib/`.

## Token-efficient workflow

1. Read `package.json` scripts before inventing commands.
2. Inspect only the component, route, API helper, or test touched by the task.
3. Reuse existing primitives before adding new UI patterns.
4. Keep CSS aligned with existing design tokens instead of one-off values.
5. Avoid package updates unless the user asks or the task cannot be done without
   them.

## Commands

Run from `frontend/`.

```bash
npm run lint
npm run typecheck
npm run test
npm run build
npm run test:e2e
```

Use targeted Vitest runs while iterating, for example:

```bash
npx vitest run src/path/to/file.test.tsx
```

## Common mistakes to avoid

- Do not read from `localStorage` directly in components; use the existing auth
  token/session boundary.
- Do not create fetch calls outside the API client layer.
- Do not add route-level data fetching that bypasses TanStack Query conventions.
- Do not introduce unlabelled form controls or inaccessible icon-only buttons.
- Do not rely on color alone for state; preserve keyboard and screen-reader
  affordances.
- Do not commit `dist/`, Playwright reports, or coverage output.
