# Phase 10d: Optional Monitoring Compose Profile

## Goal

Add an optional `monitoring` Docker Compose profile that provides local Prometheus and
Grafana with provisioned scrape config and starter dashboards, without affecting the default
product Compose stack.

Design source: `docs/design/metrics-monitoring-spec.md` §Dashboards, §Alerting Rules,
§Docker Compose Monitoring Stack.

## Phase Placement

Branch: `developer/phase-10d-monitoring-compose`

Status: Planned (requires Phase 10a `/metrics` endpoint and Phase 10b domain metrics).

## Current Baseline

- Compose services use Docker `json-file` logging.
- No Prometheus, Grafana, or Alertmanager services exist.
- No monitoring volumes are defined.

## Dependencies

- Phase 10a `GET /metrics` endpoint with Prometheus-format output.
- Phase 10b domain metrics for meaningful dashboard panels.
- Phase 10c admin readiness for dependency health panels (optional but recommended first).

## Scope

### Compose Profile

Add an optional `monitoring` profile to `docker-compose.yml` or a separate
`docker-compose.monitoring.yml` overlay. Starting the monitoring stack must not be required
for the default product startup.

### Prometheus Service

- Scrape `api:8000/metrics` on the internal Compose network.
- Scrape interval: 15 s default; configurable.
- Retention: 15 days default.
- Provision scrape config from a checked-in `prometheus.yml`.
- Do not expose Prometheus publicly; bind to the internal network only.

### Grafana Service

- Provision the Prometheus data source automatically.
- Provision starter dashboards from checked-in JSON files:
  - **Executive Health**: API up/error rate, search p50/p95 vs. 300 ms target, Q&A p50/p95
    vs. 10 s target, ingest throughput/failures, DLQ pending count, dependency status.
  - **API And UX**: request rate/error rate/latency by route, auth failures, authz denials,
    preview/download success rates.
  - **Ingestion And Indexing**: sync attempts/outcomes by connector type, pipeline stage
    durations, DLQ trend.
  - **Search And RAG**: hybrid search latency, backend split, Q&A retrieval/generation
    latency, Ollama error rate.
  - **Infrastructure**: PostgreSQL/Meilisearch/Qdrant/LibreTranslate/Ollama/Kafka health,
    Meilisearch index health, Qdrant collection size.

### Alertmanager (Optional)

- Include an optional Alertmanager configuration example for email or internal chat.
- Not required for the base monitoring profile.

### Alerting Rules

Provision Prometheus alerting rules from `docs/design/metrics-monitoring-spec.md`
§Alerting Rules:

| Alert | Severity | Condition |
|---|---|---|
| API down | Critical | Scrape fails or `/health` fails for 2 min |
| PostgreSQL unavailable | Critical | `dependency_up{dependency="postgres"} == 0` for 2 min |
| Search unavailable | Critical | Meilisearch or Qdrant down for 5 min |
| High API error rate | Warning | 5xx rate > 2% for 10 min |
| Search SLO breach | Warning | p95 search > 300 ms for 15 min |
| Q&A SLO breach | Warning | p95 RAG > 10 s for 15 min |
| DLQ growing | Warning | Pending DLQ increasing for 15 min |
| Disk pressure | Critical | Any durable volume < 10% free for 5 min |
| Ollama degraded | Warning | Ollama down with intelligence/RAG enabled for 10 min |

### Documentation

Update `docs/operations/production-compose.md`:

- Add monitoring profile startup instructions: `docker compose --profile monitoring up`.
- Document monitoring volume reset procedure (separate from product data volumes).
- Note that losing Prometheus/Grafana data does not affect product documents or permissions.

## Implementation Notes

- Keep monitoring volumes (`prometheus_data`, `grafana_data`) separate from product volumes
  (`postgres_data`, `meilisearch_data`, `qdrant_data`, `files_data`).
- Dashboard JSON files must not contain hardcoded credentials or secret examples.
- `docker compose config` must pass without the monitoring profile.
- `docker compose --profile monitoring config` must also pass.

## Validation

```bash
docker compose config
docker compose --profile monitoring config
# Lint dashboard JSON files
python3 -c "import json, pathlib; [json.loads(p.read_text()) for p in pathlib.Path('docker/grafana/dashboards').glob('*.json')]"
```

## Acceptance Criteria

- Default `docker compose up` starts the product without Prometheus or Grafana.
- `docker compose --profile monitoring up` adds Prometheus and Grafana on the internal
  network.
- Grafana loads provisioned dashboards without manual configuration.
- All five starter dashboards render without errors on a running stack.
- Alert rules are syntactically valid Prometheus YAML.
- Monitoring volumes are listed in the backup guide as operational state, not product data.
