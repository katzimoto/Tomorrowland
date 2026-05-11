# Phase 10c: Admin Readiness Endpoint

## Goal

Add an admin-only readiness endpoint that probes all core and optional dependencies and
returns a stable health shape with per-dependency latency and status.

Design source: `docs/design/metrics-monitoring-spec.md` §Admin Readiness.

## Phase Placement

Branch: `developer/phase-10c-admin-readiness`

Status: Planned (requires Phase 10a for `tomorrowland_dependency_up` gauge export).

## Current Baseline

- `GET /admin/health` exists but is shallow (`{"status":"ok"}`).
- `GET /health` is intentionally unauthenticated and must remain shallow (process liveness
  only; no dependency probes).

## Dependencies

- Phase 02 auth guards (`Depends(current_user)`, `require_admin`).
- Phase 10a metrics foundation for exporting `tomorrowland_dependency_up` gauges.

## Scope

### `GET /admin/readiness`

Guarded by `Depends(current_user)` and `require_admin(user)`.

Response shape:

```json
{
  "status": "ok|degraded|down",
  "service": "api",
  "checked_at": "<RFC 3339 UTC timestamp>",
  "dependencies": {
    "postgres":        {"status": "ok|degraded|down", "latency_ms": 7},
    "elasticsearch":   {"status": "ok|degraded|down", "latency_ms": 21},
    "qdrant":          {"status": "ok|degraded|down", "latency_ms": 13},
    "libretranslate":  {"status": "ok|degraded|down", "latency_ms": 1000},
    "ollama":          {"status": "ok|degraded|down", "latency_ms": 45}
  }
}
```

Status semantics:

- `ok`: all required dependencies for enabled features are available.
- `degraded`: core API works but an optional/feature-specific dependency is unavailable
  (e.g., Ollama when intelligence is enabled).
- `down`: a core dependency required for normal operation is unavailable (e.g., PostgreSQL).

### Probe Implementation

Each dependency probe must:

- Use a short timeout (≤ 2 s recommended).
- Return latency in milliseconds.
- Not affect the public `/health` endpoint behavior.
- Cache results for 10–30 seconds to prevent dashboard-induced load on dependencies.

### Dependency Gauge Export

Export `tomorrowland_dependency_up{dependency="<name>"}` gauge (value `1` or `0`) and
`tomorrowland_dependency_latency_seconds` histogram from the cached probe results.

## Implementation Notes

- Keep `GET /health` unchanged: shallow, unauthenticated, no dependency calls.
- The readiness endpoint may be deprecated in favor of updating `GET /admin/health`; decide
  before coding and record in `docs/review/spec-gaps.md`.
- Probe timeouts must not cascade into API request timeouts.

## Validation

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src --strict
pytest tests/unit/test_admin_readiness.py -q
```

Tests must mock each dependency and verify `ok`, `degraded`, and `down` responses including
the caching behavior.

## Acceptance Criteria

- `GET /admin/readiness` is accessible to admins only.
- Response lists all five dependencies with status and latency.
- Overall `status` is `down` when PostgreSQL is unreachable, `degraded` when only Ollama
  or LibreTranslate is unreachable.
- Results are cached; rapid repeated calls do not generate repeated probe traffic.
- `tomorrowland_dependency_up` gauges reflect the most recent cached probe result.
- `GET /health` behavior is unchanged.
