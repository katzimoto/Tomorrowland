---
name: release-pr-review
description: Use for Tomorrowland pull request review, release preparation, RC validation, changelog updates, merge readiness, and risk assessment.
license: MIT
compatibility: claude-code, opencode
metadata:
  project: Tomorrowland
  audience: review-release-agents
---

# Release PR Review

## Review goals

Decide whether a change is safe, scoped, verified, and ready to merge. Prefer actionable findings over generic feedback.

## PR review checklist

Inspect:

- Issue alignment and acceptance criteria.
- Changed files versus allowed scope.
- Public API or schema changes.
- Migrations and downgrade paths.
- Permission and data-leak boundaries.
- Tests, typecheck, lint, and build evidence.
- Frontend user flows and error states.
- Release notes or changelog needs.
- Rollback and operational risk.

## Review output

Use this format:

```md
## Verdict
Approve / Request changes / Comment only

## Blocking issues
- ...

## Non-blocking notes
- ...

## Verification reviewed
- ...

## Missing verification
- ...

## Merge risk
Low / Medium / High, with reason
```

## Release validation

For RC or release work, require:

- Artifact split/package expectations.
- Docker compose startup path.
- Search/import/document preview smoke checks.
- Translation smoke check where relevant.
- Optional Ollama behavior if affected.
- Changelog/release note accuracy.

## Guardrails

- Do not approve broad unrelated diffs.
- Do not require perfection for low-risk scoped fixes.
- Do not claim local checks passed unless evidence exists.
- Prefer exact file/line comments for blocking issues.
