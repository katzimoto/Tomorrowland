---
name: tomorrowland-project-context
description: Use for Tomorrowland planning, review, debugging, and implementation context. Summarizes the product domain, architecture map, repo context order, and handoff expectations.
license: MIT
compatibility: claude-code, opencode
metadata:
  project: Tomorrowland
  audience: all-agents
---

# Tomorrowland Project Context

## Product domain

Tomorrowland is a local-first knowledge intelligence system for private document corpora. Its core domain is documents, metadata, previews, permissions, translation, collaboration, search, indexing, and optional local LLM assistance.

## Context order

For non-trivial work, prefer this order:

1. `AGENTS.md`
2. `docs/agents/token-efficiency.md`
3. `docs/agents/coding-behavior.md`
4. `CLAUDE.md` for Claude Code tasks
5. The relevant GitHub Issue body when present
6. One relevant `docs/context/<area>.md` file when needed
7. Source and test files found with `rg`
8. `CHANGELOG.md` before assuming a feature is absent

## Architecture map

- Frontend: React UI for workspace, document, import, search, translation, and preview flows.
- API: FastAPI service for auth, document access, search, translation, and collaboration.
- Persistence: PostgreSQL with migrations and repository-style data access.
- Search: keyword/full-text search over document text, metadata, and translated variants.
- Vector store: Qdrant for embedding-backed retrieval where enabled.
- Workers: extraction, indexing, translation, sync, and artifact jobs.
- Local model runtime: optional Ollama integration.
- Observability: Docker logs, health checks, and Grafana.

## Working rules

- Prefer the live issue and current code over stale planning docs.
- Keep changes scoped and surgical.
- Verify with the narrowest useful command or manual flow.
- Report skipped checks honestly.
- Use `rg` before opening broad files.

## Handoff

End substantial work with changed files, verification, skipped checks, risks, and the exact next-agent prompt.
