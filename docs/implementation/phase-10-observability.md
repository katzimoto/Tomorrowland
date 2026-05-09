# Phase 10: Metrics And Monitoring

## Goal

Implement local-first metrics and monitoring for Neverland using the design in
`docs/design/metrics-monitoring-spec.md`, while preserving the current production
Compose behavior and the minimal public health endpoint.

## Current Baseline

- The API exposes `GET /health` with a minimal liveness payload.
- `GET /admin/health` is admin-gated but shallow.
- Docker Compose health checks cover API, frontend, PostgreSQL, Redpanda,
  Elasticsearch, Qdrant, LibreTranslate, and Ollama.
- Compose services use Docker `json-file` logs.
- Python service classes log failures through standard loggers.
- There is no metrics endpoint, Prometheus client dependency, request ID
  middleware, structured JSON logging, trace propagation, Prometheus/Grafana
  service, or long-running worker container.

## Recommended Branch

`developer/phase-10-observability`

## Scope

### Phase 10a — Metrics Foundation

- Add a Prometheus/OpenMetrics dependency.
- Add `GET /metrics` for Prometheus-format application metrics.
- Add HTTP middleware that records:
  - request totals by method, route template, and status class;
  - request duration histograms by method and route template;
  - unhandled exception totals by route template and exception type.
- Add request ID middleware:
  - accept `X-Request-ID` from trusted callers;
  - generate a UUID when missing;
  - echo `X-Request-ID` on responses;
  - make it available to logs and future traces.
- Centralize metric label helpers so route labels never include raw IDs,
  filenames, query text, document content, user IDs, group names, or secrets.
- Document how operators scrape `/metrics` from the private Compose network.

### Phase 10b — Domain Metrics

Instrument existing service paths with low-cardinality counters and histograms:

- authentication attempts and authorization denials;
- admin audit actions;
- source sync attempts by connector type;
- pipeline stages for extraction, translation, chunking, indexing, intelligence,
  subscriptions, and DLQ routing;
- search and backend latency for Elasticsearch and Qdrant;
- preview and download outcomes;
- manual and automatic translation;
- Ollama-backed summarization, entity extraction, tagging, and RAG Q&A;
- comments, annotations, subscriptions, notifications, related documents, and
  expertise endpoints.

### Phase 10c — Admin Readiness

- Add `GET /admin/readiness` guarded by `Depends(current_user)` and
  `require_admin(user)`.
- Probe PostgreSQL, Elasticsearch, Qdrant, LibreTranslate, and Ollama with short
  timeouts.
- Cache probe results briefly to avoid dashboard-induced load.
- Return `ok`, `degraded`, or `down` with per-dependency latency and status.
- Export `neverland_dependency_up` and dependency latency metrics.

### Phase 10d — Optional Monitoring Compose Profile

- Add an optional `monitoring` Compose profile with Prometheus and Grafana.
- Provision Prometheus scrape config for `api:8000/metrics`.
- Provision starter Grafana dashboards for executive health, API/UX, ingestion,
  search/RAG, and infrastructure.
- Document monitoring startup, reset, backup relevance, and troubleshooting in
  `docs/operations/production-compose.md`.
- Keep monitoring volumes separate from product source-of-truth data.

### Phase 10e — Structured Logs And Tracing Hooks

- Convert app logs to JSON with timestamp, level, logger, message, request ID,
  route template, method, status code, duration, component, outcome, and safe
  error type.
- Preserve compatibility with Docker `json-file` collection.
- Add optional OpenTelemetry hooks only after metrics and logs are stable.
- Do not introduce a remote collector by default.

### Phase 10f — Worker Observability Follow-Up

When long-running worker entrypoints exist, reuse the same service metrics and
add:

- worker heartbeat gauges;
- Kafka consumer lag gauges;
- per-topic processing counters;
- retry/backoff metrics;
- worker-specific dashboards and alerts.

## Out Of Scope

- Sending telemetry to external SaaS products.
- Adding high-cardinality or content-bearing labels.
- Replacing existing audit logs with metrics.
- Moving routes out of `src/services/api/main.py`.
- Introducing long-running worker containers before a worker entrypoint exists.
- Making public `/health` perform dependency checks.

## Validation

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src --strict
pytest tests/unit/test_health.py -q
pytest tests/unit/test_observability.py -q
pytest tests/integration/test_observability.py -q
docker compose config
docker compose --profile monitoring config
```

If a phase only changes documentation, use:

```bash
git diff --check
python - <<'PY'
from pathlib import Path
for path in [
    Path('docs/design/metrics-monitoring-spec.md'),
    Path('docs/implementation/phase-10-observability.md'),
    Path('docs/implementation/README.md'),
    Path('docs/README.md'),
    Path('CHANGELOG.md'),
]:
    text = path.read_text()
    assert text.endswith('\n'), path
PY
```

## Acceptance Criteria

- Operators can scrape application metrics locally without exposing document
  content, identities, secrets, or unbounded labels.
- Public liveness remains cheap and unauthenticated.
- Admin readiness explains core versus optional dependency degradation.
- Dashboards cover API health, search latency, Q&A latency, ingestion failures,
  DLQ state, and dependency health.
- Alerts map to sustained operator-actionable failures.
- The implementation remains aligned with the current synchronous service-class
  pipeline and can be reused by future long-running worker containers.
