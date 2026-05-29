# Local Demo

Use this guide for local evaluation and demos after starting the Compose
runtime. For full development setup, see `local-dev.md`.

## Prerequisites

- Docker Engine and Docker Compose plugin.
- The Compose runtime is running (see `local-dev.md`).

## Quick document-flow smoke test

After `docker compose up --build -d` succeeds, verify the services are healthy:

```bash
bash scripts/dev/smoke_document_flow.sh
```

Example output:

```
==> Starting document-flow smoke test (mode=local)
  [INFO] API: http://localhost:8000
  [INFO] Frontend: not configured (set FRONTEND_URL to check)
  [INFO] Result file: tmp/smoke-document-flow-result.json
==> Stage: check_dependencies
  [PASS] check_dependencies
==> Stage: api_health
  [PASS] api_health

==> Document-flow smoke test PASSED (3s)
```

To include frontend health:

```bash
FRONTEND_URL=http://localhost:8080 bash scripts/dev/smoke_document_flow.sh
```

## CI mode

For CI environments, use `SMOKE_MODE=ci` to force hard failures on any stage:

```bash
SMOKE_MODE=ci FRONTEND_URL=http://localhost:8080 \
  bash scripts/dev/smoke_document_flow.sh
```

Results are written to `tmp/smoke-document-flow-result.json` by default:

```json
{
  "smoke": "document-flow",
  "status": "pass",
  "stage": "final",
  "message": "All stages passed",
  "elapsed_seconds": 3,
  "timestamp": "2026-05-29T..."
}
```

## With credentials (recommended)

Set admin credentials to enable auth and search checks:

```bash
SMOKE_ADMIN_EMAIL=admin@example.com SMOKE_ADMIN_PASSWORD=your-password \
  bash scripts/dev/smoke_document_flow.sh
```

Example output with all five stages:

```
==> Starting document-flow smoke test (mode=local)
  [INFO] API: http://localhost:8000
  [INFO] Frontend: not configured (set FRONTEND_URL to check)
  [INFO] Result file: tmp/smoke-document-flow-result.json
==> Stage: check_dependencies
  [PASS] check_dependencies
==> Stage: api_health
  [PASS] api_health
==> Stage: frontend_health
  [SKIP] Frontend health check skipped (FRONTEND_URL not set)
==> Stage: auth_login
  [INFO] Logging in as admin@example.com
  [PASS] Obtained access token (XXX chars)
  [PASS] auth_login
==> Stage: doc_search
  [INFO] Searching for 'tomorrowland'
  [PASS] Search endpoint is accessible and returns valid JSON
==> Stage: doc_preview
  [INFO] Fetching preview for doc-abc-123
  [INFO] Preview snippet (42 chars) retrieved successfully
  [PASS] Preview endpoint returns valid JSON with snippet
  [PASS] doc_preview
==> Stage: doc_download
  [INFO] Downloading document doc-abc-123
  [INFO] Downloaded 1024 bytes
  [PASS] Download endpoint returns file content
  [PASS] doc_download

==> Document-flow smoke test PASSED (5s)
```

## What this covers

- API availability (`GET /health`)
- Frontend availability (`GET /health`)
- Dependency presence (curl, python3)
- Authentication flow (`POST /auth/login`)
- Authenticated search access (`POST /search`)
- Document preview (`GET /preview/{id}`)
- Document download (`GET /download/{id}`)

Preview and download stages gracefully skip when no documents exist.
Future slices of issue #541 will add document ingestion and
fixture setup.
