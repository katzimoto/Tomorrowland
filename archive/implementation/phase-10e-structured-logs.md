# Phase 10e: Structured Logs And Tracing Hooks

## Goal

Convert application logs to structured JSON records with a consistent schema, and add
optional OpenTelemetry tracing hooks for future distributed tracing support.

Design source: `docs/design/metrics-monitoring-spec.md` §Structured Logs, §Tracing.

## Phase Placement

Branch: `developer/phase-10e-structured-logs`

Status: Planned (can proceed independently of Phase 10d; requires Phase 10a request-ID
middleware for `request_id` log field).

## Current Baseline

- Application failures are emitted through standard Python loggers in pipeline, intelligence,
  translation, and Ollama client code.
- Compose uses the Docker `json-file` logging driver; log lines are currently plain text.
- No request-ID correlation in log records (added in Phase 10a middleware).

## Dependencies

- Phase 10a request-ID middleware (provides `request_id` per request).
- `src/shared/logging.py` — existing structured logging module to extend.

## Scope

### JSON Log Schema

Convert all application log records to JSON with these fields:

| Field | Required | Notes |
|---|---|---|
| `timestamp` | Yes | RFC 3339 UTC. |
| `level` | Yes | `debug`, `info`, `warning`, `error`, `critical`. |
| `logger` | Yes | Python logger name. |
| `message` | Yes | Human-readable event summary; no secrets or document content. |
| `request_id` | HTTP only | From Phase 10a middleware context. |
| `route` | HTTP only | Route template (not raw path with IDs). |
| `method` | HTTP only | HTTP method. |
| `status_code` | HTTP only | Response code. |
| `duration_ms` | HTTP only | Request latency. |
| `component` | Recommended | `api`, `pipeline`, `search`, `translation`, `intelligence`, etc. |
| `outcome` | Recommended | `success`, `failure`, `skipped`, `retry`, `dlq`. |
| `error_type` | Errors only | Exception class name only; no message if it may contain user data. |

### Docker `json-file` Compatibility

- JSON log records must remain parseable by Docker's `json-file` driver.
- The Docker log wrapper wraps each record in `{"log": "...", "stream": "...", "time": "..."}`.
  The application log line inside `log` must itself be valid JSON.
- Preserve `docker compose logs -f api` usability.

### No Secrets Or Content In Logs

- Log messages must never include: JWT tokens, LDAP passwords, raw document text, extracted
  chunks, file contents, user-provided query strings, or API keys.
- `error_type` may include exception class names only; exception messages should be logged
  only after verifying they cannot contain user data.

### Optional OpenTelemetry Hooks

After logs are stable, add optional OpenTelemetry span creation for:

- HTTP request handling (route template as span name).
- Database transactions.
- Meilisearch and Qdrant calls.
- LibreTranslate calls.
- Ollama calls.
- Pipeline stages (extract, translate, chunk, embed, index, intelligence).

Hooks must be no-ops when no OpenTelemetry exporter is configured. Do not introduce a remote
collector by default.

## Implementation Notes

- Extend `src/shared/logging.py`; do not replace it wholesale.
- Use a Python logging formatter rather than monkey-patching individual log call sites.
- Request context (`request_id`, `route`, `method`) should flow through context variables
  set by Phase 10a middleware.
- All structured log field values must pass through the same safe label helper used by
  Phase 10a metrics to avoid content leakage.

## Validation

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src --strict
pytest tests/unit/test_structured_logging.py -q
```

Tests must verify:

- Log records are valid JSON.
- `request_id` appears in HTTP-triggered log records.
- `error_type` is the exception class name only (not the message) for known-sensitive paths.
- No token, password, or document-content field appears in sample log records.

## Acceptance Criteria

- All application log records are valid JSON parseable by the Docker `json-file` driver.
- HTTP log records include `request_id`, `route`, `method`, `status_code`, `duration_ms`.
- No log record contains a JWT, LDAP credential, raw document text, or extracted chunk.
- OpenTelemetry hooks are present but no-op when no exporter is configured.
- `docker compose logs -f api` remains usable; no line-wrapping or encoding regression.
