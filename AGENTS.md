# AGENTS.md — Tomorrowland Agent Guide

Read this first. Keep context small, verify assumptions from files, and prefer the
narrowest command that proves your change. For any non-trivial task, also read
`docs/agents/token-efficiency.md` before expanding context beyond the issue, the
single relevant plan, or one area context map.

## Fast orientation

- Tomorrowland is a local-first knowledge intelligence system for private document
  corpora.
- Backend: Python 3.11+ / FastAPI / SQLAlchemy / PostgreSQL / Elasticsearch /
  Qdrant / LibreTranslate.
- Frontend: React 19 / TypeScript / Vite in `frontend/`.
- Canonical requirements are `spec.md` and `spec-v4.pdf`; do not edit them
  unless the user explicitly asks.
- Current implementation history lives in `CHANGELOG.md`; read the latest
  `[Unreleased]` bullets before assuming a feature is missing.
- Current executable work is tracked in GitHub Issues. Issue bodies override the
  old phase table when they include a context budget, allowed paths, and
  acceptance criteria.

## Current release queue

Work from GitHub Issues first. Pick the highest-priority open issue whose
relationships do not block implementation. If an issue has a planning request for
Claude, do not implement until the plan is posted or the user explicitly says to
proceed.

### Release-critical path

| Priority | Issue | Owner fit | Status note |
|---|---|---|---|
| 1 | #83 Hebrew and English UI Localization | Claude implementation, Codex fixups | Release-target UI requirement. |
| 2 | #75 Air-Gapped Upgrade Without Data Loss | Claude plan, Codex implementation, Claude review | Safety-sensitive; wait for plan before implementation. |
| 3 | #65 NiFi Event Integration and Kafka Consumer Wiring | Claude plan, Codex implementation | Release-target connector work; no live NiFi/Kafka in CI. |
| 4 | #79 NTFS ACL Permission Sync for SMB Sources | Claude security plan/review, narrow Codex implementation | Security-sensitive; disabled by default and fail-closed. |
| 5 | #84 Frontend Perceived Performance Polish | Claude or Codex | Parallel-safe frontend polish. |
| 6 | #85 Search Workflow Keyboard and Quick Preview | Claude or Codex | Parallel-safe frontend workflow polish. |
| 7 | #86 Large List and Lazy Panel Performance | Claude or Codex | Parallel-safe frontend rendering polish. |
| 8 | #87 Admin Source Sync Usability Polish | Claude or Codex | May touch frontend and small admin API paths. |
| 9 | #88 Frontend User Performance Telemetry | Claude or Codex | Privacy-safe local timing instrumentation. |
| 10 | #89 Agent Docs and Release Queue Efficiency Refresh | Claude or human | Docs-only coordination cleanup. |

### Optional or deferred before release candidate

| Issue | Status guidance |
|---|---|
| #63 Structured Logs and Tracing Hooks | Useful ops polish; not a release blocker unless requested. |
| #64 Optional Monitoring Compose Profile | Enterprise polish; can follow release candidate. |
| #58 Legacy Office Format Extraction | Do before release only if `.doc`, `.xls`, `.ppt` corpora are required. |
| #66 Optional Atlassian Permission Hardening | Decision-gated; may close with no code if not required now. |
| #67 Worker Observability | Deferred until long-running worker entrypoints exist. |

### Recently completed release-hygiene work

Do not reclaim these unless a new regression issue is opened:

- #60 Admin readiness endpoint — done.
- #61 UI collaboration and discovery — done via #81; #72 was superseded.
- #77 SMB Source Connector MVP — done via #80.
- #78 Host-Mounted SMB Share Deployment Guide — done via #82.

## Context routing

Use layered context. Do not load the whole repository by default.

Default context order:

1. `AGENTS.md`.
2. `docs/agents/token-efficiency.md`.
3. `CLAUDE.md` when running Claude Code.
4. GitHub Issue body, especially `Context Budget`, `Allowed Changes`, and
   `Forbidden Changes`.
5. The single implementation/design plan referenced by the issue, if any.
6. One relevant context map from `docs/context/`, when needed.
7. Source and test files located with `rg`.
8. `CHANGELOG.md` before assuming a feature is missing.

Available context maps:

| Area | Context map |
|---|---|
| Backend API/auth/permissions | `docs/context/backend-api.md` |
| Frontend/UI | `docs/context/frontend.md` |
| Search | `docs/context/search.md` |
| Extraction | `docs/context/extraction.md` |

For docs-only missions, do not read product source code unless the docs need exact
service names, commands, paths, or API behavior.

## Multi-agent orchestration

Tomorrowland may be worked on by Codex, Claude Code, and human reviewers. GitHub
Issues and PRs are the coordination objects for current work. This file provides
routing rules; it should not be treated as a stale static project plan.

### Agent role split

- **Claude Code** is preferred for planning, architecture review, security/edge
  cases, API consistency checks, broad frontend localization, UX/text consistency,
  docs polish, issue decomposition, and reviewer reports.
- **Codex** is preferred for scoped implementation after a plan, mechanical
  refactors, test generation, lint/type/build fixes, CI repair, scripts, shell
  safety, and small targeted patches.
- **Human reviewers** own priority changes, merge decisions, risky migrations,
  destructive-operation policy, and changes to canonical requirements.

Security-sensitive work such as #79 must be planned/reviewed by Claude and
implemented narrowly with strict tests. Destructive or safety-sensitive work such
as #75 must have a reviewed plan before implementation.

## Mission ownership rules

- One branch has one active owner at a time: Codex, Claude, or a human.
- Do not edit another agent's in-progress branch unless an issue or PR comment
  explicitly transfers ownership.
- If working from a GitHub Issue, reference the issue number in the branch, PR,
  reviewer report, and final handoff.
- If no issue exists, create one before implementing non-trivial work.
- If work discovers independent features, create separate issues instead of
  expanding the current PR.

Use this claim comment when starting work:

```md
## Agent Claim

Owner: Codex | Claude | Human
Issue: #<issue>
Branch: `<branch>`
Parallel-safe: yes/no
Allowed paths:
- ...
Expected shared-file touches:
- None, or list files
Blocked by: None, or #<issue-or-pr>
```

Use this handoff comment when transferring ownership:

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

## Shared-file conflict policy

These files often conflict across parallel work and should have a single owner or
be handled in a final integration pass:

- `CHANGELOG.md`
- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- package lockfiles
- migrations and migration indexes
- frontend translation dictionaries
- release/operations docs
- generated artifacts

If two PRs need the same shared file, merge the schema/API/config PR first, then
rebase the second branch and resolve the shared file once. Do not let two agents
resolve the same conflict independently.

Merge order for parallel PRs:

1. Schema/config/API-contract PRs.
2. Backend services that define interfaces.
3. Frontend consumers of those interfaces.
4. Docs/test-only PRs.
5. Final integration/changelog cleanup.

## GitHub Issue workflow

For new issues, prefer this compact structure:

```md
# Mission: <short title>

## Objective
One clear deliverable.

## Context Budget
Read first:
- `AGENTS.md`
- `docs/agents/token-efficiency.md`
- `<single relevant plan or context doc>`

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
- ...

## Forbidden Changes
- ...

## Acceptance Criteria
- [ ] Targeted tests/checks pass
- [ ] `CHANGELOG.md` updated when user-visible behavior, schema, config, docs workflow, or operations change
- [ ] PR references this issue
- [ ] Agent handoff includes context accounting
```

Recommended labels:

```txt
mission
status:planning
status:next
status:implementation
status:review
status:blocked
status:done
parallel-safe
risk:high
risk:low
```

## Branch and PR expectations

For issue-only work without a listed branch, use:

```txt
issue/<issue-number>-<short-name>
```

PRs must stay scoped to one issue, one phase, or one named subtask. PR
descriptions should include:

```md
## Mission
Closes #<issue>.

## Changes
- ...

## Tests / Checks
- ...

## Risks
- ...

## Notes for Reviewers
- ...

## Agent Handoff
...
```

## Required agent handoff

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

## Token-efficient workflow

1. Start with `git status --short` and inspect only files relevant to the task.
2. Use `rg` / `rg --files`; do not use recursive `grep` or broad file dumps.
3. Prefer the issue body over old phase docs when an issue has a context budget.
4. Read at most one implementation plan, one design doc, and one context map by
   default.
5. Do not read `spec.md` or `spec-v4.pdf` unless the user explicitly asks or the
   issue authorizes it.
6. Prefer targeted tests first, then broader checks before handoff.
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
ruff check --fix src/ tests/ migrations/
ruff format src/ tests/ migrations/
mypy src --strict
pytest tests/unit/test_<area>.py -q
pytest tests/integration/test_<area>.py -q
pytest
```

## Frontend commands

Run from repo root.

```bash
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

## Python conventions

- Every Python file starts with `from __future__ import annotations`.
- Ruff line length is 100; mypy is strict.
- Public functions/classes need Google-style docstrings.
- Use `str | None`, `dict[str, Any]`, and modern generic syntax.
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
- Do not forget `CHANGELOG.md` for user-visible code, schema, config, operations,
  docs workflow, or release-process changes.
- Do not add hardcoded secrets; `.env.example` may contain placeholders only.
- Do not move routes out of `src/services/api/main.py` unless a phase explicitly
  authorizes the refactor.
- Do not update `spec.md` or `spec-v4.pdf` as implementation notes.

## Documentation structure rules

- Implementation plans in `docs/implementation/` follow the `phase-XX-name.md`
  naming convention.
- When a phase covers multiple independent features, split it into one overview
  plus one `phase-XXa-feature.md` per feature.
- Update `docs/README.md` and `docs/implementation/README.md` when adding or
  renaming plan files.
- After completing a phase, update its status in the relevant README files in the
  same PR when those indexes are still authoritative.

## Review routing

- Ask **Claude** to review architecture, API consistency, security boundaries,
  migrations, edge cases, and plan compliance.
- Ask **Codex** to review implementation correctness, test coverage, lint/type
  failures, regressions, and CI failures.
- Reviewer reports should be concise: blockers, warnings, suggestions,
  coverage/checks, and verdict.

Useful review prompts:

```txt
@claude review this PR against AGENTS.md, the issue, architecture consistency, and edge cases.
@codex review this PR for correctness, tests, typing, lint, regressions, and CI failures.
```
