---
name: shared-memory
description: Use when agents need durable project memory across Claude, OpenCode, Codex, reviews, debugging sessions, and release work. Defines what to read, what to write, and what must never be stored.
license: MIT
compatibility: claude-code, opencode
metadata:
  project: Tomorrowland
  audience: all-agents
---

# Shared Memory

## Purpose

Use repo-owned Markdown memory as the shared brain between agents. Do not rely on hidden model memory for project state, decisions, or handoffs.

## Memory locations

- `docs/memory/current-state.md` — active priorities, known risks, and current working state.
- `docs/memory/decisions.md` — durable architecture and product decisions.
- `docs/memory/handoffs.md` — concise cross-agent handoffs that remain useful after the chat ends.
- `docs/memory/glossary.md` — Tomorrowland terms, service names, and domain vocabulary.
- `docs/agents/shared-memory.md` — rules for reading and updating memory.

## Read policy

Before substantial work, read only the memory files relevant to the task:

- Planning or prioritization: current state and decisions.
- Implementation: relevant decisions plus current-state risks.
- Review: relevant decisions plus recent handoffs.
- Debugging: current-state risks plus recent handoffs.
- Terminology or product copy: glossary.

## Write policy

Update memory only when the information will remain useful across sessions:

- A durable architecture or product decision.
- A new active priority or changed merge order.
- A repeated bug pattern or operational gotcha.
- A handoff another agent should continue from.
- A term or naming convention that prevents confusion.

Do not write memory for routine edits, one-off logs, speculative ideas, or completed details that are already obvious from the PR.

## Safety rules

Never store sensitive data, private user data, full raw logs, large transcripts, or verbose scratchpad reasoning. If a finding is unverified, mark it as unverified.

## Memory entry format

Use compact entries:

- Date and short title.
- Status: Active, Superseded, Done, or Watch.
- Source: issue, PR, commit, doc, or chat summary.
- Decision or finding.
- Impact.
- Next action.

## Agent behavior

- Prefer updating existing entries over duplicating memory.
- Mark stale entries as superseded instead of deleting history.
- Cite issue, PR, commit, or file references when possible.
- Keep memory small enough that agents can read it without wasting context.
