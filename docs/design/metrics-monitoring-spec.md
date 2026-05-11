# Metrics And Monitoring Design

## Goal

Provide an observability design for Tomorrowland that matches the current local-first
architecture while leaving room for later dedicated workers and larger
multi-host deployments. The design covers health checks, metrics, structured
logs, traces, dashboards, and alerting without changing the canonical product
specification.

## Current Code Baseline

The current implementation has these observability primitives:

- `GET /health` returns a minimal API liveness payload: `{"status":"ok","service":"api"}`.
- `GET /admin/health` is admin-gated and currently returns `{"status":"ok"}`.
- Docker Compose defines health checks for the API, frontend, PostgreSQL,
  Redpanda, Elasticsearch, Qdrant, LibreTranslate, and Ollama.
- Compose uses the Docker `json-file` logging driver for application and
  infrastructure services.
- Application failures are mostly emitted through standard Python loggers in
  pipeline, intelligence, translation, and Ollama client code.
- There is no metrics endpoint, Prometheus client dependency, trace propagation,
  log correlation middleware, Prometheus/Grafana service, or dedicated worker
  container yet.

Because ingestion, indexing, translation, and intelligence work currently run
through direct API-triggered service classes, worker metrics in this design are
instrumented in service methods first and later reused by long-running worker
entrypoints when those entrypoints exist.

## Design Principles

- **Local-first:** default monitoring stack runs locally through Docker Compose
  and does not require SaaS collectors.
- **No document-content leakage:** labels, log fields, traces, and exemplars must
  never include raw document text, prompts, extracted chunks, passwords, JWTs,
  LDAP credentials, API tokens, or file contents.
- **Low cardinality:** labels may include route templates, status classes,
  connector type, source type, task type, queue/topic, backend name, and outcome;
  labels must not include user IDs, document IDs, filenames, query text, source
  names, group names, exception messages, or free-form URLs.
- **Admin-safe visibility:** public health stays minimal. Detailed readiness,
  metrics, and operational state are either bound to the private Compose network
  or protected by admin/API gateway controls.
- **Progressive rollout:** add app-level instrumentation before introducing a
  full monitoring stack; every phase remains useful in the current codebase.
- **Actionable alerts:** alert only on symptoms that need operator action, not
  every transient dependency warning.

## Surfaces

### Public Liveness

`GET /health` remains unauthenticated and intentionally shallow. It should only
answer whether the API process can serve HTTP. It must not perform database,
search, vector, translation, or model calls because Compose health checks depend
on it for process restart decisions.

Recommended response shape:

```json
{"status":"ok","service":"api"}
```

### Admin Readiness

Add a detailed admin-only readiness endpoint after the metrics foundation lands:

```text
GET /admin/readiness
```

The endpoint should check dependencies with short timeouts and return a stable
JSON shape:

```json
{
  "status": "ok|degraded|down",
  "service": "api",
  "checked_at": "2026-05-09T00:00:00Z",
  "dependencies": {
    "postgres": {"status": "ok", "latency_ms": 7},
    "elasticsearch": {"status": "ok", "latency_ms": 21},
    "qdrant": {"status": "ok", "latency_ms": 13},
    "libretranslate": {"status": "degraded", "latency_ms": 1000},
    "ollama": {"status": "ok", "latency_ms": 45}
  }
}
```

Status semantics:

- `ok`: all required dependencies for enabled features are available.
- `degraded`: core API works, but an optional or feature-specific dependency is
  unavailable, such as Ollama when intelligence features are enabled.
- `down`: core dependencies required for normal operation are unavailable, such
  as PostgreSQL.

Readiness checks should cache results for a short interval, for example 10 to 30
seconds, to avoid turning dashboards into dependency load generators.

### Metrics Endpoint

Expose Prometheus-format metrics on the API service:

```text
GET /metrics
```

Deployment options, in preferred order:

1. Bind `/metrics` only to the internal Compose network and let Prometheus scrape
   `api:8000/metrics`.
2. If published externally, protect `/metrics` through reverse-proxy allowlists
   or admin authentication.
3. Never include sensitive labels or exemplars even on private networks.

The implementation should use `prometheus-client` or equivalent OpenMetrics
output. Metrics must be safe when dependencies are missing and must not block
request handling.

### Structured Logs

Move application logs toward JSON records with a common schema:

| Field | Required | Notes |
| --- | --- | --- |
| `timestamp` | Yes | RFC 3339 UTC timestamp. |
| `level` | Yes | `debug`, `info`, `warning`, `error`, or `critical`. |
| `logger` | Yes | Python logger name. |
| `message` | Yes | Human-readable event summary without secrets. |
| `request_id` | When available | Generated per inbound HTTP request. |
| `trace_id` | When available | OpenTelemetry trace identifier. |
| `route` | HTTP only | Route template, not raw path with IDs. |
| `method` | HTTP only | HTTP method. |
| `status_code` | HTTP only | Response code. |
| `duration_ms` | HTTP only | Request latency. |
| `component` | Recommended | `api`, `pipeline`, `search`, `translation`, `intelligence`, etc. |
| `outcome` | Recommended | `success`, `failure`, `skipped`, `retry`, `dlq`. |
| `error_type` | Errors only | Exception class name only; no full message if it may contain user data. |

The API should accept and propagate `X-Request-ID`; if absent, middleware should
generate one. Responses should echo `X-Request-ID` to make operator support and
user bug reports correlate with logs.

### Tracing

Tracing is optional for the first metrics phase but the design should leave
hooks for OpenTelemetry. Recommended spans:

- HTTP request handling by route template.
- Database transactions around route handlers and repositories.
- Elasticsearch search and indexing calls.
- Qdrant vector search, upsert, and delete calls.
- LibreTranslate detection/translation calls.
- Ollama summarization, entity extraction, tagging, and Q&A calls.
- Pipeline stages: extract, translate, chunk, embed, index, intelligence,
  subscriptions.

Trace attributes follow the same low-cardinality and no-content rules as metric
labels.

## Metric Catalog

### Process And Runtime

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `tomorrowland_build_info` | gauge | `version`, `commit`, `environment` | Static build/runtime metadata with value `1`. |
| `process_*` | default | none | Standard process metrics from the Prometheus client. |
| `python_gc_*` | default | none | Standard Python GC metrics. |

### HTTP API

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `tomorrowland_http_requests_total` | counter | `method`, `route`, `status_class` | API requests by normalized route. |
| `tomorrowland_http_request_duration_seconds` | histogram | `method`, `route` | API latency by route. |
| `tomorrowland_http_request_size_bytes` | histogram | `method`, `route` | Optional request body size buckets. |
| `tomorrowland_http_response_size_bytes` | histogram | `method`, `route` | Optional response body size buckets. |
| `tomorrowland_http_exceptions_total` | counter | `route`, `error_type` | Unhandled exceptions by route template and exception class. |

Recommended latency buckets: `0.005`, `0.01`, `0.025`, `0.05`, `0.1`, `0.25`,
`0.5`, `1`, `2.5`, `5`, `10`, `30`.

### Authentication And Authorization

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `tomorrowland_auth_login_attempts_total` | counter | `provider`, `outcome` | Login attempts by configured provider and result. |
| `tomorrowland_authz_denials_total` | counter | `resource_type`, `action` | Permission denials without identity labels. |
| `tomorrowland_admin_actions_total` | counter | `action`, `resource_type` | Admin actions already written to audit log. |

### Ingestion And Pipeline

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `tomorrowland_ingestion_syncs_total` | counter | `connector_type`, `outcome` | Source sync attempts. |
| `tomorrowland_ingestion_documents_total` | counter | `connector_type`, `outcome` | Documents discovered or accepted for processing. |
| `tomorrowland_pipeline_documents_total` | counter | `stage`, `outcome` | Document processing by stage. |
| `tomorrowland_pipeline_stage_duration_seconds` | histogram | `stage` | Stage latency for extraction, translation, chunking, indexing, etc. |
| `tomorrowland_pipeline_document_bytes` | histogram | `connector_type` | Original file sizes. |
| `tomorrowland_pipeline_chunks_total` | counter | `outcome` | Chunks created or failed. |
| `tomorrowland_dlq_records_total` | counter | `reason`, `source` | Records sent to the DLQ. |
| `tomorrowland_dlq_pending` | gauge | none | Current pending DLQ records from PostgreSQL. |

### Search And Retrieval

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `tomorrowland_search_requests_total` | counter | `mode`, `outcome` | Search requests by BM25, vector, or hybrid mode. |
| `tomorrowland_search_duration_seconds` | histogram | `mode` | End-to-end search latency. |
| `tomorrowland_search_backend_duration_seconds` | histogram | `backend`, `operation` | Elasticsearch and Qdrant call latency. |
| `tomorrowland_search_results_count` | histogram | `mode` | Result count distribution. |
| `tomorrowland_search_permission_filtered_total` | counter | `mode` | Results filtered out by permission checks, if available without high cost. |
| `tomorrowland_search_index_documents` | gauge | `backend` | Approximate indexed document/vector count from Elasticsearch and Qdrant. |

### Translation, Intelligence, And RAG

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `tomorrowland_translation_requests_total` | counter | `kind`, `outcome` | Detection, auto-enrich, and manual translation attempts. |
| `tomorrowland_translation_duration_seconds` | histogram | `kind` | Translation latency. |
| `tomorrowland_translation_characters_total` | counter | `kind` | Characters submitted for translation. |
| `tomorrowland_intelligence_tasks_total` | counter | `task`, `outcome` | Summarization, entity extraction, and auto-tag tasks. |
| `tomorrowland_intelligence_task_duration_seconds` | histogram | `task` | Intelligence task latency. |
| `tomorrowland_ollama_requests_total` | counter | `operation`, `outcome` | Ollama calls by operation. |
| `tomorrowland_ollama_duration_seconds` | histogram | `operation` | Ollama request latency. |
| `tomorrowland_rag_requests_total` | counter | `outcome` | Q&A requests. |
| `tomorrowland_rag_duration_seconds` | histogram | `phase` | Retrieval, prompt assembly, and generation latency. |
| `tomorrowland_rag_citations_count` | histogram | none | Citation count distribution. |

### Collaboration And Activity

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `tomorrowland_preview_requests_total` | counter | `mime_family`, `outcome` | Preview requests by coarse MIME family. |
| `tomorrowland_download_requests_total` | counter | `outcome` | Safe download attempts. |
| `tomorrowland_comments_total` | counter | `action`, `outcome` | Comment create/update/delete operations. |
| `tomorrowland_annotations_total` | counter | `action`, `visibility`, `outcome` | Annotation operations. |
| `tomorrowland_subscriptions_total` | counter | `action`, `outcome` | Subscription CRUD actions. |
| `tomorrowland_notifications_total` | counter | `event`, `outcome` | Notification creation/read events. |

### Dependency And Queue Health

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `tomorrowland_dependency_up` | gauge | `dependency` | `1` when a dependency readiness probe succeeds, else `0`. |
| `tomorrowland_dependency_latency_seconds` | histogram | `dependency`, `operation` | Dependency probe or call latency. |
| `tomorrowland_kafka_consumer_lag` | gauge | `topic`, `consumer_group` | Future worker consumer lag once consumers exist. |
| `tomorrowland_worker_heartbeat_timestamp_seconds` | gauge | `worker` | Future long-running worker heartbeat. |

## Dashboards

### Executive Health

- API up/down and error rate.
- Search p50/p95 latency against the 300 ms target.
- Q&A p50/p95 latency against the 10 second target.
- Ingest throughput and failures.
- DLQ pending count.
- Dependency status for PostgreSQL, Elasticsearch, Qdrant, LibreTranslate, and
  Ollama.

### API And UX

- Request rate, error rate, and latency by route.
- Authentication failures by provider.
- Authorization denials by resource/action.
- Preview and download success/error rates.
- Slowest routes by p95 latency.

### Ingestion And Indexing

- Source sync attempts and outcomes by connector type.
- Pipeline stage durations.
- Documents processed and failed by stage.
- Chunk counts and indexing backend call latency.
- DLQ trend and retry outcomes.

### Search And RAG

- Hybrid search latency and backend split.
- Search result count distribution.
- Q&A retrieval/generation latency split.
- Ollama error rate and latency.
- RAG answer fallback/error outcomes.

### Infrastructure

- PostgreSQL, Elasticsearch, Qdrant, LibreTranslate, Ollama, and Redpanda health.
- Container restarts, CPU, memory, disk use, and volume free space.
- Elasticsearch shard/index health and Qdrant collection size.

## Alerting Rules

Initial alert rules should prefer sustained conditions:

| Alert | Severity | Condition | Suggested Duration |
| --- | --- | --- | --- |
| API down | Critical | Prometheus cannot scrape API or `/health` fails. | 2 minutes |
| PostgreSQL unavailable | Critical | `tomorrowland_dependency_up{dependency="postgres"} == 0`. | 2 minutes |
| Search unavailable | Critical | Elasticsearch or Qdrant dependency down. | 5 minutes |
| High API error rate | Warning | 5xx rate exceeds 2% of requests. | 10 minutes |
| Search SLO breach | Warning | p95 search latency exceeds 300 ms. | 15 minutes |
| Q&A SLO breach | Warning | p95 RAG latency exceeds 10 seconds. | 15 minutes |
| DLQ growing | Warning | Pending DLQ records increase for consecutive checks. | 15 minutes |
| Ingestion failing | Warning | Pipeline failure ratio exceeds 5%. | 15 minutes |
| Disk pressure | Critical | Any durable volume has less than 10% free space. | 5 minutes |
| Ollama degraded | Warning | Ollama down while intelligence or RAG is enabled. | 10 minutes |

## Docker Compose Monitoring Stack

Add monitoring as an optional profile after application metrics exist:

- `prometheus`: scrapes API `/metrics`, cAdvisor/node-exporter equivalents if
  accepted for the target deployment, and infrastructure exporters where useful.
- `grafana`: local dashboards provisioned from the repository.
- `alertmanager`: optional for local deployments; useful when integrating with
  email or internal chat.
- Exporters should be added only when they provide data not already exposed by
  the service or Docker runtime.

Prometheus and Grafana volumes should be documented in the backup guide as
operational state, not source-of-truth product data. Losing dashboards should
not lose documents or permissions.

## Implementation Phases

1. **Metrics foundation:** add Prometheus client dependency, `/metrics`, HTTP
   middleware, safe label helpers, request ID middleware, unit tests, and docs.
2. **Domain metrics:** instrument auth, sync, pipeline, search, preview,
   translation, intelligence, RAG, comments, annotations, subscriptions, and DLQ
   paths with targeted tests.
3. **Readiness and dependency probes:** add cached admin readiness checks and
   dependency gauges.
4. **Local monitoring stack:** add optional Compose profile for Prometheus and
   Grafana plus dashboard provisioning and operations documentation.
5. **Structured logs and tracing:** move to JSON logs with request IDs, then add
   OpenTelemetry hooks if operationally needed.
6. **Worker observability:** when long-running worker entrypoints are introduced,
   reuse the same pipeline metrics and add heartbeats plus consumer lag.

## Validation Expectations

- Metrics endpoint tests verify Prometheus output and safe low-cardinality
  labels.
- Route middleware tests verify normalized route labels and `X-Request-ID`
  propagation.
- Instrumented service tests verify success and failure counters without live
  external services.
- Readiness tests mock PostgreSQL, Elasticsearch, Qdrant, LibreTranslate, and
  Ollama outcomes.
- Compose validation covers optional monitoring profile configuration.
- Documentation validation confirms no secret examples or document-content labels
  appear in metrics, logs, dashboards, or alerts.
