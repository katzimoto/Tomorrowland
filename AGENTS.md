# AGENTS.md — Neverland Agent Guide

Read this first. Keep context small, verify assumptions from files, and prefer the
narrowest command that proves your change.

## Fast orientation

- Neverland is a local-first knowledge intelligence system for private document
  corpora.
- Backend: Python 3.11+ / FastAPI / SQLAlchemy / PostgreSQL / Elasticsearch /
  Qdrant / LibreTranslate.
- Frontend: React 19 / TypeScript / Vite in `frontend/`.
- Canonical requirements are `spec.md` and `spec-v4.pdf`; do not edit them
  unless the user explicitly asks.
- Current implementation history lives in `CHANGELOG.md`; read the latest
  `[Unreleased]` bullets before assuming a phase is missing.

## Token-efficient workflow

1. Start with `git status --short` and inspect only files relevant to the task.
2. Use `rg` / `rg --files`; do not use recursive `grep` or broad file dumps.
3. Read docs in this order only as needed:
   - `CHANGELOG.md` for existing features.
   - `docs/implementation/README.md` for phase index.
   - The single phase plan that matches the task.
   - `docs/logical-spec.md` only for behavior questions.
4. Prefer targeted tests first, then broader checks before handoff.
5. Do not reformat unrelated files or churn generated lockfiles unless the task
   requires dependency changes.
6. Preserve user changes: if `git status --short` shows unexpected edits, inspect
   before touching those files.

## Repo map

| Area | Path | Notes |
|---|---|---|
| API routes | `src/services/api/main.py` | MVP keeps all FastAPI routes here. |
| Auth/users/groups | `src/services/auth/` | JWT, password, LDAP boundary, repositories. |
| Permissions | `src/services/permissions/` | Use existing guards before adding new checks. |
| Documents | `src/services/documents/` | Metadata repository and document models. |
| Extraction | `src/services/extraction/` | Registry pattern; tests per file type. |
| Pipeline/workers | `src/services/pipeline/` | Ingestion, slow translation, intelligence hooks. |
| Search | `src/services/search/` | Elasticsearch, Qdrant, hybrid merge. |
| Shared infra | `src/shared/` | Config, DB helpers, logging, events. |
| Backend tests | `tests/unit/`, `tests/integration/` | Match test scope to touched code. |
| Frontend | `frontend/` | React app; see `frontend/AGENTS.md`. |
| Migrations | `migrations/versions/` | Every schema change needs upgrade and downgrade. |

## Backend commands

Run from repo root.

```bash
# Fast lint/format/type checks
ruff check --fix src/ tests/ migrations/
ruff format src/ tests/ migrations/
mypy src --strict

# Targeted tests
pytest tests/unit/test_<area>.py -q
pytest tests/integration/test_<area>.py -q

# Full backend suite with coverage
pytest
```

## Python conventions

- Every Python file starts with `from __future__ import annotations`.
- Ruff line length is 100; mypy is strict.
- Public functions/classes need Google-style docstrings.
- Use `str | None`, `dict[str, Any]`, and other modern generic syntax.
- Import order: standard library, third-party, local.
- Use `shared.db.db_uuid(value)` for SQL UUID parameter binding.
- Use SQLAlchemy bound parameters; do not interpolate SQL strings.

## FastAPI and persistence patterns

- Auth dependency: `Depends(current_user)`.
- Admin-only operation: call `require_admin(user)`.
- Document access: call `assert_doc_access(doc_id, user, auth_repo)` before
  reading or mutating protected document data.
- DB transaction pattern: `with app.state.engine.begin() as connection:`.
- External services in unit tests should be mocked or stubbed.
- Integration tests use fixtures from `tests/conftest.py`, especially
  `migrated_engine`.

## Common mistakes to avoid

- Do not serve `document.path` directly; use the existing safe download/path
  validation patterns.
- Do not bypass feature flags for optional capabilities.
- Do not create a migration without a downgrade path.
- Do not forget `CHANGELOG.md` for user-visible code, schema, config, or docs
  workflow changes.
- Do not add hardcoded secrets; `.env.example` may contain placeholders only.
- Do not move routes out of `src/services/api/main.py` unless a phase explicitly
  authorizes the refactor.
- Do not update `spec.md` or `spec-v4.pdf` as implementation notes.

## Review and PR expectations

- PRs should map to one phase or one named subtask.
- Include tests or a clear reason a docs-only change did not need runtime tests.
- If UI behavior changes, include visual evidence or explain why a screenshot was
  not possible.
- Reviewer reports belong in `review/<pr-number>.md` and should be concise:
  blockers, warnings, suggestions, coverage/checks, verdict.
