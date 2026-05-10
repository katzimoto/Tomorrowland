# CODEX.md — Neverland Codex Entry Point

Codex must treat `AGENTS.md` as the primary repository instruction file.

Before taking implementation work, Codex must read:

1. `AGENTS.md`
2. `docs/agents/token-efficiency.md`
3. The selected GitHub Issue body
4. The issue `Context Budget`
5. The single referenced implementation or design plan
6. One relevant `docs/context/<area>.md` file if listed

## Issue selection

If the user or workflow references a specific issue, use that issue only.

If no issue number is provided, choose exactly one open issue using this priority order:

1. Issues labeled `agent:codex` and `status:implementation`.
2. Issues labeled `agent:codex` and `status:parallel-safe`.
3. Issues whose Claude Planning Report says `Ready for Codex? Yes`.
4. The smallest unblocked issue with the narrowest `Allowed Changes`.

Skip issues with:

- `status:blocked`
- `status:needs-human`
- `status:planning`
- `status:review`
- unresolved `Blocked by` relationships
- missing `Context Budget`
- missing `Allowed Changes`
- missing `Forbidden Changes`
- an active `Agent Claim` by another agent

Before changing files, post an `Agent Claim` comment on the issue.

## Implementation rules

- Implement one issue only.
- Stay strictly inside `Allowed Changes`.
- Do not edit `Forbidden Changes`.
- Use `rg` before opening source files.
- Keep diffs minimal and scoped.
- Add or update targeted tests.
- Update `CHANGELOG.md` only for user-visible behavior, schema, config, or workflow changes.
- Do not edit `spec.md` or `spec-v4.pdf` unless explicitly authorized.
- Do not merge manually.

## Branch and PR rules

Use this branch pattern:

```txt
mission/<issue-number>-<short-slug>
```

Open a draft PR when implementation is complete enough for review. The PR must:

- link the issue with `Closes #<issue-number>`;
- include test results;
- include the full `Agent Handoff` from `AGENTS.md`;
- add labels `agent:codex` and `status:review`;
- add `automerge:eligible` only when the PR is low risk, scoped, tested, and not blocked.

Do not add `automerge:eligible` if the PR:

- has `risk:high`;
- needs a human decision;
- changes migrations, authentication, authorization, data deletion, secrets, deployment, or canonical requirements;
- has failing or unrun critical checks;
- violates the Context Budget or Allowed Changes.

## Automated handoff flow

The expected automated path is:

1. A ready issue gets `agent:codex` and `status:implementation`.
2. The automation posts an `@codex` implementation request.
3. Codex claims the issue and implements it.
4. Codex opens a PR with `agent:codex`, `status:review`, and optionally `automerge:eligible`.
5. The auto-Claude-review workflow requests Claude review.
6. If Claude approves, CI passes, required labels are present, and no stop labels exist, the auto-merge workflow may merge the PR.

Stop and comment instead of continuing when any gate is unclear.
