---
name: tl-implement-issue
description: >
  Use this skill when implementing a Tomorrowland GitHub issue, feature branch task, or
  mission brief. Invoke it at the start of any non-trivial implementation, refactor, or
  bug fix — including when a mission brief says "implement", "build", "add", "fix", or
  "wire up". Covers the full workflow: context loading, code discovery, surgical editing,
  verification, and handoff. Also use it when resuming an in-progress implementation or
  picking up work from a planner handoff.
license: MIT
compatibility: claude-code, opencode
metadata:
  project: Tomorrowland
  audience: implementation-agents
---

# tl-implement-issue

## Purpose

This skill is the standard implementation workflow for Tomorrowland issues. It makes the full cycle explicit so nothing important gets skipped — especially verification and handoff — which are the two steps most often dropped under time pressure.

## Step 1: Load context (in this order, stop when you have enough)

1. `AGENTS.md` — branch policy, dev commands, multi-agent rules
2. `docs/agents/token-efficiency.md` — context limits, search-first rules
3. `docs/agents/coding-behavior.md` — execution discipline
4. The GitHub Issue body — goal, Context Budget, Allowed/Forbidden Changes, acceptance criteria
5. One referenced design or implementation plan (only if the issue links one or the issue is vague)
6. One relevant `docs/context/<area>.md` (backend-api, frontend, search, extraction) — only when needed
7. `docs/memory/current-state.md` + `docs/memory/decisions.md` — active state and durable decisions relevant to this area

Stop loading when you can state the goal, the affected files, and the verification step. Do not read `spec.md` or `spec-v4.pdf`.

## Step 2: Discover code with rg before opening files

Run targeted searches to find the exact files and symbols you need. Open files only after you know why.

```bash
rg "<route or symbol or model name>" src/ tests/ -n
rg --files src/services/<area>/
git diff --name-only <base-branch>...HEAD
```

If you find yourself opening a file to look around, stop and search more specifically first.

## Step 3: State the plan (briefly, internally or in one paragraph)

Before touching any file, state:
- **Goal**: one concrete outcome
- **Assumptions**: anything that could be wrong
- **Smallest safe change**: what you'll actually touch
- **Files to change**: list them
- **Verification**: the exact commands you'll run

If this can't be stated clearly, the context loading in Step 1 is incomplete.

## Step 4: Implement

Follow `safe-implementation` discipline:
- Touch only what the issue requires
- Match the project's existing patterns
- No speculative abstractions, no configurability for its own sake
- No formatting-only changes on unrelated files
- Dead code: mention it, don't delete it unless it's yours

For new tests: write the test first if the issue is a bug (failing test proves the bug), or alongside the implementation for features.

After implementing:
- If the change is user-visible, update `CHANGELOG.md`.
- If `graphify-out/` exists, run `graphify update .` to keep the knowledge graph current (AST-only, no API cost).

## Step 5: Verify (run in this order, fix before continuing)

Backend (all commands use `uv run`):
```bash
uv run ruff check --fix src/ tests/ migrations/
uv run ruff format src/ tests/ migrations/
uv run mypy src --strict
uv run pytest tests/unit/test_<area>.py -q
uv run pytest tests/integration/test_<area>.py -q
```

Frontend (when changed; run from `frontend/`):
```bash
npm run typecheck
npx vitest run src/features/<area>/   # or the relevant test file
```

If a command can't run (environment gap, Docker not up), say so explicitly — do not claim it passed.

The 90% coverage floor is enforced on the full suite. Targeted runs will show a coverage failure — that's expected. Run the full suite only when CI isn't available and a complete verification is needed.

## Step 6: Update shared memory (only when useful cross-session)

Update `docs/memory/` only for information that will help a future agent:
- A durable decision that changed (`decisions.md`)
- A new active risk or milestone (`current-state.md`)
- A handoff another agent should continue from (`handoffs.md`)

Skip memory updates for routine edits. Use compact entry format with Date, Status, Source, Finding, Impact, Next action.

## Step 7: Produce the handoff

End with this format:

```md
## Handoff

### Completed
- ...

### Changed files
- `src/...`

### Verification run
- `pytest tests/unit/test_<area>.py` — N passed

### Verification skipped
- `pytest` full suite — reason

### Context Loaded
- AGENTS.md, coding-behavior.md, issue #<N>

### Context Skipped
- spec.md — not authorized

### Risks / follow-ups
- ...

### Next recommended step
- ...
```

Do not invent a passing verification. Report what ran and what didn't.
