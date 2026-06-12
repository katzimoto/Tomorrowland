# AGENTS.md — Tomorrowland (compact)

Read this first. Keep context minimal and prefer the narrowest command that proves
your change. For non-trivial tasks, read `docs/agents/token-efficiency.md`,
`docs/agents/coding-behavior.md`, and `docs/agents/ci-hardening.md` first.

## CI Hardening (MANDATORY)

**Every agent MUST pass the local quality gate before committing or pushing.**
See `docs/agents/ci-hardening.md` for the full rules. Summary:

1. Run `uv run ruff check --fix src/ tests/ migrations/` — fix all issues
2. Run `uv run ruff format src/ tests/ migrations/` — no formatting changes
3. Run `uv run mypy src --strict` — zero errors
4. Run `uv run pytest tests/unit/test_<area>.py -q` — tests pass
5. Before push: run `uv run pytest tests/unit/ -q`

**Never commit code that fails these checks.** Never use `--no-verify` for PR-ready code.
Never suppress ruff/mypy errors to make CI pass.

## Dev commands (exact)

Backend (run from repo root). All Python commands use `uv run`:

```bash
uv run ruff check --fix src/ tests/ migrations/
uv run ruff format src/ tests/ migrations/
uv run mypy src --strict
uv run pytest tests/unit/test_<area>.py -q
uv run pytest tests/integration/test_<area>.py -q
uv run pytest
```

Quick targeted runs:

```bash
uv run pytest tests/unit/test_search_hybrid.py -q
```

Frontend (run from repo root): see `frontend/AGENTS.md` for commands and
conventions (do not duplicate frontend policies here).

Quick targeted runs:

```bash
uv run pytest tests/unit/test_search_hybrid.py -q
npx vitest run src/path/to/file.test.tsx
```

Order: fix → format → typecheck → test. CI enforces this. Note: backend CI uses
Python 3.13; local dev is supported on Python >=3.11.

## Architecture (what agents need to know)

- Monorepo: Python backend at repo root, React frontend in `frontend/`.
- ASGI entrypoint: `src/services/api/asgi:app` (uvicorn). Routes are organized
  in `src/services/api/routers/` by domain and included in `main.py` via `APIRouter`.
- Services: `src/services/{auth,permissions,documents,extraction,pipeline,search,translation,intelligence,connectors,comments,annotations,alerts,rag,related,preview}`.
- Shared infra: `src/shared/` (config, DB helpers, logging, events, metrics).
- Config: Pydantic Settings auto-loads `.env` (`shared.config.Settings`).
- Migrations: `migrations/versions/`. Every migration must include upgrade and
  downgrade paths. Integration tests migrate a temporary SQLite DB via the
  `migrated_engine` fixture (`tests/conftest.py`) so `pytest` normally does not
  require Docker services.
- Coverage: no enforced floor and not collected by default; opt in with
  `uv run pytest --cov=src --cov-branch` when you need a coverage report.
- Docker Compose: standard services include api, frontend, postgres, meilisearch,
  qdrant, kafka (Redpanda), rabbitmq, libretranslate, ollama, and the pipeline
  workers. Optional `monitoring` profile adds Prometheus/Grafana on loopback.
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

- All agents: apply `docs/agents/coding-behavior.md` for non-trivial implementation, review, and debugging work.
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
- **Every coding mission MUST end with a PR.** Never leave work as local-only commits, dangling branches, or uncommitted changes in worktrees. Push the branch and open a PR — even for drafts. If you can't push (e.g., no network), at minimum commit with a clear message and tell Chief of Staff where the branch lives. Work without a PR is lost work.

## Mandatory PR policy (all crew coding agents)

**For any task that changes code, config, or tests in the repo:**

1. **Commit** your changes to a named branch (never leave uncommitted worktree state).
2. **Push** the branch to `origin`.
3. **Create a PR** with a descriptive title and body referencing the kanban task ID.
4. **Post the PR URL** in the kanban task comment when completing — this is part of the handoff.

**Why:** Remote branches survive worktree GC; local-only commits don't. PRs create a durable, reviewable record. The pre-PR checklist (`scripts/check-pr-cleanliness.sh`) catches agent artifacts before merge.

**Enforcement:** The board self-healing cron (`217969c3ed9e`) will flag completed coding tasks without linked PRs. Chief of Staff will chase these up.

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
3. `docs/agents/coding-behavior.md`
4. `CLAUDE.md` (Claude Code only)
5. GitHub Issue body (`Context Budget`, `Allowed Changes`, `Forbidden Changes`)
6. Single referenced implementation/design plan, if any
7. One relevant `docs/context/<area>.md` when needed (backend-api, frontend, search, extraction)
8. Source & test files discovered with `rg`
9. `CHANGELOG.md` before assuming a feature is missing

Do not read `spec.md` or `spec-v4.pdf` unless explicitly authorized.

## References

- `docs/agents/token-efficiency.md` — context limits and handoff fields
- `docs/agents/coding-behavior.md` — shared execution discipline for simple, surgical, verifiable work
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

6. **Documentation updated** — every non-trivial change must include docs.
   See `docs/agents/documenting-features.md` for the change-type → docs mapping.
   At minimum, verify the relevant wiki page is updated and run:
   ```bash
   uv run mkdocs build --strict
   ```
   CI enforces this through the `Docs CI` workflow.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, invoke the `skill` tool with `skill: "graphify"` before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
