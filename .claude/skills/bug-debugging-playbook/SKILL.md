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

### Search or Meilisearch/Elasticsearch issue

Check index name, document schema, metadata mapping, translated text fields, reindex path, and stale worker jobs.

### Translation missing in frontend

Check worker completion, API response shape, cache invalidation, frontend query keys, state mapping, and rendering conditions.

## Guardrails

- Do not fix multiple unrelated bugs in one patch.
- Do not silence errors without preserving debuggability.
- Do not make broad infra changes before confirming the service boundary.
- Prefer observable fixes: logs, tests, and manual verification.
