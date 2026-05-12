# Agent Templates

Use these when claiming work, transferring ownership, or handing off.

## Agent Claim

```md
## Agent Claim
Owner: Codex | Claude | Human
Issue: #<issue>
Branch: `<branch>`
Parallel-safe: yes/no
Allowed paths:
- ...
Expected shared-file touches:
- None, or list files
Blocked by: None, or #<issue-or-pr>
```

## Ownership Transfer

```md
## Ownership Transfer
From: Codex | Claude | Human
To: Codex | Claude | Human
Branch: `<branch>`
Reason: planning complete | implementation complete | review fixes needed | CI repair needed
Current status:
- ...
Files already changed:
- ...
Do not touch:
- ...
Next action:
- ...
```

## Required Handoff

```md
## Agent Handoff
### Completed
- ...
### Remaining
- ...
### Tests Executed
- ...
### Context Loaded
- ...
### Context Skipped
- ...
### Token Efficiency Notes
- Used `rg` before opening files: yes/no
- Read more than one plan: yes/no, reason
- Read broad source areas: yes/no, reason
### Risks
- ...
### Suggested Next Steps
- ...
```

## GitHub Issue Template

```md
# Mission: <short title>
## Objective
One clear deliverable.
## Context Budget
Read first:
- `AGENTS.md`
- `docs/agents/token-efficiency.md`
- `<single relevant plan or context doc>`
Allowed source paths:
- ...
Allowed test paths:
- ...
Do not read unless explicitly needed:
- ...
Do not edit:
- `spec.md`
- `spec-v4.pdf`
- unrelated files outside the mission scope
## Relationships
Parent: #<issue> or None
Blocked by: #<issue-or-pr> or None
Blocks: #<issue-or-pr> or None
Depends on: #<issue-or-pr> or None
Related: #<issue-or-pr> or None
Follow-ups: #<issue> or None
## Allowed Changes
- ...
## Forbidden Changes
- ...
## Acceptance Criteria
- [ ] Targeted tests/checks pass
- [ ] `CHANGELOG.md` updated when user-visible behavior, schema, config, docs workflow, or operations change
- [ ] PR references this issue
- [ ] Agent handoff includes context accounting
```

## PR Description Template

```md
## Mission
Closes #<issue>.
## Changes
- ...
## Tests / Checks
- ...
## Risks
- ...
## Notes for Reviewers
- ...
## Agent Handoff
...
```
