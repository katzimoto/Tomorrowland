---
name: safe-implementation
description: Use before implementation, refactor, bug fix, or review work. Enforces simple, surgical, verifiable changes aligned with Tomorrowland agent rules.
license: MIT
compatibility: claude-code, opencode
metadata:
  project: Tomorrowland
  audience: implementation-agents
---

# Safe Implementation

## Operating mode

Implement the smallest change that satisfies the task. Do not expand scope, redesign adjacent systems, or refactor unrelated code.

## Before editing

State internally or in the plan:

1. The concrete goal.
2. Assumptions and ambiguity.
3. The smallest safe change.
4. Files likely to change.
5. Verification to run.

## While editing

- Match existing patterns.
- Keep public behavior unchanged unless requested.
- Do not add speculative abstractions.
- Do not add configurability unless required.
- Do not reformat unrelated files.
- Do not delete unrelated dead code; mention it instead.
- Prefer one bounded patch over a wide cleanup.

## Bug fixes

For bugs, prefer this sequence:

1. Identify the failing path.
2. Reproduce or describe the minimal reproduction.
3. Find the smallest root-cause fix.
4. Add or update a focused test when practical.
5. Verify the failing path is fixed.

## UI changes

For UI/UX implementation:

- Preserve existing functionality and API contracts.
- Keep core flows reachable.
- Maintain loading, empty, and error states.
- Include screenshot or manual-flow notes when relevant.

## Final report

Always include:

- Changed files.
- What changed.
- Verification run.
- Verification skipped and why.
- Remaining risk.
- Suggested next step.
