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
7. `graphify query "<question>"` for targeted code discovery when `graphify-out/` exists
8. Source and test files found with `rg`
9. `CHANGELOG.md` before assuming a feature is absent

## Architecture map

- Frontend: React 19 + TypeScript + Vite UI (TanStack Router, TanStack Query v5) for workspace, document, import, search, translation, chat, and preview flows.
- API: FastAPI service organized in `src/services/api/routers/` by domain (auth, documents, search, translation, chat, intelligence, annotations, alerts, etc.).
- Persistence: PostgreSQL with Alembic migrations; repository-style data access; SQLite used for integration tests via `migrated_engine` fixture.
- Search: Meilisearch for full-text / BM25 keyword search over document text, metadata, and translated variants.
- Vector store: Qdrant for embedding-backed vector retrieval; hybrid search merges Qdrant + Meilisearch results, deduplicating by `chunk_id`.
- Extraction pipeline: multi-phase MIME detection (Magika ML layer-1, python-magic fallback), text extraction, charset detection, language detection, OCR, and attachment handling. `ExtractionResult` is the uniform envelope.
- Workers: parse worker, slow worker, vector worker (extraction, indexing, translation), intelligence worker (summarize, entity extraction, auto-tag), sync, and artifact jobs.
- Document chat / RAG: session-based chat using hybrid retrieval (Qdrant + Meilisearch), Ollama generation, streaming citations, scope enforcement (`single_document`, `selected_documents`, `workspace`).
- Intelligence worker: async per-document summarization, entity extraction, and auto-tagging — failures are logged and swallowed, never propagate to block ingestion.
- Local model runtime: Ollama integration for LLM inference (`ollama-llm`) and embeddings (`ollama-embed`), separate Compose services since v0.2.0.
- Observability: Docker logs, health checks, Grafana (optional monitoring profile).

## Working rules

- Prefer the live issue and current code over stale planning docs.
- Keep changes scoped and surgical.
- Verify with the narrowest useful command or manual flow.
- Report skipped checks honestly.
- Use `rg` before opening broad files.

## Handoff

End substantial work with changed files, verification, skipped checks, risks, and the exact next-agent prompt.
