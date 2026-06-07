# Shared Memory Policy

Tomorrowland uses repo-owned Markdown memory as the canonical shared memory between agents. An agent database may index or cache this memory later, but project decisions and durable handoffs must remain reviewable in git.

## Canonical memory files

- `docs/memory/current-state.md` — active priorities, known risks, and current working state.
- `docs/memory/decisions.md` — durable architecture and product decisions.
- `docs/memory/handoffs.md` — concise cross-agent handoffs.
- `docs/memory/glossary.md` — Tomorrowland terms, service names, and domain vocabulary.
- `docs/memory/archive/` — memory system's internal archive (compacted entries moved here by the memory lifecycle).

> **Note:** `archive/` at the repo root is a separate top-level archive for historical project documents (implementation plans, agent missions). It is NOT the same as `docs/memory/archive/`. See `archive/README.md`.

## Agent database stance

An agent DB is allowed as a runtime accelerator, not as the only source of truth.

Preferred model:

```txt
Canonical memory: docs/memory/*.md
Indexed memory: agent database, SQLite, Postgres, Qdrant, or similar
Runtime scratch: temporary notes, run logs, diagnostics
```

The indexed layer should be rebuildable from `docs/memory/*.md`.

## Read rules

Before substantial work, read only the memory relevant to the task:

- Planning or prioritization: `current-state.md` and `decisions.md`.
- Implementation: relevant decision entries plus current-state risks.
- Review: relevant decision entries plus recent handoffs.
- Debugging: current-state risks plus recent handoffs.
- Naming/product language: glossary.

Do not read all memory files by default if the task is small.

## Write rules

Update memory only when the information will remain useful across sessions:

- Durable architecture or product decision.
- Changed priority, merge order, or release status.
- Repeated bug pattern or operational gotcha.
- Cross-agent handoff that should survive the chat.
- Naming convention or domain term that prevents confusion.

Do not store routine edit summaries, noisy diagnostics, speculative ideas, or details already obvious from the PR.

## Safety rules

Do not store sensitive data, private user data, full raw logs, large transcripts, or hidden reasoning. Mark unverified claims as unverified.

## Entry format

```md
## YYYY-MM-DD — Short title

Status: Active | Superseded | Done | Watch
Source: Issue #123 | PR #456 | commit | doc | chat summary

Decision / Finding:
- ...

Impact:
- ...

Next action:
- ...
```

## Maintenance rules

- Update existing entries instead of duplicating them.
- Mark stale entries as `Superseded` rather than deleting useful history.
- Keep memory compact enough for agents to read cheaply.
- Prefer issue, PR, commit, or file references over vague summaries.
