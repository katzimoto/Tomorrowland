# Archive

Historical documentation moved out of `docs/` to keep the MkDocs wiki clean and
focused. These files are **not** included in the wiki navigation but are retained
for reference.

## What's here

| Directory | Contents |
|---|---|
| `implementation/` | Historical phase plans (00–10f) — design documents for features that are now implemented |
| `agents-missions/` | Completed agent mission briefs — one-off tasks executed by AI coding agents |
| `superpowers/` | Superseded design plans (RabbitMQ job bus, Meilisearch native embedder) |
| `plans/` | One-off audit fix plans |
| `review/` | Historical spec gap analysis |
| `context-budget-migration.md` | Migration plan for token-efficient issue formatting (completed) |

## Why archived?

These documents describe **past** work — implementation plans for features that
are now built, missions that were completed, and designs that were superseded.
They are not current reference material for developers or operators.

The [MkDocs wiki](../docs/index.md) contains the current, maintained documentation.
For historical context, browse the files here or use `git log`.

## When to archive

When a document describes completed work and is no longer needed in the wiki nav,
move it here. Keep it in git — don't delete it — so the project's design history
remains traceable.

> **Note:** `docs/memory/archive/` was intentionally left in place. It is the
> [shared memory system](../docs/agents/shared-memory.md)'s own internal archive
> and follows its own lifecycle independent of this top-level archive.
