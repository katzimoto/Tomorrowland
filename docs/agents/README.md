# Agent Instructions

Use GitHub Issues and PRs as the current source of truth for Tomorrowland work.
Historical phase plans are useful context only when an issue asks for them.

## Practical workflow

1. Read `AGENTS.md` first, then `docs/agents/token-efficiency.md` for any
   non-trivial task.
2. Read the issue body before source files. Follow its context budget, allowed
   paths, forbidden paths, and acceptance criteria.
3. Keep context narrow. Use `rg` and `rg --files` before opening files.
4. Do not edit `spec.md` or `spec-v4.pdf` unless the user explicitly asks.
5. Keep release blockers isolated from optional features, UI polish, and future
   planning work.
6. Do not mix release management, architecture planning, implementation, and
   optional PR work in one PR.
7. End changed-file runs with a clear handoff: completed work, remaining work,
   tests, context loaded/skipped, risks, and next steps.

## Role routing

- Use Claude Code for planning, architecture review, security/edge cases, broad
  localization/UX consistency, docs polish, and issue decomposition.
- Use Codex for scoped implementation after a plan, mechanical refactors,
  targeted tests, lint/type/build fixes, scripts, and CI repair.
- Human reviewers own priority changes, merge decisions, risky migrations,
  destructive-operation policy, and canonical requirement changes.
