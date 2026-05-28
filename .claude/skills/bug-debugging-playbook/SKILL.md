---
name: bug-debugging-playbook
description: Use for Tomorrowland runtime failures, API 500s, Docker service problems, database errors, worker failures, Qdrant/Ollama/search issues, and frontend-backend integration bugs.
license: MIT
compatibility: claude-code, opencode
metadata:
  project: Tomorrowland
  audience: debugging-agents
---

# Bug Debugging Playbook

## Default output

For debugging tasks, produce:

```md
## Likely cause
## Fast checks
## Logs to inspect
## Minimal reproduction
## Fix options
## Verification
## Risk
```

## Debugging order

1. Identify the failing user-visible flow or command.
2. Capture the exact error, status code, stack trace, or log line.
3. Find the responsible service boundary.
4. Inspect the smallest relevant code path.
5. Propose the minimum fix.
6. Verify the original failure path.

## Common Tomorrowland areas

### API 500

Check route handler, auth dependency, DB query, request/response schema, migrations, and service logs.

### Docker service failure

Check `docker compose ps`, service logs, healthcheck configuration, env vars, ports, volumes, and dependency startup order.

### PostgreSQL error

Check migration state, SQLAlchemy query shape, bound parameters, UUID handling, transaction boundaries, and schema drift.

### Qdrant collection missing

Check startup bootstrap, collection creation logic, embedding dimension, worker order, and retry behavior.

### Ollama model error

Check model name, local availability, pull/load state, endpoint URL, timeout, and fallback handling.

### Meilisearch / full-text search issue

Check index name, document schema, metadata mapping, translated text fields, reindex path, and stale worker jobs.

### AI, RAG, or intelligence worker error

Check:
- `src/services/rag/service.py` — retrieval scope (`single_document`, `selected_documents`, `workspace`), hybrid search merge (deduplicates by `chunk_id`, not `document_id`), context budget
- `src/services/intelligence/worker.py` — summarize, entity extraction, auto-tag; failures must be logged and swallowed, not propagated (they must not block the ingestion pipeline)
- `src/services/rag/ollama_client.py` — model name (`model` property, not `_model`), timeout, streaming endpoint
- Chat session — TanStack Query seed-once pattern; check if `seededForSession` ref guard is resetting correctly on session change
- Qdrant payload fields — `chunk_id`, `document_id`, `group_id`, `source_id`, `title`, `source_language`
- Scope enforcement — BM25 applies post-filter via `_apply_scope_to_bm25()`; Qdrant enforces at query time via `must` filter

### Translation missing in frontend

Check worker completion, API response shape, cache invalidation, frontend query keys, state mapping, and rendering conditions.

## Guardrails

- Do not fix multiple unrelated bugs in one patch.
- Do not silence errors without preserving debuggability.
- Do not make broad infra changes before confirming the service boundary.
- Prefer observable fixes: logs, tests, and manual verification.
