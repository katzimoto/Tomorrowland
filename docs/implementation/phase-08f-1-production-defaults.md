# Phase 08f-1: Production Defaults And Security Guards

## Goal

Harden production-facing defaults before the no-mock Compose smoke test and
operator documentation are finalized.

## Branch

`developer/phase-08f-1-production-defaults`

## Scope

- Add explicit `CORS_ORIGINS` configuration if it is missing.
- Default production CORS to `http://localhost:8080`, not `*`.
- Wire FastAPI `CORSMiddleware` from the typed settings surface.
- Set Compose API environment values for CORS and production-safe defaults.
- Ensure Compose does not enable debug or reload behavior for the API service.
- Keep `JWT_SECRET` in `.env.example` as a clear placeholder such as
  `change-me-in-production`; never introduce a real secret.
- Verify the safe download guard in `src/services/api/main.py` is still used for
  protected file downloads and cannot be bypassed by direct path traversal.
- Confirm there is no unauthenticated bootstrap or admin endpoint in the
  production runtime.

## Out Of Scope

- Full `.env.example` prose annotations; that belongs to Phase 08f-2.
- Smoke-test scripting; that belongs to Phase 08f-3.
- Frontend route implementation.

## Implementation Notes

Prefer typed settings in `src/shared/config.py` over ad-hoc environment reads.
If CORS parsing accepts a comma-separated string, cover trimming and empty-value
behavior with focused tests.

Use the existing FastAPI application wiring in `src/services/api/main.py`; do
not move routes out of that file for this phase.

## Validation

```bash
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev mypy src --strict
uv run --extra dev pytest

docker compose config

git grep -n "CORSMiddleware\|CORS_ORIGINS\|JWT_SECRET\|RELOAD\|DEBUG"
git grep -n "safe_download\|download" src/services/api/main.py
```

## Acceptance Criteria

- API CORS behavior is configurable and production Compose does not default to
  wildcard origins.
- Debug and reload flags are false or absent in Compose API configuration.
- Tracked secrets remain placeholders only.
- Download path validation remains in place and covered by the existing or new
  tests.
- Any security audit findings are fixed or explicitly documented for the next
  sub-phase.

Stop for Reviewer-agent review.
