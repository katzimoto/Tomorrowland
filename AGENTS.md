# AGENTS.md — Tomorrowland (compact)

Read this first. Keep context minimal and prefer the narrowest command that proves
your change. For non-trivial tasks, read `docs/agents/token-efficiency.md` first.

## Dev commands (exact)

Backend (run from repo root):

```bash
ruff check --fix src/ tests/ migrations/
ruff format src/ tests/ migrations/
mypy src --strict
pytest tests/unit/test_<area>.py -q
pytest tests/integration/test_<area>.py -q
pytest
```

Frontend (run from repo root): see `frontend/AGENTS.md` for commands and
conventions (do not duplicate frontend policies here).

Quick targeted runs:

```bash
pytest tests/unit/test_search_hybrid.py -q
npx vitest run src/path/to/file.test.tsx
```

Order: fix → format → typecheck → test. CI enforces this. Note: backend CI uses
Python 3.13; local dev is supported on Python >=3.11.

## Architecture (what agents need to know)

- Monorepo: Python backend at repo root, React frontend in `frontend/`.
- ASGI entrypoint: `src/services/api/asgi:app` (uvicorn). All routes live in
  `src/services/api/main.py` — do not split routes without explicit authorization.
- Services: `src/services/{auth,permissions,documents,extraction,pipeline,search,translation,intelligence,connectors,comments,annotations,alerts,rag,related,preview}`.
- Shared infra: `src/shared/` (config, DB helpers, logging, events, metrics).
- Config: Pydantic Settings auto-loads `.env` (`shared.config.Settings`).
- Migrations: `migrations/versions/`. Every migration must include upgrade and
  downgrade paths. Integration tests migrate a temporary SQLite DB via the
  `migrated_engine` fixture (`tests/conftest.py`) so `pytest` normally does not
  require Docker services.
- Coverage: tests enforce a 90% coverage floor (`pyproject.toml`).
- Docker Compose: standard services include api, frontend, postgres, elasticsearch,
  qdrant, kafka (Redpanda), libretranslate, ollama. Optional `monitoring` profile
  adds Prometheus/Grafana on loopback.
- Air-gapped release: platform archive + split image parts + optional Ollama
  model bundle. Operator wrapper: `scripts/tomorrowland-airgap.sh`.

## Release guardrails (short)

- One active RC at a time: builds → validation → attach assets/checksums → then
  resume next-RC work.
- Do not close a release issue until CI passed, artifacts & checksums exist,
  assets attached to the GitHub Release, air-gap validation passed, and the
  final URL/checksum is posted back to the issue.
- Always refresh `main` before creating release branches (`git pull --ff-only origin main`).
- Preserve release tooling (`scripts/*-ollama*.sh`, `build_ollama_bundle`, `ollama_model` workflow inputs) unless the mission explicitly changes them.
- Large features (new architecture, workers, air-gapped packaging, model packs) default to `future/deferred` unless the release owner explicitly promotes them.
- One status label per issue/PR: `status:next|status:in-progress|status:deferred|status:done`.
- Debug failing logs before changing workflows, Dockerfiles, or scripts.

## Multi-agent rules (concise)

- Claude Code: planning, architecture/security reviews, API/UX/consistency,
  docs polish, high-level decomposition.
- Codex: scoped implementation after a plan, mechanical refactors, tests/CI
  fixes, small targeted patches.
- Human reviewers: merge decisions, risky migrations, destructive operations,
  canonical requirement changes.
- One branch — one active owner. Reference the issue in branch names and PRs.
- Create an issue before non-trivial work. If work discovers independent
  features, open separate issues.

## Feature branch policy

Large multi-issue features must target a dedicated integration branch first,
not `main` directly. This prevents partial merges from leaving the app in an
inconsistent state.

### When to use a feature branch

Use `feature/<short-feature-name>` when work involves any of:

- multiple issues under one parent feature;
- architecture or runtime changes;
- schema + backend + frontend coordination;
- worker/runtime split work;
- air-gapped packaging changes;
- search/vector/indexing model changes;
- release packaging changes;
- any change where a partial merge to `main` would break consistency.

Examples:

- `feature/pipeline-jobs` for #209/#213/#214/#215/#216
- `feature/document-versioning` for #201/#202/#203/#204/#205
- `feature/vector-safety` for #184/#185/#186
- `feature/structured-logging` for #63/#163/#164/#165/#179/#180/#181
- `feature/admin-source-ux` for #87/#170/#171

Small isolated fixes may still target `main` directly: one-file frontend cleanup,
isolated test-only PRs, docs-only changes, or focused bugfixes with no multi-PR
dependency.

### Branch flow

```text
main
  -> feature/<feature-name>
       <- PR for issue A
       <- PR for issue B
       <- PR for issue C
       <- integration validation / fix PRs
  -> final PR: feature/<feature-name> -> main
```

Subtask branches target the feature branch. Only the final integration PR
targets `main`.

### PR requirements

- PR title/body must state the base branch clearly.
- PR body must explain whether it targets `main` or a feature branch.
- Do not retarget or merge feature sub-PRs into `main` without explicit approval.
- The integration branch must periodically rebase/merge latest `main` and rerun CI.
- The final PR to `main` must include an integration validation summary
  (ruff, mypy, pytest, frontend checks, production-audit where applicable).

### Guardrails

- Do not use a feature branch as a dumping ground for unrelated work.
- Do not merge broken intermediate states into `main`.
- Do not bypass branch protection or CI.
- Keep subtask branches small and reviewable even when they target a feature branch.

## Shared-file conflicts (short)

Touch these only when required or when your PR owns the final integration:
`CHANGELOG.md`, `README.md`, `AGENTS.md`, `CLAUDE.md`, package lockfiles,
migrations, frontend translation dictionaries, release/operations docs, generated
artifacts.

Preferred merge order for parallel PRs: schema/config → backend interfaces →
frontend consumers → docs/test-only → final integration/changelog.

## Context loading order (token-efficient)

1. `AGENTS.md`
2. `docs/agents/token-efficiency.md`
3. `CLAUDE.md` (Claude Code only)
4. GitHub Issue body (`Context Budget`, `Allowed Changes`, `Forbidden Changes`)
5. Single referenced implementation/design plan, if any
6. One relevant `docs/context/<area>.md` when needed (backend-api, frontend, search, extraction)
7. Source & test files discovered with `rg`
8. `CHANGELOG.md` before assuming a feature is missing

Do not read `spec.md` or `spec-v4.pdf` unless explicitly authorized.

## References

- `docs/agents/token-efficiency.md` — context limits and handoff fields
- `docs/agents/templates.md` — claim/transfer/issue/PR templates (new)
- `frontend/AGENTS.md` — frontend-specific conventions
- `docs/context/*.md` — area context maps

## Pre-PR changed-files checklist

Before opening any PR, run the following and review every file listed:

```bash
git diff --name-only <target-branch>...HEAD
```

For PRs targeting `main` use `main`; for feature-branch sub-PRs use the feature
branch name. Then verify:

1. **Every changed file is in scope** — it must be required by the issue.
   Unexplained out-of-scope changes block merge.
2. **No local agent artifacts** — the following files must not appear in the diff:
   - `.opencode_auth.json`
   - `token_opencode.txt`
   - any root-level file named `main` (without extension)
   These belong in `.git/info/exclude` or your global gitignore, not in
   `repo/.gitignore` and never in a commit.
3. **No unrelated `.gitignore` additions** — only add entries that the team has
   agreed to track. Local tooling exclusions go in `.git/info/exclude` or
   `~/.gitignore_global`.
4. **No formatting-only changes outside scope** — ruff/prettier churn on files
   not touched by the issue adds noise and risks merge conflicts.
5. **No execute-bit or trailing-newline-only diffs** — check with
   `git diff --stat` and `git diff` before staging.

Run the guard script for a quick automated check:

```bash
bash scripts/check-pr-cleanliness.sh [target-branch]
```

## Conventions & guardrails (quick)

### Python
- Files start with `from __future__ import annotations`.
- Ruff line length = 100; mypy is strict.
- Use `str | None`, `dict[str, Any]`, modern generics.
- Use `shared.db.db_uuid(value)` for SQL UUID parameter binding.
- Use SQLAlchemy bound parameters; do not interpolate SQL strings.

### FastAPI & persistence
- Auth dependency: `Depends(current_user)`.
- Admin-only: `require_admin(user)`.
- Document access: `assert_doc_access(doc_id, user, auth_repo)`.
- DB transaction: `with app.state.engine.begin() as connection:`.

### Data-layer guardrail
Default: SQLAlchemy Core repos + Pydantic models + Alembic migrations. Do not
introduce SQLModel or refactor data-layer broadly unless explicitly authorized.

### Common mistakes
- Do not serve `document.path` directly; use safe download/path validation.
- Do not bypass feature flags.
- Do not create migrations without downgrade paths.
- Do not add hardcoded secrets; `.env.example` contains placeholders only.
- Do not move routes out of `src/services/api/main.py` without explicit authorization.

### Review routing (short)
- Claude: architecture, API consistency, security boundaries, migrations, plan compliance.
- Codex: correctness, tests, typing, lint, regressions, CI.

Useful prompts:
```txt
@claude review this PR against AGENTS.md, the issue, architecture consistency, and edge cases.
@codex review this PR for correctness, tests, typing, lint, regressions, and CI failures.
```
