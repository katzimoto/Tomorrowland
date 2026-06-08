# Phase 10b: Domain Metrics

## Goal

Instrument all existing service paths with low-cardinality counters and histograms so
operators can observe the health of every major application domain.

Design source: `docs/design/metrics-monitoring-spec.md` §Metric Catalog (all domain tables).

## Phase Placement

Branch: `developer/phase-10b-domain-metrics`

Status: Planned (requires Phase 10a metrics foundation and safe label helpers).

## Dependencies

- Phase 10a metrics foundation, `/metrics` endpoint, and label helper utilities.
- All Phase 03–08 service implementations (auth, pipeline, search, translation,
  intelligence, RAG, comments, annotations, subscriptions, notifications, related).

## Scope

Instrument the following service paths. Use the metric names and label sets defined in
`docs/design/metrics-monitoring-spec.md`. Do not introduce new metric names not listed there
without updating the spec first.

### Authentication And Authorization

- `tomorrowland_auth_login_attempts_total` — labels: `provider`, `outcome`.
- `tomorrowland_authz_denials_total` — labels: `resource_type`, `action`.
- `tomorrowland_admin_actions_total` — labels: `action`, `resource_type`.

### Ingestion And Pipeline

- `tomorrowland_ingestion_syncs_total` — labels: `connector_type`, `outcome`.
- `tomorrowland_ingestion_documents_total` — labels: `connector_type`, `outcome`.
- `tomorrowland_pipeline_documents_total` — labels: `stage`, `outcome`.
- `tomorrowland_pipeline_stage_duration_seconds` histogram — label: `stage`.
- `tomorrowland_pipeline_document_bytes` histogram — label: `connector_type`.
- `tomorrowland_pipeline_chunks_total` — labels: `outcome`.
- `tomorrowland_dlq_records_total` — labels: `reason`, `source`.
- `tomorrowland_dlq_pending` gauge — no labels; read from PostgreSQL at scrape time.

### Search And Retrieval

- `tomorrowland_search_requests_total` — labels: `mode`, `outcome`.
- `tomorrowland_search_duration_seconds` histogram — label: `mode`.
- `tomorrowland_search_backend_duration_seconds` histogram — labels: `backend`, `operation`.
- `tomorrowland_search_results_count` histogram — label: `mode`.
- `tomorrowland_search_index_documents` gauge — label: `backend`.

### Translation, Intelligence, And RAG

- `tomorrowland_translation_requests_total` — labels: `kind`, `outcome`.
- `tomorrowland_translation_duration_seconds` histogram — label: `kind`.
- `tomorrowland_translation_characters_total` counter — label: `kind`.
- `tomorrowland_intelligence_tasks_total` — labels: `task`, `outcome`.
- `tomorrowland_intelligence_task_duration_seconds` histogram — label: `task`.
- `tomorrowland_ollama_requests_total` — labels: `operation`, `outcome`.
- `tomorrowland_ollama_duration_seconds` histogram — label: `operation`.
- `tomorrowland_rag_requests_total` — label: `outcome`.
- `tomorrowland_rag_duration_seconds` histogram — label: `phase`.
- `tomorrowland_rag_citations_count` histogram — no labels.

### Collaboration And Activity

- `tomorrowland_preview_requests_total` — labels: `mime_family`, `outcome`.
- `tomorrowland_download_requests_total` — label: `outcome`.
- `tomorrowland_comments_total` — labels: `action`, `outcome`.
- `tomorrowland_annotations_total` — labels: `action`, `visibility`, `outcome`.
- `tomorrowland_subscriptions_total` — labels: `action`, `outcome`.
- `tomorrowland_notifications_total` — labels: `event`, `outcome`.

## Implementation Notes

- Instrument at the service-class method level, not inside route handlers, so metrics are
  reusable by future worker entrypoints.
- Use the safe label helpers from Phase 10a for all label values.
- Mock all external services in unit tests; verify counter increments on success and failure
  paths without requiring live backends.

## Validation

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src --strict
pytest tests/unit/test_domain_metrics.py -q
```

Each instrumented service should have at least a success-path and failure-path counter
assertion.

## Acceptance Criteria

- All metric names in the catalog have at least one test asserting they increment on the
  happy path.
- Failure paths increment outcome-labeled failure counters rather than raising unhandled
  exceptions.
- No label value contains a user ID, document ID, query string, source name, or file content.
- Existing service unit tests remain green.
