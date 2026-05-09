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

## Mission queue

Work in priority order. Pick the highest-ranked **Next** or **parallel-safe** mission,
read its single plan file, create the branch, and work until the plan's
"Stop after opening PR" instruction. Mark the row **In progress** in this file when you
claim it. All plan files live in `docs/implementation/`.

Parallel-safe missions share no state with other in-flight work and can run on independent
branches simultaneously.

| # | Mission | Plan | Branch | Status |
|---|---|---|---|---|
| 1 | UI: search workspace | `phase-08c-search-workspace.md` | `developer/phase-08c-search-workspace` | **Next** |
| 2 | Metrics foundation | `phase-10a-metrics-foundation.md` | `developer/phase-10a-metrics-foundation` | Done |
| 3 | Legacy Office extraction | `phase-09b-legacy-office-extraction.md` | `developer/phase-09b-legacy-office-extraction` | **Next** (parallel-safe) |
| 4 | UI: document detail + Q&A | `phase-08d-document-detail.md` | `developer/phase-08d-document-detail` | Blocked by #1 |
| 5 | Domain metrics | `phase-10b-domain-metrics.md` | `developer/phase-10b-domain-metrics` | Blocked by #2 |
| 6 | Admin readiness endpoint | `phase-10c-admin-readiness.md` | `developer/phase-10c-admin-readiness` | Blocked by #2 |
| 7 | UI: collaboration + discovery | `phase-08e-collaboration-discovery.md` | `developer/phase-08e-collaboration-discovery` | Blocked by #4 |
| 8 | Structured logs + tracing | `phase-10e-structured-logs.md` | `developer/phase-10e-structured-logs` | Blocked by #2 |
| 9 | Monitoring Compose profile | `phase-10d-monitoring-compose.md` | `developer/phase-10d-monitoring-compose` | Blocked by #5 |
| 10 | NiFi + Kafka integration | `phase-09a-nifi-integration.md` | `developer/phase-09a-nifi-integration` | **Next** (parallel-safe) |
| 11 | Atlassian hardening | `phase-09c-atlassian-hardening.md` | `developer/phase-09c-atlassian-hardening` | Conditional |
| 12 | Worker observability | `phase-10f-worker-observability.md` | `developer/phase-10f-worker-observability` | Deferred |

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

## Documentation structure rules

- Every implementation plan in `docs/implementation/` must follow the `phase-XX-name.md`
  naming convention. Never create loosely named plan files (e.g. `my-feature-plan.md`).
- When a phase covers multiple independent features, split it: one overview index file
  plus one `phase-XXa-feature.md` per feature. See phases 03, 08f, 09, and 10 as patterns.
- Every feature that has a UX spec or metric catalog must have a matching design document in
  `docs/design/`. Link the design file in the implementation plan under `## Design source`.
- Update `docs/README.md` and `docs/implementation/README.md` in the same commit whenever
  a new plan file is added or an existing file is renamed.
- After completing a phase, update its status to `Done` in both README files in the same PR.

## Review and PR expectations

- PRs should map to one phase or one named subtask.
- Include tests or a clear reason a docs-only change did not need runtime tests.
- If UI behavior changes, include visual evidence or explain why a screenshot was
  not possible.
- Reviewer reports belong in `review/<pr-number>.md` and should be concise:
  blockers, warnings, suggestions, coverage/checks, verdict.
