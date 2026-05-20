---
name: agent-handoff
description: Use at the end of substantial Tomorrowland agent work or when transferring work between Claude, OpenCode, Codex, reviewer, or release agents.
license: MIT
compatibility: claude-code, opencode
metadata:
  project: Tomorrowland
  audience: all-agents
---

# Agent Handoff

## Purpose

Reduce context loss between agents. Every substantial task should end with a compact, factual handoff that another agent can continue from without re-reading everything.

## Required handoff format

```md
## What changed
- ...

## Changed files
- `path/to/file`

## What I verified
- Command/manual flow and result

## What I did not verify
- Check skipped and reason

## Open risks
- ...

## Suggested next agent
Claude / OpenCode planner / OpenCode builder / OpenCode reviewer / release-manager

## Exact next prompt
```text
<copy-paste prompt for the next agent>
```
```

## Rules

- Be specific and short.
- Do not claim verification that did not run.
- Include failed commands when relevant.
- Separate completed work from recommended follow-up.
- Name the next agent only when there is a clear follow-up.
- Include the issue/PR number when known.

## Transfer patterns

### Planner to builder

Include approved approach, allowed paths, forbidden paths, and verification command.

### Builder to reviewer

Include changed files, tests run, skipped checks, and areas needing careful review.

### Reviewer to builder

Include blocking findings, exact fix request, and verification needed.

### Debugger to builder

Include reproduction, likely root cause, minimal fix path, and validation command.
