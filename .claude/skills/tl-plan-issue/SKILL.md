---
name: tl-plan-issue
description: >
  Use this skill when planning (but not yet implementing) a Tomorrowland GitHub issue,
  feature, or architectural change. Invoke it when the mission says "plan only", "design
  the approach", "do not implement yet", or when the work is complex enough that an
  approved plan is worth having before code is written. Produces a compact implementation
  plan — goal, assumptions, affected files, approach steps, verification, and risks —
  without editing any source files. Hand the plan off to tl-implement-issue when approved.
license: MIT
compatibility: claude-code, opencode
metadata:
  project: Tomorrowland
  audience: planning-agents
---

# tl-plan-issue

## Purpose

Planning before implementing reduces wasted work. This skill produces a concise, reviewable implementation plan by doing the context loading and code discovery that an implementor would do anyway — but stopping before any edits, so a human or reviewer can sanity-check the approach first.

The plan is useful when:
- The task has multiple valid approaches with real tradeoffs
- Schema, API contract, or permission boundary changes are involved
- The issue says "plan only" or comes from a decomposition step
- An agent is handed off mid-flight and needs to restate the approach before continuing

## Step 1: Load context

Same order as `tl-implement-issue`, but lighter — stop as soon as you can fill the plan template:

1. `AGENTS.md`
2. `docs/agents/token-efficiency.md`
3. The GitHub Issue body (goal, constraints, acceptance criteria)
4. One referenced design doc — only if the issue links one or the approach is genuinely unclear
5. One `docs/context/<area>.md` — only when the plan requires understanding an area's conventions
6. `docs/memory/decisions.md` — for decisions that constrain the approach

Skip `coding-behavior.md` — that's for implementors. Do not read `spec.md` or `spec-v4.pdf`.

## Step 2: Discover affected code with rg

Do not open files unless a targeted search proves they're relevant:

```bash
rg "<symbol or route or model>" src/ tests/ -n --max-count 5
rg --files src/services/<area>/
```

This is the most important step: a plan that names the wrong files wastes the implementor's time.

## Step 3: Write the plan

Use this format exactly:

```md
## Plan: <issue title>

### Goal
One concrete outcome sentence.

### Assumptions
- What must be true for this plan to work.
- Anything that could be wrong.

### Out of scope
- What this plan explicitly does not cover.

### Affected files
- `src/...` — what changes and why
- `tests/...` — new/updated tests

### Approach
1. Step one (what and why)
2. Step two
3. ...

### Verification
- `ruff check --fix src/ tests/`
- `mypy src --strict`
- `pytest tests/unit/test_<area>.py -q`
- `pytest tests/integration/test_<area>.py -q`
- (frontend) `npm run typecheck`, `npx vitest run src/features/<area>/`

### Risks
- ...

### Open questions
- Anything that needs human or reviewer decision before implementation starts.
```

Keep the plan concise. If the approach has two viable options with different tradeoffs, present both and flag the decision.

## Step 4: Stop here

Do not edit any source file. Do not create migration files. Do not write tests.

The plan's value is being reviewable before implementation. Editing files defeats that purpose.

If a question is blocking (e.g., which scope types need validation?) and you can resolve it by reading one more file, do it — then note in Open Questions that the answer came from `<file>`.

## What comes next

Hand the plan to an implementor with:

```
Use tl-implement-issue. The plan is in this message. Branch: <branch>.
Do not re-plan; just implement the steps above and verify as specified.
```

Or present the plan to the human for approval before spawning an implementor.
