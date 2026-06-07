# Phase 08f-4: Smoke Bootstrap Helper

## Goal

Factor the no-mock Compose smoke-test fixture setup into a reusable, bounded
helper that can run inside the API container without adding an unauthenticated
production endpoint.

## Branch

`developer/phase-08f-4-smoke-bootstrap-helper`

## Scope

- Add a Python helper that creates or reuses the smoke admin, group, folder
  source, source permission grant, and deterministic fixture document.
- Keep credentials in environment variables and never print passwords, tokens,
  or authorization headers.
- Validate the fixture path stays under the configured `FILES_ROOT` before
  writing the deterministic document.
- Update `scripts/smoke-test.sh` to invoke the helper instead of carrying inline
  database bootstrap code.
- Keep the smoke test's login, ingestion, search, preview, download, and
  frontend checks API-driven.

## Acceptance Criteria

- The helper is idempotent for repeated smoke-test runs against a kept Compose
  stack.
- The helper refuses fixture paths outside the Compose files volume root.
- The smoke script still accepts the existing environment overrides and flags.
- No unauthenticated bootstrap endpoint is introduced.
