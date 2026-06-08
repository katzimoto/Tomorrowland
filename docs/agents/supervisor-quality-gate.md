# Supervisor Quality Gate — Post-Review Sweep

The Supervisor is a Hermes profile (`supervisor`) that acts as the final quality
gate after a reviewer agent approves a PR and before the PR is merged.

## Workflow

```text
Coder submits PR
  → Reviewer inspects, runs targeted checks, writes review/<N>.md, approves
    → Supervisor is dispatched as a quality gate
      → Runs 4 checks: ruff lint, ruff format, mypy, pytest
        → Writes review/<N>-supervisor.md
          → PASS → PR is clear to merge
          → FAIL → PR is blocked; coder fixes failures, re-submits
```

## Supervisor profile configuration

Profile location: `/home/user/.hermes/profiles/supervisor/`

Key settings in `config.yaml`:
- `terminal.cwd`: `/home/user/projects/Tomorrowland`
- `toolsets`: `[hermes-cli]` (provides terminal, file, web, browser)
- `display.personality`: `critical`

System prompt: `SOUL.md` — defines the 4-check quality gate, report format,
and non-negotiable rules.

## How to dispatch the supervisor

### Option A: Kanban task (recommended)

Create a kanban task that the dispatcher will route to the supervisor profile
when the reviewer approves a PR:

```bash
hermes kanban create "Gate: PR #N post-review sweep" \
  --assignee supervisor \
  --body "Run the quality gate on <worktree-path>. Report to review/<N>-supervisor.md." \
  --workspace-kind dir \
  --workspace-path <worktree-path>
```

The supervisor reads the reviewer's handoff from `review/<N>.md`, runs all 4
checks, and writes the gate report.

### Option B: Direct invocation

```bash
hermes run --profile supervisor \
  "Run the quality gate on <worktree-path>. The reviewer approved PR #N. 
   Read review/<N>.md for context, then run all 4 checks and write 
   review/<N>-supervisor.md."
```

## What the supervisor checks

| Gate | Command | Pass condition |
|------|---------|---------------|
| Lint | `uv run ruff check src/ tests/ migrations/` | Exit code 0 |
| Format | `uv run ruff format --check src/ tests/ migrations/` | Exit code 0 |
| Type | `uv run mypy src --strict` | Exit code 0 |
| Tests | `uv run pytest -q` | Exit code 0 |

All 4 checks run regardless of prior failures. The supervisor never skips a
check.

## Report format

The report is written to `review/<pr-identifier>-supervisor.md`:

```markdown
# PR <N> Supervisor Gate — PASS / FAIL

## Lint (ruff check)
[PASS/FAIL — short summary]

## Format (ruff format --check)
[PASS/FAIL — short summary]

## Type check (mypy --strict)
[PASS/FAIL — short summary]

## Test suite (pytest -q)
[PASS/FAIL — short summary]

## Verdict
[ALL GATES PASS — ready to merge] or [GATE FAILURES — see details above]
```

## Interpreting the gate

- **ALL GATES PASS**: The PR has passed lint, format, type checking, and the
  full test suite. It is ready for merge. The PR author or reviewer can proceed
  with merge.
- **GATE FAILURES**: One or more checks failed. The report lists exactly which
  checks failed and what the errors were. The PR must not be merged until all
  failures are addressed and the gate is re-run.

## Warnings vs failures

The supervisor reports only PASS or FAIL — there is no "warning" tier. If a
check has a non-zero exit code, it fails. Partial passes (e.g., "tests passed
but with warnings") count as FAIL because the exit code is non-zero.

## Known limitations

- **mypy import-not-found**: When dependencies aren't installed (e.g.,
  sqlalchemy, prometheus_client), mypy reports `import-not-found` for every
  file that imports them. These are environment issues, not code defects.
  Before running the supervisor, ensure the worktree has its dependencies
  installed (`uv sync`).
- **Stale tests**: Tests that import deleted modules (like `shared.events`)
  will fail during collection. The supervisor reports these as test failures.
  Stale tests should be removed or updated before the supervisor runs.

## Integration with CI

The supervisor gate is intended as a pre-merge check, complementing the
existing GitHub Actions CI pipeline. The supervisor runs the same checks as CI
(`ruff check`, `ruff format --check`, `mypy --strict`, `pytest`) but produces
a human-readable report and can be triggered on any worktree without pushing to
GitHub.

For a fully automated pipeline:
1. Reviewer agent approves → creates kanban task for supervisor
2. Supervisor dispatcher picks up the task → runs gate on the worktree
3. Supervisor writes report → comments on the PR with the gate result
4. If PASS: PR is mergeable. If FAIL: PR stays blocked until fixes land.
