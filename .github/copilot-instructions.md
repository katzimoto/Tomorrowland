# GitHub Copilot instructions for Tomorrowland

Use this file as Copilot-specific onboarding. The canonical project workflow remains
`AGENTS.md`; read it before making non-trivial changes. Also read
`docs/agents/token-efficiency.md` before expanding context beyond the issue and
immediate files.

## Project orientation

Tomorrowland is a local-first private document intelligence system. It is built
for local and air-gapped deployments, so do not assume runtime internet access,
remote model APIs, or online package downloads are available in deployed mode.

Backend stack: Python 3.11+, FastAPI, SQLAlchemy Core, PostgreSQL,
Elasticsearch, Qdrant, Kafka-compatible event plumbing, LibreTranslate, and
optional Ollama.

Frontend stack: React 19, TypeScript, and Vite in `frontend/`.

Canonical requirements live in `spec.md` and `spec-v4.pdf`. Do not edit them
unless a human explicitly asks.

## How to work in this repository

- Work from a GitHub Issue when possible. The issue body overrides older phase
  plans when it includes allowed paths, forbidden paths, context budget, and
  acceptance criteria.
- Keep each change scoped to one issue, one phase, or one named subtask.
- Do not mix release blockers, architecture planning, feature implementation,
  UI polish, docs cleanup, and optional future work in one PR.
- Use `rg` / `rg --files` before opening broad source areas.
- Read `CHANGELOG.md` before assuming a feature is missing.
- Preserve user changes and avoid editing another agent's branch unless ownership
  has been explicitly transferred.
- Keep generated artifacts and release assets out of normal implementation PRs.

## Copilot role in the agent split

Use Copilot mainly for narrow implementation, repetitive refactors, targeted
tests, PR summaries, and code review comments. For security-sensitive, release,
architecture, migration, or destructive-operation decisions, leave clear notes
for Claude or a human reviewer instead of broadening the change.

## Safety guardrails

- Never hardcode secrets. `.env.example` and `.env.airgap.example` may contain
  placeholders only.
- Do not bypass auth, permission, feature-flag, or safe download/path validation
  patterns.
- Do not serve raw `document.path` values directly.
- Use SQLAlchemy bound parameters; do not interpolate SQL strings.
- Every schema migration needs both upgrade and downgrade behavior.
- Do not introduce SQLModel or broadly refactor repositories unless an issue
  explicitly authorizes it.
- Preserve air-gapped behavior: release artifacts must not require builds or
  internet access at runtime.

## Validation expectations

Run the narrowest checks that prove the changed area. Prefer targeted tests first,
then broader checks when the risk or touched area justifies it.

Backend commands from repo root:

```bash
ruff check src/ tests/ migrations/
mypy src --strict
pytest tests/unit/test_<area>.py -q
pytest tests/integration/test_<area>.py -q
```

Frontend commands from repo root:

```bash
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
```

Docs-only changes should usually state that product tests were not run and why.

## PR and handoff expectations

PR descriptions should include mission, changes, tests/checks, risks, reviewer
notes, and an agent handoff. End changed-file work with:

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

### Risks
- ...

### Suggested Next Steps
- ...
```

For Copilot code review, focus comments on correctness, regression risk,
security/permissions, test gaps, build failures, and deviation from the issue or
`AGENTS.md`. Avoid style-only churn unless it blocks maintainability.
