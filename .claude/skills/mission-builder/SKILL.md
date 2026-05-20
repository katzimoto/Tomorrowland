---
name: mission-builder
description: Use when converting a user idea, bug, design request, or agent assignment into a precise Tomorrowland mission for Claude, OpenCode, Codex, or a GitHub issue.
license: MIT
compatibility: claude-code, opencode
metadata:
  project: Tomorrowland
  audience: planning-agents
---

# Mission Builder

## Goal

Turn fuzzy requests into executable missions with clear scope, allowed changes, forbidden changes, verification, and handoff expectations.

Use this skill for prompts such as:

- Create a mission for Claude.
- Give OpenCode a task.
- Help me create an issue.
- Do not implement, just plan.
- Review this idea and make it actionable.

## Required mission format

```md
# Mission: <short action title>

## Goal
<one concrete outcome>

## Context
<repo/product context needed to start without broad reading>

## Non-goals
<what must not be changed or expanded>

## Allowed changes
<paths, modules, behaviors, or docs the agent may touch>

## Forbidden changes
<explicit boundaries, risky areas, unrelated refactors>

## Suggested files to inspect first
<small list based on the request; prefer rg if unsure>

## Implementation approach
<step-by-step, smallest safe approach>

## Verification
<exact commands or manual flows>

## Done when
<acceptance criteria>

## Handoff
<required final report fields>
```

## Agent routing

- Claude: planning, architecture, security, UX consistency, reviews, decomposition.
- OpenCode planner: read-only plan, file discovery, validation strategy.
- OpenCode builder: bounded implementation after the plan is clear.
- OpenCode reviewer: correctness, tests, typing, lint, regressions.

## Quality rules

- Prefer a small mission over a broad project brief.
- Include non-goals before implementation details.
- Name verification before code edits.
- Require honest reporting for skipped checks.
- When the request is a bug, require reproduction or a minimal diagnostic path.
- When the request is UI/UX, require preserving existing functionality.
