# Agent Instructions

Use GitHub Issues and PRs as the current source of truth for Tomorrowland work.
Historical phase plans are useful context only when an issue asks for them.

## Practical workflow

1. Read `AGENTS.md` first, then `docs/agents/token-efficiency.md` for any
   non-trivial task.
2. If using GitHub Copilot, also read `.github/copilot-instructions.md` and the
   relevant path-specific instruction file under `.github/instructions/`.
3. Read the issue body before source files. Follow its context budget, allowed
   paths, forbidden paths, and acceptance criteria.
4. Keep context narrow. Use `rg` and `rg --files` before opening files.
5. Do not edit `spec.md` or `spec-v4.pdf` unless the user explicitly asks.
6. Keep release blockers isolated from optional features, UI polish, and future
   planning work.
7. Do not mix release management, architecture planning, implementation, and
   optional PR work in one PR.
8. End changed-file runs with a clear handoff: completed work, remaining work,
   tests, context loaded/skipped, risks, and next steps.

## Role routing

- Use Claude Code for planning, architecture review, security/edge cases, broad
  localization/UX consistency, docs polish, issue decomposition, and reviewer
  reports.
- Use Codex for scoped implementation after a plan, mechanical refactors,
  targeted tests, lint/type/build fixes, scripts, and CI repair.
- Use GitHub Copilot for in-editor implementation help, narrow issue execution,
  repetitive refactors, targeted tests, PR summaries, and additional code review
  comments.
- Human reviewers own priority changes, merge decisions, risky migrations,
  destructive-operation policy, and canonical requirement changes.

## Copilot

- [Copilot workflow](copilot.md) — how to route Tomorrowland work to Copilot,
  which prompts to use, and when to escalate to Codex, Claude, or a human.
