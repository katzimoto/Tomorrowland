# Phase 08f-5: Production Audit Helper

## Goal

Add a bounded, repeatable production-hardening audit helper that operators and
reviewers can run before the no-mock smoke test. This step captures static
validation and optional dependency-audit checks without starting the Compose
stack or printing secrets.

## Branch

`developer/phase-08f-5-production-audit`

## Recommended Prerequisites

- Phase 08f-1 through 08f-4 merged so production defaults, operations docs,
  smoke-test automation, and the smoke bootstrap helper are stable.

## Scope

- Add a repository-root script for production audit checks that:
  - validates pending diffs with `git diff --check`;
  - verifies `docker compose config` renders successfully;
  - scans tracked application code for hardcoded secret-like assignments outside
    test files;
  - can run Python and frontend dependency audits on demand.
- Document the helper in production operations docs.
- Keep dependency audits opt-in so offline review environments can still run the
  non-network static checks.

## Out Of Scope

- Starting or smoke-testing the stack; `scripts/smoke-test.sh` remains the
  no-mock runtime validation path.
- Replacing project lint, type-check, or test commands.
- Adding unauthenticated bootstrap or administrative endpoints.

## Validation

```bash
bash -n scripts/production-audit.sh
bash scripts/production-audit.sh
bash scripts/production-audit.sh --include-dependency-audits
```

If Docker or dependency-audit tools are unavailable in the review environment,
record the exact failing command and environment limitation in the PR notes.

## Acceptance Criteria

- Reviewers have a single documented command for production static checks.
- Dependency audits are available without making network-dependent checks a
  prerequisite for every local run.
- Secret-like assignment hits outside tests fail clearly and redact the matched
  assignment value in diagnostics.
- The helper does not start or mutate the Compose stack.

Stop for Reviewer-agent review.
