# Phase 10: Metrics And Monitoring

## Goal

Implement local-first metrics and monitoring for Tomorrowland using the design in
`docs/design/metrics-monitoring-spec.md`, while preserving the current production Compose
behavior and the minimal public health endpoint.

Phase 10 is split into six independent sub-plans. Each can be developed and reviewed on its
own branch, in dependency order.

## Sub-Plans

| Sub-Phase | Plan | Purpose | Status |
|---|---|---|---|
| 10a | `phase-10a-metrics-foundation.md` | Prometheus `/metrics`, HTTP middleware, request-ID | Done |
| 10b | `phase-10b-domain-metrics.md` | Instrument auth, pipeline, search, RAG, collaboration | Planned (needs 10a) |
| 10c | `phase-10c-admin-readiness.md` | Admin readiness endpoint with dependency probes | Planned (needs 10a) |
| 10d | `phase-10d-monitoring-compose.md` | Optional Prometheus + Grafana Compose profile | Planned (needs 10a, 10b) |
| 10e | `phase-10e-structured-logs.md` | JSON structured logs and OpenTelemetry hooks | Planned (needs 10a) |
| 10f | `phase-10f-worker-observability.md` | Worker heartbeats and consumer lag | Deferred (needs workers) |

## Design Reference

All metric names, label schemas, dashboard designs, and alerting rules are defined in
`docs/design/metrics-monitoring-spec.md`. Do not introduce new metric names without
updating that spec first.

## Current Baseline

- `GET /health` returns `{"status":"ok","service":"api"}` — unauthenticated and shallow.
- `GET /admin/health` is admin-gated but shallow.
- Docker Compose health checks cover API, frontend, PostgreSQL, Kafka, Elasticsearch,
  Qdrant, LibreTranslate, and Ollama.
- No metrics endpoint, Prometheus client, request-ID middleware, JSON log formatter, or
  monitoring Compose profile exists yet.

## Out Of Scope (All Sub-Phases)

- Sending telemetry to external SaaS products.
- High-cardinality or content-bearing metric labels.
- Replacing existing audit logs with metrics.
- Moving routes out of `src/services/api/main.py`.
- Making public `GET /health` perform dependency checks.
- Introducing long-running worker containers before a worker entrypoint phase exists.

## Validation (Docs-Only Changes)

If a phase only changes documentation:

```bash
git diff --check
python3 - <<'PY'
from pathlib import Path
for path in [
    Path("docs/design/metrics-monitoring-spec.md"),
    Path("docs/implementation/phase-10-observability.md"),
    Path("docs/implementation/README.md"),
    Path("docs/README.md"),
    Path("CHANGELOG.md"),
]:
    text = path.read_text()
    assert text.endswith("\n"), path
PY
```
