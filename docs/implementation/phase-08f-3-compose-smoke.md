# Phase 08f-3: No-Mock Compose Smoke Test

## Goal

Add an operator-friendly smoke test that proves the production Compose stack can
run the main product path without mocked services.

## Branch

`developer/phase-08f-3-compose-smoke`

## Recommended Prerequisites

- Phase 08f-1 merged so production defaults are stable.
- Phase 08f-2 merged so the script follows documented setup and reset behavior.

## New File

```text
scripts/smoke-test.sh
```

## Smoke Flow

The script should be safe to run from the repository root and should fail fast
with clear diagnostics.

1. Start the stack with `docker compose up --build -d` unless an explicit flag
   tells the script to use an already running stack.
2. Poll `GET /health` until the API is ready or a bounded timeout expires.
3. Seed or reuse a smoke admin user, group, and source fixture using documented
   admin APIs or a narrow helper if one already exists.
4. Place a deterministic fixture document under the Compose-mounted `/data`
   path used by the source.
5. Log in and capture an auth token without printing secrets.
6. Create or reuse a folder source that points at the fixture path.
7. Grant the smoke user or group access to the source.
8. Trigger synchronous ingestion.
9. Poll search until the fixture document appears.
10. Fetch document preview content.
11. Download the document and verify the response is non-empty.
12. Check that the frontend root on `http://localhost:8080` responds.
13. Tear down with `docker compose down -v` by default, while offering a
    documented keep-running option for debugging.

## Script Requirements

- Use Bash strict mode (`set -euo pipefail`).
- Avoid printing tokens, passwords, or full authorization headers.
- Use bounded polling loops with useful timeout messages.
- Make hostnames, ports, credentials, and fixture names configurable through
  environment variables with safe defaults.
- Clean up temporary local files.
- Preserve Compose logs on failure or print the exact command operators should
  run to inspect them.
- Prefer `curl` and `python` standard-library JSON parsing over new project
  dependencies.

## Optional Helper Split

If smoke fixture setup requires a new reusable bootstrap endpoint or admin CLI,
stop and propose an 08f-4 helper split. Do not add an unauthenticated production
bootstrap endpoint as part of this phase.

## Validation

```bash
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev mypy src --strict
uv run --extra dev pytest

npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build

docker compose config
bash scripts/smoke-test.sh
```

## Audits

Run or document environment limitations for:

```bash
uv run pip-audit
npm --prefix frontend audit
```

Run a tracked-secret spot check and investigate any non-test hits:

```bash
git grep -n -E "(password|secret|token|api_key)\s*=\s*['\"][^$<{]" -- '*.py' '*.ts' '*.tsx'
```

## Acceptance Criteria

- The smoke test can run against a clean Compose stack from the repository root.
- The script verifies authentication, source setup, ingestion, search, preview,
  download, and frontend reachability.
- Failure output identifies the failed step and how to inspect logs.
- The default path tears down Compose volumes so repeated runs start cleanly.
- No unauthenticated bootstrap/admin endpoint is introduced.
- Audit results are clean or accepted exceptions are documented with
  justification.

Stop for Reviewer-agent review.
