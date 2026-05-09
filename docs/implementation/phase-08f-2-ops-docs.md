# Phase 08f-2: Production Operations Documentation

## Goal

Make local production operation understandable without reading the source code.
This phase documents the hardened configuration surface established by Phase
08f-1.

## Branch

`developer/phase-08f-2-ops-docs`

## Recommended Prerequisite

Phase 08f-1 merged, or the agent has verified the latest names and defaults for
CORS, auth, service URLs, and Compose runtime flags before editing docs.

## Scope

- Annotate every variable in `.env.example` with a one-line description.
- Mark required variables explicitly.
- Distinguish optional variables, feature flags, and local-development defaults.
- Use placeholders only for passwords, tokens, and secrets.
- Expand `docs/operations/production-compose.md` with:
  - first-run setup;
  - startup and shutdown commands;
  - reset and clean-volume migration guidance;
  - backup and restore guidance for PostgreSQL, file storage, Elasticsearch,
    and Qdrant data that must stay consistent;
  - common troubleshooting steps;
  - current worker-container status;
  - expected health endpoints and service ports.
- Remove stale references that say the no-mock smoke test lands in an already
  completed phase.

## Troubleshooting Topics To Cover

- Migration failures: inspect `migrate` logs and re-run
  `docker compose run --rm migrate`.
- Elasticsearch index startup: check API startup logs and index creation.
- Qdrant startup races: explain retry behavior or documented manual restart.
- Ollama model availability: pull the configured model manually when needed.
- Authentication failures caused by unchanged placeholder secrets or mismatched
  LDAP settings.
- Frontend/API proxy issues between `http://localhost:8080` and the API service.

## Out Of Scope

- Implementing new configuration options.
- Adding the smoke-test script.
- Adding long-running worker containers before an entrypoint exists.

## Validation

```bash
git diff --check
python - <<'PY'
from pathlib import Path
for path in [Path('.env.example'), Path('docs/operations/production-compose.md')]:
    text = path.read_text()
    assert text.endswith('\n'), path
PY

docker compose config
```

If `docker compose config` cannot run in the environment, include the exact
environment limitation in the PR notes.

## Acceptance Criteria

- Operators can identify required values in `.env.example` without opening
  application code.
- Production docs explain start, stop, reset, backup, restore, health checks,
  and troubleshooting.
- Docs reflect the current architecture: synchronous API-triggered pipeline work
  and no long-running worker containers yet.
- No real secrets appear in docs or examples.

Stop for Reviewer-agent review.
