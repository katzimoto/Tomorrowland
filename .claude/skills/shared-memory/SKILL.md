---
name: shared-memory
description: Repo-owned Markdown memory (docs/memory/*.md) is the shared brain across Claude, OpenCode, Codex, and release/review/debug agents. Use this skill whenever you start substantial work (read the relevant memory first), finish substantial work or hand off, record an architecture or product decision, note a recurring bug or operational gotcha, or when a memory file has grown too large to read (compact it). Covers what to read, what to write, the on-disk entry format, the memory.py append/archive/stats helper, and committing memory. Reach for it even when the user just says "remember this", "update the memory", "hand this off", or "what's the current state".
license: MIT
compatibility: claude-code, opencode
metadata:
  project: Tomorrowland
  audience: all-agents
---

# Shared Memory

## Purpose

Project state, decisions, and handoffs live in `docs/memory/*.md` — plain Markdown in the repo, reviewable in git, readable by every agent and tool. This is the shared brain. Do not rely on a model's hidden memory or a private cache for anything another agent would need: if it isn't in `docs/memory/`, it effectively doesn't exist for the next session.

`docs/agents/shared-memory.md` is the canonical policy; this skill is the operational companion (format, routing, the helper script, compaction). If the two ever disagree, the repo doc wins.

## Which file holds what (one home per fact)

| File | Holds | Lifecycle |
|------|-------|-----------|
| `current-state.md` | What's true and active **now**: in-flight work, active priorities, known risks / `Watch` items, recent merges | Churns; compacted as it grows |
| `decisions.md` | Durable architecture/product decisions and conventions that outlive the work that prompted them | Long-lived; only `Superseded` entries leave |
| `handoffs.md` | "Next agent, continue from here": goal, changed files, key invariants, a next-step prompt | Compacted once consumed |
| `glossary.md` | Terms, service names, domain vocabulary | Stable reference; never archived |

**De-duplicate by reference, not by copy.** Each fact has one home. If it's relevant in another file, link it by date + title (e.g. "see decisions.md 2026-06-01 — QA UI removed") rather than pasting the same paragraph into three files — copies drift and bloat the read path.

## Reading (don't ingest 1000-line files)

These files grow, so getting oriented should not mean reading a whole file:

- Newest entries are at the **top** — read the first ~100–150 lines for current context (`sed -n '1,150p' docs/memory/current-state.md`).
- Looking for a specific thing? `grep -n` the topic or date (`grep -n "airgap\|#624" docs/memory/*.md`).
- `python .claude/skills/shared-memory/scripts/memory.py stats` shows each file's size and entry counts.

Read only what the task needs: planning → current-state + decisions; implementation → relevant decisions + current-state risks; review → relevant decisions + recent handoffs; debugging → current-state risks + recent handoffs; naming → glossary.

## Entry format (on-disk)

Newest entries go at the **top**, under the file's one-line intro, separated by a `---` line. Use this shape:

```markdown
## YYYY-MM-DD — short title

Status: Active | Watch | Done | Superseded
Source: issue / PR / commit / doc / chat

<2–8 line body: the decision or finding, its impact, and the next action.
Tables, bullet lists, and a "Next agent prompt:" blockquote are welcome in handoffs.>
```

`Status` meanings: **Active** = current and true; **Watch** = an open risk to keep an eye on; **Done** = completed, kept for history; **Superseded** = replaced (point to what replaced it). Convert relative dates ("today", "last week") to absolute ones — entries outlive the session that wrote them.

## Writing: what earns a place

Write only what stays useful across sessions:

- A durable architecture or product decision → `decisions.md`.
- A new active priority, changed merge order, or known risk → `current-state.md`.
- A repeated bug pattern or operational gotcha (e.g. a branch that keeps reverting released work) → `current-state.md` (Watch) or `decisions.md`.
- A handoff another agent should continue from → `handoffs.md`.
- A term or naming convention that prevents confusion → `glossary.md`.

Skip routine edits, one-off run logs, speculative ideas, and details already obvious from the PR or git history. Prefer updating an existing entry over adding a near-duplicate; mark the old one `Superseded` instead of deleting it (history stays in git).

**Never store** secrets, tokens, private user data, full raw logs, large transcripts, or verbose scratch reasoning. Mark anything unverified as unverified, so a later agent doesn't treat a hunch as fact.

## The memory.py helper

`.claude/skills/shared-memory/scripts/memory.py` (stdlib only; run from the repo root — it finds `docs/memory/` itself) keeps the format consistent and the files small.

**Append** an entry (body on stdin, so multi-line bodies are easy):

```bash
printf '**Done:** merged to main (cec926d).\n**Next:** resolve the double-index question.\n' \
  | python .claude/skills/shared-memory/scripts/memory.py append \
      --file handoffs --title "review+fix #624" --status Done --source "PR #624, cec926d"
```

It writes the dated header, inserts at the top, and adds the `---` separator for you. `--file` takes a short name (`current-state`, `decisions`, `handoffs`, `glossary`) or a path.

**Stats** — see which files are getting heavy:

```bash
python .claude/skills/shared-memory/scripts/memory.py stats
```

You can always edit the files by hand instead; the script just removes the boilerplate and the guesswork about format and position.

## Keeping files readable (compaction)

An active file you can't read is useless, so keep `current-state.md` and `handoffs.md` lean (roughly under ~40 entries; `stats` flags files above that). When one gets heavy, move stale entries out:

```bash
python .claude/skills/shared-memory/scripts/memory.py archive --file current-state --keep 25 --dry-run
python .claude/skills/shared-memory/scripts/memory.py archive --file current-state --keep 25
```

This moves `Done`/`Superseded` entries that fall outside the newest `--keep` into `docs/memory/archive/<name>.md` — still in git for history, just out of the agent read path. `Active` and `Watch` entries are **never** archived, no matter their age. Leave `decisions.md` and `glossary.md` alone (decisions are durable — mark them `Superseded` rather than archiving; the glossary is a reference).

## Committing memory

Memory only becomes shared once it's committed — an uncommitted edit helps no one. Keep it a small, separate commit (`docs(memory): …`). You're usually on `main`, so branch first unless the user explicitly asks to commit to `main`, and don't push unless asked. If `main` has moved, pull (fast-forward) before committing so your entry lands on top of current state.
