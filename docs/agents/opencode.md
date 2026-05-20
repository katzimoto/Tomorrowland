# OpenCode workflow

Use OpenCode as a local repository coding agent for scoped implementation,
review preparation, and test/debug loops. Do not use it as the source of truth
for Tomorrowland priority, architecture, release policy, security posture, or
merge decisions.

OpenCode loads additional instruction files from `opencode.json`. This repository
uses that file to include the shared token-efficiency rules, shared coding
behavior rules, and this OpenCode workflow document.

## What OpenCode should do

Good OpenCode missions:

- Implement a small issue after the issue defines allowed paths and acceptance
  criteria.
- Add or update targeted backend or frontend tests.
- Repair lint, typecheck, build, or failing-test output after the exact failure is
  known.
- Perform mechanical refactors inside one bounded module or component area.
- Prepare a concise handoff after local changes.

Avoid broad missions such as "clean up the backend", "improve the frontend",
"make release ready", "fix security", or "modernize the codebase". Convert broad
work into GitHub Issues first.

## Required startup context

For non-trivial tasks, load only this context before opening source files:

1. `AGENTS.md`
2. `docs/agents/token-efficiency.md`
3. `docs/agents/coding-behavior.md`
4. `docs/agents/opencode.md`
5. The GitHub Issue body
6. One relevant context map or implementation plan, only if the issue points to it

Then use `rg` / `rg --files` to locate exact source and test files.

## Execution discipline

For every non-trivial implementation task, apply `docs/agents/coding-behavior.md`:

- Restate the goal before editing.
- State assumptions and ambiguity.
- Identify the smallest safe change.
- Keep the diff surgical.
- Do not refactor adjacent code unless explicitly asked.
- Do not add speculative abstractions or extra features.
- Name the verification command or manual flow before changing code.
- Report verification honestly at handoff.

## Recommended prompts

For implementation:

```text
Use this issue as the source of truth. Read AGENTS.md, docs/agents/token-efficiency.md,
docs/agents/coding-behavior.md, docs/agents/opencode.md, and only the allowed
paths listed in the issue. Make the smallest code change that satisfies the
acceptance criteria. End with the standard agent handoff and list the checks you
ran.
```

For test generation:

```text
Add targeted tests for the behavior described in this issue. Do not change
production code unless a failing test proves a bug and the issue allows it.
Explain the exact behavior covered by each test.
```

For CI or local failure repair:

```text
Use the failing output as the source of truth. Identify the failing command,
exact error, likely root cause, minimal fix, files involved, and validation
command before editing files.
```

For plan-then-build work:

```text
Plan mode first: restate the goal, assumptions, smallest safe approach, files
likely to change, and verification steps. Do not edit files in plan mode.

Build mode after approval: implement only the approved plan, keep the diff
surgical, run the agreed verification, and report changed files, checks, skipped
checks, risks, and follow-ups.
```

## Routing with other agents

- Use OpenCode for local implementation loops, bounded refactors, targeted tests,
  and failure repair.
- Use GitHub Copilot for in-editor completions, PR summaries, narrow issue
  execution, and extra code-review comments.
- Use Codex for mechanical repository-level execution, branch-level tasks, and CI
  repair where remote GitHub workflow context matters.
- Use Claude for architecture, security, migrations, edge cases, issue
  decomposition, and broad review.
- Use a human reviewer for priority changes, canonical requirements, release
  decisions, destructive-operation policy, and merges.

## Done criteria for OpenCode work

OpenCode work is ready for PR or handoff only when:

- The work references exactly one issue or named subtask.
- Changed files stay inside the allowed scope.
- Tests/checks are listed, or skipped checks are justified.
- Risks and follow-ups are explicit.
- The handoff includes completed work, remaining work, tests, context loaded,
  context skipped, token efficiency notes, changed files, verification, and next
  steps.