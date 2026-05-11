# Phase 10f: Worker Observability

## Goal

When long-running worker entrypoints exist, reuse the Phase 10a–10b service metrics and add
worker-specific gauges for heartbeats, consumer lag, and retry/backoff behavior.

Design source: `docs/design/metrics-monitoring-spec.md` §Dependency And Queue Health
(`tomorrowland_kafka_consumer_lag`, `tomorrowland_worker_heartbeat_timestamp_seconds`).

## Phase Placement

Branch: `developer/phase-10f-worker-observability`

Status: **Deferred** — implement only when long-running worker entrypoints are introduced.
Do not start this phase while ingestion, indexing, translation, and intelligence work run
through direct API-triggered service classes.

## Current Baseline

- Pipeline, intelligence, translation, and search indexing run through synchronous
  service-class calls inside FastAPI request handlers.
- No dedicated worker process or entrypoint exists.
- Consumer-lag and heartbeat metrics are not meaningful without a running consumer.

## Dependencies

- Phase 10a metrics foundation and safe label helpers.
- Phase 10b domain metrics (reused by worker service paths).
- A long-running worker entrypoint (future phase).
- Kafka consumer implementation from Phase 09a or future worker phase.

## Scope

### Worker Heartbeat

- `tomorrowland_worker_heartbeat_timestamp_seconds` gauge — label: `worker` (worker name/type).
- Each worker updates its heartbeat gauge once per processing loop or at a configurable
  interval.
- A flatlined heartbeat (no update for N seconds) should trigger an alert via Grafana
  or Alertmanager.

### Kafka Consumer Lag

- `tomorrowland_kafka_consumer_lag` gauge — labels: `topic`, `consumer_group`.
- Expose lag from the consumer's committed offset vs. the partition high-water mark.
- Update at each poll cycle.

### Per-Topic Processing Counters

- `tomorrowland_kafka_messages_processed_total` counter — labels: `topic`, `outcome`.
- `tomorrowland_kafka_processing_duration_seconds` histogram — label: `topic`.

### Retry And Backoff Metrics

- `tomorrowland_worker_retries_total` counter — labels: `worker`, `stage`, `reason`.
- `tomorrowland_worker_backoff_duration_seconds` histogram — label: `worker`.

### Worker Dashboards

Extend Phase 10d Grafana dashboards with a **Worker Observability** panel group:

- Heartbeat status per worker (last seen timestamp, gap alert).
- Consumer lag by topic and consumer group.
- Message processing rate and failure rate.
- Retry/backoff frequency.

## Implementation Notes

- Reuse Phase 10b service metrics for pipeline stage instrumentation inside workers.
- Worker metric registration should use the same metric registry as the API; avoid
  duplicate metric names.
- Worker heartbeat interval and lag scrape interval should be configurable.

## Validation

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src --strict
pytest tests/unit/test_worker_observability.py -q
```

## Acceptance Criteria

- Worker heartbeat gauge updates on each processing loop iteration.
- Consumer lag gauge reflects the actual committed vs. high-water mark offset.
- Processing, retry, and backoff counters increment on the expected paths.
- Worker dashboard panels render without errors.
- All Phase 10a–10e metric names remain unchanged.
