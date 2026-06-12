# CI Hardening Rules for All Agents

These rules are MANDATORY for all coding agents (backend-coder, frontend-coder, freebuff, codex, claude-code). They prevent CI breaks.

## The Golden Rule

**Never push code that hasn't passed the local quality gate.**

If you commit code that breaks ruff, mypy, or tests, you WILL break CI. This is non-negotiable.

## Pre-Commit Checklist (MANDATORY before every commit)

Before ANY git commit, you MUST run these checks locally:

```bash
uv run ruff check --fix src/ tests/ migrations/
uv run ruff format src/ tests/ migrations/
uv run mypy src --strict
uv run pytest tests/unit/test_<area>.py -q  # at minimum, tests in your change area
```

If any of these fail, FIX THEM before committing. Do not commit with known failures.

## Pre-Push Checklist (MANDATORY before every push)

Before ANY git push, you MUST run:

```bash
uv run pytest tests/unit/ -q
```

For full confidence (before PR):

```bash
uv run pytest -q
```

## What Breaks CI (Common Agent Mistakes)

1. **Adding unused imports** — ruff F401. Always run `ruff check --fix`.
2. **Wrong type annotations** — mypy --strict catches mismatches. Use explicit types.
3. **Renaming a function/class** — breaks all callers. Search before renaming.
4. **Adding a new parameter without default** — breaks all callers. Use optional params.
5. **Changing a public API without updating consumers** — breaks integration tests.
6. **Copying code with wrong indentation** — ruff catches this. Format after paste.
7. **Adding code that imports a module not in pyproject.toml** — mypy import-not-found.
8. **Writing a test that imports a deleted module** — test collection failure.
9. **Using `Any` everywhere** — mypy --strict disallows uninferred `Any`.
10. **Forgetting to add migration for schema changes** — integration tests fail.

## Surgical Editing Rules

- Touch ONLY files required by your task
- Do NOT reformat files you didn't change
- Do NOT refactor adjacent code
- Do NOT delete code you think is "dead" — mention it instead
- Match existing code style exactly
- If you add a new file, add tests for it

## Test Requirements

- Every new function/method needs at least one test
- Every new API endpoint needs integration tests
- Every bug fix needs a regression test
- Tests must be in the right directory: `tests/unit/` or `tests/integration/`
- Use existing test patterns — read similar tests first

## When You're Stuck

If CI fails after you push:
1. Read the CI log carefully
2. Reproduce locally: `uv run ruff check --fix && uv run mypy src --strict && uv run pytest -q`
3. Fix the root cause, don't just suppress
4. Push the fix

Do NOT:
- Suppress ruff errors with `# noqa` without a good reason
- Add `type: ignore` to fix mypy errors
- Delete a failing test instead of fixing it
- Disable CI checks

## Coverage Floors (active, #703)

These floors are enforced in CI. Do not lower them without a matching issue.

### Backend (`backend.yml` — `quality` job)

```
--cov=src --cov-branch --cov-fail-under=60
```

Measured baseline: 62% branch+statement coverage from the unit test suite
(`tests/` excluding `tests/integration/`). Floor set at baseline − 2.
To raise: run `uv run pytest tests/ -q --ignore=tests/integration --cov=src
--cov-branch --cov-report=term` locally, confirm the new floor, update
`--cov-fail-under` in `backend.yml`.

### Frontend (`frontend/vitest.config.ts`)

```ts
thresholds: { statements: 50, branches: 33, functions: 42, lines: 50 }
```

Raised from 30/20/25/30 after WS4 backend and frontend test-gap issues (#701,
#702) landed. To raise further: run `npm run test:coverage` (requires
`@vitest/coverage-v8`), confirm the new numbers, update `vitest.config.ts`.

## Nightly CI (`nightly-integration.yml`, #703)

A scheduled workflow at `02:00 UTC` catches regressions per-PR CI cannot:

| Check | Detail |
|---|---|
| Integration suite | Full `tests/integration/` against PostgreSQL |
| Migration downgrade smoke | Last 5 revisions: upgrade → downgrade -1 → upgrade head (SQLite + Postgres) |
| Retrieval eval | `tests/eval --eval`; result JSON uploaded as artifact for trending |

The eval job is `continue-on-error: true` (trending only, no hard gate on
eval metrics). Trigger manually via `workflow_dispatch` to validate.

## Emergency Bypass

If you absolutely must commit broken code (e.g., WIP for handoff):
1. Use a WIP commit message: `WIP: <description> — will fix CI`
2. NEVER push WIP commits to main or feature branches
3. Fix before creating a PR
4. Use `git commit --no-verify` only for WIP commits, never for PR-ready code
