# Phase 10a: Metrics Foundation

## Goal

Add the Prometheus metrics endpoint, HTTP request middleware, and request-ID middleware.
This is the prerequisite for all subsequent observability phases.

Design source: `docs/design/metrics-monitoring-spec.md` §Metrics Endpoint, §HTTP API
metric table, §Process And Runtime metric table.

## Phase Placement

Branch: `developer/phase-10a-metrics-foundation`

Status: Done.

## Current Baseline

- `GET /health` returns `{"status":"ok","service":"api"}` — unauthenticated and intentionally
  shallow.
- No `prometheus-client` dependency, no `/metrics` endpoint, no request-ID middleware.

## Dependencies

- Phase 01 FastAPI app skeleton (`src/services/api/main.py`).
- Phase 08f-1 production defaults (CORS, security hardening).

## Scope

### Prometheus Dependency And `/metrics` Endpoint

- Add `prometheus-client` to `pyproject.toml`.
- Expose `GET /metrics` returning Prometheus/OpenMetrics format.
- Bind `/metrics` to the internal Compose network only; document scrape config for operators
  in `docs/operations/production-compose.md`.
- Register standard process and Python GC metrics from the Prometheus client.
- Register `tomorrowland_build_info` gauge with `version`, `commit`, `environment` labels
  (value `1`, set at startup from env/config).

### HTTP Request Middleware

Add FastAPI middleware that records per-request:

- `tomorrowland_http_requests_total` counter — labels: `method`, `route` (template), `status_class`
  (2xx/4xx/5xx).
- `tomorrowland_http_request_duration_seconds` histogram — labels: `method`, `route`; buckets:
  `0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30`.
- `tomorrowland_http_exceptions_total` counter — labels: `route`, `error_type` (exception class
  name only).

### Request-ID Middleware

- Accept `X-Request-ID` from trusted callers; generate a UUID v4 when absent.
- Echo `X-Request-ID` on all responses.
- Make the request ID available to the logging context for later structured log phases.

### Safe Label Helpers

- Centralize route-template normalization: strip path parameters (`/documents/{documant_id}` not
  `/documents/abc123`).
- Labels must never include user IDs, document IDs, filenames, query text, source names,
  group names, exception messages, or file contents.
- Provide a helper function used by all metric instrumentation in subsequent phases.

## Implementation Notes

- Metrics must not block request handling; use non-blocking Prometheus client calls.
- Metrics must be safe when dependencies are missing or during startup.
- Do not move routes out of `src/services/api/main.py`.

## Validation

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src --strict
pytest tests/unit/test_metrics_foundation.py -q
pytest tests/unit/test_request_id_middleware.py -q
```

Verify Prometheus output format and that no label values contain raw IDs or content.

## Acceptance Criteria

- `GET /metrics` returns valid Prometheus text format.
- HTTP request counters and histograms increment for every API call.
- Route labels are normalized templates with no raw path parameters.
- `X-Request-ID` is echoed on responses and generated when absent.
- Standard process and GC metrics are present.
- No label value contains a user ID, document ID, query string, or file content.
