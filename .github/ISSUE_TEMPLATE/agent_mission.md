---
name: Agent Mission
description: Scoped mission for Codex, Claude Code, or human-agent collaboration
title: "Mission: "
labels: []
assignees: []
---

# Mission: <short title>

## Objective
One clear deliverable.

## Context
Relevant phase, user request, design source, prior decision, or PR.

## Context Budget

Read first:
- `AGENTS.md`
- `docs/agents/token-efficiency.md`
- `<single relevant implementation/design plan>`
- `<single relevant docs/context/*.md>`

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
Directories/files the agent may edit.

## Forbidden Changes
Protected files/modules.

## Acceptance Criteria
- [ ] Targeted tests pass
- [ ] Relevant lint/type checks pass
- [ ] `CHANGELOG.md` updated if user-visible behavior, schema, config, or workflow changes
- [ ] PR references this issue and the source phase/design plan
- [ ] Agent handoff includes `Context Loaded`, `Context Skipped`, and `Token Efficiency Notes`

## Risks / Notes
Known edge cases, migrations, compatibility concerns, or follow-up work.
