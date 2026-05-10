# AGENTS.md — Neverland Agent Guide

Read this first. Keep context small, verify assumptions from files, and prefer the
narrowest command that proves your change. For any non-trivial task, also read
`docs/agents/token-efficiency.md` before expanding context beyond the issue, the
single relevant plan, or one area context map.

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
- Token budget rules live in `docs/agents/token-efficiency.md`; context maps live
  in `docs/context/`.

## Mission queue

Work in priority order. Pick the highest-ranked **Next** or **parallel-safe** mission,
read its single plan file, create the branch, and work until the plan's
"Stop after opening PR" instruction. Mark the row **In progress** in this file when you
claim it. All plan files live in `docs/implementation/`.

Parallel-safe missions share no state with other in-flight work and can run on independent
branches simultaneously.

| # | Mission | Plan | Branch | Status |
|---|---|---|---|---|
| 1 | UI: search workspace | `phase-08c-search-workspace.md` | `developer/phase-08c-search-workspace` | Done |
| 2 | Metrics foundation | `phase-10a-metrics-foundation.md` | `developer/phase-10a-metrics-foundation` | Done |
| 3 | Legacy Office extraction | `phase-09b-legacy-office-extraction.md` | `developer/phase-09b-legacy-office-extraction` | **Next** (parallel-safe) |
| 4 | UI: document detail + Q&A | `phase-08d-document-detail.md` | `developer/phase-08d-document-detail` | Done |
| 5 | Domain metrics | `phase-10b-domain-metrics.md` | `developer/phase-10b-domain-metrics` | Done |
| 6 | Admin readiness endpoint | `phase-10c-admin-readiness.md` | `developer/phase-10c-admin-readiness` | **Next** (parallel-safe) |
| 7 | UI: collaboration + discovery | `phase-08e-collaboration-discovery.md` | `developer/phase-08e-collaboration-discovery` | **In progress** |
| 8 | Structured logs + tracing | `phase-10e-structured-logs.md` | `developer/phase-10e-structured-logs` | **Next** (parallel-safe) |
| 9 | Monitoring Compose profile | `phase-10d-monitoring-compose.md` | `developer/phase-10d-monitoring-compose` | **Next** |
| 10 | NiFi + Kafka integration | `phase-09a-nifi-integration.md` | `developer/phase-09a-nifi-integration` | **Next** (parallel-safe) |
| 11 | Atlassian hardening | `phase-09c-atlassian-hardening.md` | `developer/phase-09c-atlassian-hardening` | Conditional |
| 12 | Worker observability | `phase-10f-worker-observability.md` | `developer/phase-10f-worker-observability` | Deferred |

Branch validation (2026-05-09): local refs contain only the current `work` branch at the
Phase 10a merge commit; no additional unmerged `developer/*` mission branches were present
beyond the externally reported in-progress Phase 08 missions marked above.

## Context routing

Use layered context. Do not load the whole repository by default.

Default context order:

1. This `AGENTS.md` file.
2. GitHub Issue body, especially `Context Budget`, `Allowed Changes`, and `Forbidden Changes`.
3. `docs/agents/token-efficiency.md`.
4. The single implementation/design plan referenced by the issue or mission queue.
5. One relevant context map from `docs/context/`.
6. Source and test files located by `rg`.

Available context maps:

| Area | Context map |
|---|---|
| Backend API/auth/permissions | `docs/context/backend-api.md` |
| Frontend/UI | `docs/context/frontend.md` |
| Search | `docs/context/search.md` |
| Extraction | `docs/context/extraction.md` |

Use `docs/agents/issue-context-template.md` when creating or refining mission issues.
Use `docs/agents/context-budget-migration.md` when migrating older issues to include a
context budget.

## Multi-agent orchestration

Neverland may be worked on by Codex, Claude Code, and human reviewers. This file plus the
single relevant phase plan are the source of truth for repository work. GitHub Issues and
PRs are coordination objects; they do not override the mission queue or phase plans unless
the user explicitly says so.

### Agent role split

- **Claude Code** is preferred for planning, architecture review, issue decomposition,
  security/edge-case analysis, API consistency checks, and reviewer reports.
- **Codex** is preferred for scoped implementation, mechanical refactors, test generation,
  lint/type/build fixes, CI repair, and small targeted patches.
- **Human reviewers** own priority changes, merge decisions, risky migrations, and any
  change to canonical requirements.

Any agent may create or edit GitHub Issues when doing so clarifies scope, dependencies,
acceptance criteria, or follow-up work. Issue edits must be factual and concise.

### Mission ownership rules

- One branch has one active owner at a time: Codex, Claude, or a human.
- Do not edit another agent's in-progress branch unless an issue or PR comment explicitly
  transfers ownership.
- If a mission is already marked **In progress**, do not claim it unless the current owner
  hands it off.
- If working from a GitHub Issue, reference the issue number in the branch, commits, PR,
  reviewer report, and final handoff.
- If no GitHub Issue exists, the mission queue row and phase plan are sufficient authority.

### GitHub Issue workflow

Use issues to decompose large work, track dependencies, or coordinate Codex/Claude handoffs.
For new issues, prefer this compact structure:

```md
# Mission: <short title>

## Objective
One clear deliverable.

## Context
Relevant files, phase plan, constraints, and prior decisions.

## Context Budget

Read first:
- `AGENTS.md`
- `docs/agents/token-efficiency.md`
- `<single relevant implementation/design plan>`
- `<single relevant docs/context/*.md>`

Allowed source paths:
- ...

Allowed test paths:
- ...

Do not read unless explicitly needed:
- ...

Do not edit:
- `spec.md`
- `spec-v4.pdf`
- unrelated files outside the mission scope

## Relationships
Parent: #<issue> or None
Blocked by: #<issue-or-pr> or None
Blocks: #<issue-or-pr> or None
Depends on: #<issue-or-pr> or None
Related: #<issue-or-pr> or None
Follow-ups: #<issue> or None

## Allowed Changes
Directories/files the agent may edit.

## Forbidden Changes
Protected files/modules, especially `spec.md` and `spec-v4.pdf` unless explicitly allowed.

## Acceptance Criteria
- [ ] Targeted tests pass
- [ ] Lint/type checks relevant to touched code pass
- [ ] `CHANGELOG.md` updated for user-visible code, schema, config, or workflow changes
- [ ] PR references the mission issue or phase plan
- [ ] Agent handoff includes `Context Loaded`, `Context Skipped`, and `Token Efficiency Notes`

## Risks / Notes
Known edge cases, migrations, compatibility concerns, or follow-up work.
```

Recommended labels when issues are used:

```txt
agent:codex
agent:claude
status:planning
status:implementation
status:review
status:blocked
status:parallel-safe
status:needs-human
risk:high
risk:low
```

### Issue relationships and dependency graph

When issues are used, maintain explicit relationships in the issue body and update them as
work changes. Prefer plain issue/PR references so GitHub backlinks stay visible.

Relationship meanings:

- **Parent**: an umbrella issue or phase-level tracker. Parent issues describe intent and
  aggregate status; child issues contain executable work.
- **Child mission**: an independently executable issue created from a parent. Child issues
  must have their own objective, scope, owner, and acceptance criteria.
- **Blocked by**: work must not start, or must not merge, until the referenced issue or PR is
  complete. Agents may only do planning/review on blocked work unless the user explicitly
  authorizes implementation.
- **Blocks**: this issue prevents another issue from starting or merging. When completing
  this issue, notify every blocked issue with a short unblocking comment.
- **Depends on**: work may begin in parallel, but final validation or merge depends on the
  referenced issue, PR, interface, migration, or decision.
- **Related**: useful context only. No scheduling or merge constraint.
- **Duplicate**: close the duplicate and link to the canonical issue.
- **Follow-up**: new work discovered during implementation or review that should not expand
  the current mission scope.

Rules for dependency handling:

- Before claiming an issue, inspect its `Relationships` section and linked PRs.
- If `Blocked by` is not `None`, add `status:blocked` and do not implement beyond planning
  unless explicitly instructed.
- If this issue blocks others, list them under `Blocks` and mention them in the PR handoff.
- When a blocker merges or closes, comment on blocked issues with `Unblocked by #<number>`
  and replace `status:blocked` with `status:planning` or `status:implementation`.
- Parent issues should remain open until all child missions are complete or intentionally
  deferred.
- Do not use dependencies to justify scope creep. Create follow-up issues instead.

### Parallel multi-agent execution

Multiple agents may work at the same time only when their missions are explicitly
parallel-safe or their issue relationships show no blocking dependency.

Parallel work is allowed when all of these are true:

- Each agent has a different branch.
- Each agent has a different mission queue row or GitHub Issue.
- The `Allowed Changes` sections do not overlap except for coordination files.
- No issue is marked `Blocked by` another in-flight mission.
- Shared files such as `CHANGELOG.md`, `docs/README.md`, implementation indexes, migrations,
  generated files, and package lockfiles are either assigned to one owner or updated during
  the final integration pass.

Parallel work is not allowed when any of these are true:

- Two agents need to edit the same source file, migration chain, API contract, or shared
  frontend state model.
- One mission changes interfaces another mission consumes.
- One mission depends on database schema, config, route, permission, or event changes from
  another unmerged PR.
- The phase plan says to serialize the work.

Use this claim comment when starting parallel work:

```md
## Agent Claim

Owner: Codex | Claude | Human
Mission: #<issue> or `<phase-plan>.md`
Branch: `<branch>`
Parallel-safe: yes/no
Allowed paths:
- ...
Expected shared-file touches:
- None, or list files
Blocked by: None, or #<issue-or-pr>
```

Use this handoff comment when transferring ownership between agents:

```md
## Ownership Transfer

From: Codex | Claude | Human
To: Codex | Claude | Human
Branch: `<branch>`
Reason: planning complete | implementation complete | review fixes needed | CI repair needed
Current status:
- ...
Files already changed:
- ...
Do not touch:
- ...
Next action:
- ...
```

Merge order for parallel PRs:

1. Merge schema/config/API-contract PRs first.
2. Rebase or update dependent branches after upstream merges.
3. Run targeted tests for touched areas again after rebasing.
4. Merge leaf UI/docs/test-only PRs last unless they are independent.
5. If two PRs conflict, stop and assign one integration owner instead of letting both agents
   resolve the same conflict independently.

### Branch and PR coordination

Prefer the branch listed in the mission queue. For issue-only work without a listed branch,
use:

```txt
mission/<issue-number>-<short-name>
```

PRs must stay scoped to one phase, one mission, or one named subtask. PR descriptions should
include:

```md
## Mission
Closes #<issue> or references `<phase-plan>.md`.

## Changes
- ...

## Tests
- ...

## Risks
- ...

## Notes for Reviewers
- ...
```

### Review routing

- Ask **Claude** to review architecture, API consistency, security boundaries, migrations,
  edge cases, and whether the implementation matches the phase plan.
- Ask **Codex** to review implementation correctness, test coverage, lint/type failures,
  regressions, and CI failures.
- Reviewer reports belong in `review/<pr-number>.md` and should remain concise: blockers,
  warnings, suggestions, coverage/checks, and verdict.

Useful review prompts:

```txt
@claude review this PR against AGENTS.md, the phase plan, architecture consistency, and edge cases.
@codex review this PR for correctness, tests, typing, lint, regressions, and CI failures.
```

### Required agent handoff

Every agent run that changes files must end with this handoff in the PR or issue:

```md
## Agent Handoff

### Completed
- ...

### Remaining
- ...

### Tests Executed
- ...

### Context Loaded
- ...

### Context Skipped
- ...

### Token Efficiency Notes
- Used `rg` before opening files: yes/no
- Read more than one plan: yes/no, reason
- Read broad source areas: yes/no, reason

### Risks
- ...

### Suggested Next Steps
- ...
```

### Conflict policy

When instructions conflict, follow this priority order:

1. Explicit user instruction in the current task.
2. Safety and data-protection requirements.
3. This `AGENTS.md` file.
4. The relevant phase plan in `docs/implementation/`.
5. Existing code patterns and tests.
6. General agent preferences.

## Token-efficient workflow

1. Start with `git status --short` and inspect only files relevant to the task.
2. Use `rg` / `rg --files`; do not use recursive `grep` or broad file dumps.
3. Read docs in this order only as needed:
   - `CHANGELOG.md` for existing features.
   - `docs/implementation/README.md` for phase index.
   - The single phase plan that matches the task.
   - One relevant context map from `docs/context/`.
   - `docs/logical-spec.md` only for behavior questions.
4. Read `docs/agents/token-efficiency.md` for hard limits and context accounting.
5. Prefer targeted tests first, then broader checks before handoff.
6. Do not reformat unrelated files or churn generated lockfiles unless the task
   requires dependency changes.
7. Preserve user changes: if `git status --short` shows unexpected edits, inspect
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
