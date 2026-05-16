## Meilisearch Rollout — Decisions

### 1. Startup initialization order

`initialize_meilisearch(client, settings)` runs once at application startup, before the API
accepts traffic. It calls `apply_index_settings` on the live index unconditionally; it calls
`apply_index_settings` on the shadow index only when `feature_meilisearch_shadow_index` is
enabled. Settings application is idempotent — safe to re-run on every restart.

### 2. Feature-flag gating

Two thin helpers — `is_search_enabled(settings)` and `is_shadow_enabled(settings)` — read
`feature_meilisearch_search` and `feature_meilisearch_shadow_index` from `Settings`. Callers
must gate every read/write path through these helpers rather than reading the flag attribute
directly. This keeps flag-check semantics in one place and makes tests straightforward.

### 3. Shadow-index lifecycle

The shadow index follows a prepare → populate → swap → drop sequence:

- **prepare**: `initialize_meilisearch` with `shadow=True` creates the shadow index and applies
  settings. Called once before the bulk populate begins.
- **populate**: callers iterate document chunks and call `provider.index_batch(..., shadow=True)`
  in batches. Batch size and concurrency are caller-owned; the rollout module supplies no
  iteration logic to keep concerns separated.
- **swap**: `provider.swap_indexes()` atomically promotes shadow to live.
- **drop**: `provider.drop_shadow_index()` deletes the old live index (now shadow after swap).
  Callers must wait for the swap task to complete before dropping.

### 4. Health check integration

`meilisearch_health_probe(provider, metrics)` calls `provider.health_check()` and then
records to the shared `MetricsRegistry`:

- `dependency_up` gauge — `1` on success, `0` on failure, label `dependency="meilisearch"`
- `dependency_latency_seconds` histogram — latency in seconds, labels
  `dependency="meilisearch", operation="health"`

The function returns the raw `health_check()` dict so callers can include it in `/health`
endpoint responses. When `metrics` is `None`, the probe still runs but skips emission.

### 5. Search observability

`record_search_metrics(metrics, duration_s, hits, outcome)` emits two metrics after a
Meilisearch search call completes:

- `search_backend_duration_seconds` histogram — labels `backend="meilisearch", operation="search"`
- `search_requests_total` counter — labels `mode="meilisearch", outcome=outcome`

`outcome` is `"ok"` on success or an error class string on failure (e.g. `"connection_error"`).
When `metrics` is `None`, the call is a no-op.

### 6. Index / write observability

`record_index_metrics(metrics, duration_s, chunk_count, outcome)` emits after bulk or single
index operations:

- `pipeline_stage_duration_seconds` histogram — label `stage="meilisearch_index"`
- `pipeline_documents_total` counter — labels `stage="meilisearch_index", outcome=outcome`
  incremented by `chunk_count`

`pipeline_documents_total` is used because indexing chunks is the final pipeline stage that
makes documents searchable. Using the existing pipeline counter keeps the Grafana dashboard
unified rather than introducing a separate counter.

### 7. Docker Compose service

The `meilisearch` service uses `getmeili/meilisearch:v1.9` with:
- `MEILI_MASTER_KEY` set from `${MEILISEARCH_MASTER_KEY:-}` (empty default — instance starts
  in no-auth mode in dev, callers supply a key in prod)
- `MEILI_ENV` set to `${APP_ENV:-prod}` so Meilisearch itself omits the development UI in prod
- A TCP healthcheck on port 7700
- A named volume `meilisearch_data`
- Env vars `MEILISEARCH_URL` and `MEILISEARCH_MASTER_KEY` added to the `x-app-environment`
  block so `api` and `worker` containers can connect

The `api` service gains `meilisearch: condition: service_healthy` in `depends_on`.

### 8. No migration step

Meilisearch holds a derived read index, not a source-of-truth store. There is no Alembic
migration. The index is populated (or re-populated) via the shadow-index workflow or by
re-running the pipeline ingestion. This keeps the Meilisearch lifecycle orthogonal to the
Postgres schema migration lifecycle.

### 9. Rollback

Rollback from Meilisearch to Elasticsearch is a feature-flag flip:

1. Set `FEATURE_MEILISEARCH_SEARCH=false` in `.env` (or the container environment).
2. Restart the API container so the new setting takes effect.
3. Verify search requests return results through the Elasticsearch/hybrid path.
4. Monitor search errors and latency in logs and metrics.
5. Meilisearch data remains intact and can be re-enabled later.

**Important:** The feature flag is read at application startup. Live runtime toggling
is not supported — the API container must be restarted for the change to apply.

The Elasticsearch index remains the serving backend whenever `FEATURE_MEILISEARCH_SEARCH`
is `false`. Search continues to work even if the Meilisearch container is unavailable,
because the disabled flag prevents the application from connecting to Meilisearch.
