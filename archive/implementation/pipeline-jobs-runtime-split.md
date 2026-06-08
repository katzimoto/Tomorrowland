# Pipeline Jobs / Runtime Split — Implementation Plan

> Issue: #235
> Branch: `feature/pipeline-jobs` (integration) → `main` (final PR only)
> Status: planning only — no migrations, no worker code, no Compose changes yet

---

## 1. Integration Branch Scope

All implementation work for this track targets `feature/pipeline-jobs`.
No sub-PR may merge directly to `main`. Only the final validated integration
PR crosses that boundary.

What this track introduces:

- A PostgreSQL-backed job queue (no new required infrastructure).
- Separate long-running worker processes for fast pipeline and slow enrichment.
- Docker Compose service definitions for `pipeline-worker` and `slow-worker`.
- An async `sync-now` API contract (enqueue instead of inline run).
- Job status, retry, and dead-letter surfaces for operators.
- Structured metrics and logs emitted from worker processes.

What this track does not introduce:

- No mandatory Kafka dependency for the job queue.
- No new required services beyond those already in Compose.
- No changes to existing document schema columns.
- No user-facing auth or search changes.

---

## 2. Issue Order and Merge Order

Merge into `feature/pipeline-jobs` in this order. Each subtask branch targets
`feature/pipeline-jobs`, not `main`.

| Order | Issue | Scope | Key outputs |
|-------|-------|-------|-------------|
| 1 | **#209** | Job queue schema and Alembic migration | `pipeline_jobs` table, downgrade path |
| 2 | **#210** | `JobQueue` repository layer | `enqueue`, `claim`, `ack`, `nack`, `list_by_status` |
| 3 | **#213** | API `sync-now` async contract | `sync-now` enqueues; `GET /admin/jobs/{id}` poll endpoint |
| 4 | **#214** | `pipeline-worker` runner and Compose service | Entrypoint command, health/metrics, Compose wiring |
| 5 | **#215** | `slow-worker` runner and Compose service | Entrypoint command, health/metrics, Compose wiring |
| 6 | **#216** | Retry/DLQ, metrics, final integration validation | Full retry semantics, DLQ surface, alert rules |

After all six issues are merged and validated on `feature/pipeline-jobs`, open
the single final PR: `feature/pipeline-jobs` → `main`.

**Merge constraints:**

- #210 requires #209 (table must exist before the repository layer is written).
- #213 requires #210 (enqueue API needs the repository).
- #214 and #215 can be developed in parallel after #213 merges; they both depend
  on #213 for the queue interface but do not depend on each other.
- #216 requires #214 and #215 (retry and DLQ instrumentation spans both workers).

---

## 3. Queue Architecture Recommendation

**Chosen path: PostgreSQL DB queue as the primary and default transport.**

Kafka remains in the Compose stack for NiFi event ingestion (#65), but is
**not** required by the job queue in this track. This preserves compatibility
with air-gapped and minimal deployments.

### Rationale

| Factor | DB queue | Kafka |
|--------|----------|-------|
| Required new infra | None (Postgres already hard-dep) | Kafka mandatory (breaks minimal deploys) |
| Air-gapped deployment | No change | Requires Kafka image and broker |
| Operational simplicity | SQL inspection, standard migration | Topic/offset management, consumer groups |
| Atomic claim | `SELECT … FOR UPDATE SKIP LOCKED` | Partition/offset coordination |
| Rollback | Alembic downgrade | Topic cleanup + code rollback |
| Throughput ceiling | Adequate for document indexing workloads | Higher ceiling, not needed at this scale |

A Kafka transport for the job queue can be added later as an optional mode
(environment variable `JOB_QUEUE_BACKEND=kafka`) without changing the
repository interface. The `#216` issue should open a follow-up ticket for that
path if demand exists; it must not be built inside this track.

### Job Table Schema (illustrative, not a migration)

```sql
CREATE TABLE pipeline_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type        TEXT    NOT NULL,   -- 'pipeline' | 'slow'
    documant_id          UUID    NOT NULL,
    source_id       UUID    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'pending',
                                       -- pending | running | done | failed | dlq
    attempts        INTEGER NOT NULL DEFAULT 0,
    max_attempts    INTEGER NOT NULL DEFAULT 3,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    claimed_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    error           TEXT,
    dlq_at          TIMESTAMPTZ,
    dlq_reason      TEXT,
    next_attempt_at TIMESTAMPTZ         -- exponential back-off ceiling
);

CREATE INDEX idx_pipeline_jobs_claim
    ON pipeline_jobs (job_type, status, next_attempt_at)
    WHERE status = 'pending';

CREATE INDEX idx_pipeline_jobs_source
    ON pipeline_jobs (source_id, status);
```

Workers claim rows with `SELECT … FOR UPDATE SKIP LOCKED`. The unique claim
window is `status = 'pending' AND (next_attempt_at IS NULL OR next_attempt_at <= now())`.

---

## 4. Schema and Migration Boundaries

- **Migration owned by #209**: creates `pipeline_jobs` and its indexes.
- **Downgrade path**: drops `pipeline_jobs`. No data in existing tables is
  affected; downgrade is safe as long as workers are stopped first.
- **No existing table columns are added or removed** in this track. The
  `documents.status` and `documents.translation_quality` columns remain unchanged.
- **No Kafka topic creation** is part of these migrations; topic management
  stays in operator runbooks, not Alembic.
- Migrations follow the existing convention: `migrations/versions/` with both
  `upgrade()` and `downgrade()` functions, tested via the `migrated_engine`
  fixture in `tests/conftest.py`.

---

## 5. API `sync-now` Contract Changes

### Current contract (synchronous MVP)

```
POST /admin/ingestion/{source_id}/sync-now
→ 200 {"synced": N}
```

Pipeline runs inline in the request. Response is returned after all documents
are processed.

### New contract (async queue)

```
POST /admin/ingestion/{source_id}/sync-now
→ 200 {"queued": N, "job_ids": ["<uuid>", ...]}
```

The endpoint scans the source, creates one `pipeline_jobs` row per
newly-discovered document, and returns immediately. Callers that only check
HTTP 200 continue to work. The `synced` field is replaced by `queued`.

### New endpoints (owned by #213)

```
GET /admin/jobs/{job_id}
→ 200 {
    "id": "<uuid>",
    "job_type": "pipeline"|"slow",
    "documant_id": "<uuid>",
    "source_id": "<uuid>",
    "status": "pending"|"running"|"done"|"failed"|"dlq",
    "attempts": N,
    "created_at": "<iso8601>",
    "completed_at": "<iso8601>"|null,
    "error": "<string>"|null
}

GET /admin/jobs?source_id=<uuid>&status=<status>&limit=<N>
→ 200 {"jobs": [...], "total": N}
```

Both endpoints are admin-only (`require_admin(user)`). No user-facing job
exposure is introduced in this track.

### Sync count vs indexing count

- **Sync count** (`queued`): number of documents discovered by the source
  scanner in this sync call. This is the number of jobs enqueued.
- **Indexed count**: number of jobs that reached `status = 'done'`. Visible via
  `GET /admin/jobs?source_id=<uuid>&status=done`.
- The two counts may differ if a worker fails jobs or moves them to DLQ.
  Operators should monitor DLQ depth to detect persistent failures.

---

## 6. Worker Runner Command Shape

### `pipeline-worker`

Fast-path worker. Claims and processes `job_type = 'pipeline'` jobs.

```
tomorrowland-pipeline-worker \
    [--concurrency N]           # default: 2, env: PIPELINE_WORKER_CONCURRENCY
    [--poll-interval SECONDS]   # default: 2, env: PIPELINE_WORKER_POLL_INTERVAL
    [--queue-type db|kafka]     # default: db, env: JOB_QUEUE_BACKEND
    [--health-port PORT]        # default: 8001, env: PIPELINE_WORKER_HEALTH_PORT
    [--metrics-port PORT]       # default: same as --health-port
```

### `slow-worker`

Enrichment worker. Claims and processes `job_type = 'slow'` jobs.

```
tomorrowland-slow-worker \
    [--concurrency N]           # default: 1, env: SLOW_WORKER_CONCURRENCY
    [--poll-interval SECONDS]   # default: 5, env: SLOW_WORKER_POLL_INTERVAL
    [--health-port PORT]        # default: 8002, env: SLOW_WORKER_HEALTH_PORT
    [--metrics-port PORT]       # default: same as --health-port
```

### Common behavior for both workers

- **Health**: `GET /health` returns `{"status": "ok", "worker_type": "..."}`
  on the health port.
- **Metrics**: `GET /metrics` returns Prometheus-format metrics on the same port.
- **Startup**: reads `DATABASE_URL` and all shared config from `.env` via
  `shared.config.Settings`.
- **Shutdown**: handles `SIGTERM` by stopping job pickup, waiting for any
  in-progress job to finish (up to 30 seconds), then exiting cleanly.
- **Entrypoints**: registered in `pyproject.toml` under `[project.scripts]`.
- **Compose profile**: worker containers belong to a `workers` Compose profile
  so the standard `docker compose up` does not start them until a worker
  entrypoint exists. Add them to the default profile only after this track is
  fully merged.

---

## 7. Retry and Dead-Letter Semantics

### Retry policy

1. On job failure: increment `attempts`, log the error, compute
   `next_attempt_at = now() + 2^attempts seconds` (exponential backoff).
2. Set `status = 'pending'` so the scheduler picks it up again when
   `next_attempt_at` is past.
3. When `attempts >= max_attempts`: set `status = 'dlq'`, set `dlq_at = now()`,
   record `dlq_reason` (truncated exception class and message, no stack trace in
   the DB column).

### Failure categories

| Category | Action |
|----------|--------|
| Transient infra (DB connection lost, Elasticsearch timeout) | Retry with backoff; do not count toward `max_attempts` for first occurrence per job |
| Business logic failure (extraction failed, doc not found) | Count toward `max_attempts`; DLQ after limit |
| Vector indexing failure (Qdrant unavailable) | Log and continue; document still marked `done` (existing soft-failure behavior preserved) |
| Intelligence / alert matching failure | Log and continue; always best-effort |

### Dead-letter queue surface

- Operator inspection: `GET /admin/jobs?status=dlq&source_id=<uuid>`
- Manual re-queue: `POST /admin/jobs/{job_id}/retry` — resets `status`,
  `attempts`, and `dlq_at`; implemented in #216.
- Alert rule `TomorrowlandDlqPending` already exists in
  `docker/prometheus/alerts.yml` and fires when DLQ depth exceeds 0.
  The new `tomorrowland_dlq_depth` gauge (see Section 8) feeds this rule.

---

## 8. Metrics and Logging Expectations

### New Prometheus metrics (emitted by workers)

| Metric | Type | Labels | Notes |
|--------|------|--------|-------|
| `tomorrowland_job_queue_depth` | Gauge | `worker_type`, `status` | Polled from DB; updated each poll cycle |
| `tomorrowland_job_duration_seconds` | Histogram | `worker_type`, `outcome` | Per-job wall-clock time; `outcome` = done/failed/dlq |
| `tomorrowland_job_attempts_total` | Counter | `worker_type`, `attempt_type` | `attempt_type` = first/retry |
| `tomorrowland_dlq_depth` | Gauge | `worker_type` | Feeds existing `TomorrowlandDlqPending` alert |

Existing metrics (`tomorrowland_pipeline_documents_total`,
`tomorrowland_pipeline_stage_duration_seconds`, etc.) continue unchanged.
Workers call the same `MetricsRegistry` used by the API worker today.

### Structured log fields

Workers emit JSON-structured log lines. Required fields for every job log
event:

```json
{
  "worker_type": "pipeline"|"slow",
  "job_id": "<uuid>",
  "documant_id": "<uuid>",
  "source_id": "<uuid>",
  "attempt": 1,
  "outcome": "done"|"failed"|"dlq"|"retry",
  "duration_ms": 1234,
  "correlation_id": "<uuid>"
}
```

Forbidden log fields (preserve existing data-safety rules):
- No document content, titles, or extracted text in log lines.
- No file paths beyond what is already in the structured correlation log.
- No user IDs, query text, or JWT values.

---

## 9. Rollback Strategy

### Phase rollback (stop workers, keep API running)

1. Stop worker containers: `docker compose stop pipeline-worker slow-worker`.
2. In-flight jobs (`status = 'running'`) remain claimed. The API remains
   available; sync-now continues to enqueue jobs.
3. Workers can be restarted at any time. Jobs with `status = 'running'`
   that exceeded a wall-clock timeout (configurable, default 10 minutes) are
   reclaimed by a worker startup sweep and reset to `pending`.

### Full feature rollback

1. Stop workers.
2. Wait for all `status = 'running'` rows to timeout and be reset (or reset
   them manually with `UPDATE pipeline_jobs SET status='pending' WHERE status='running'`).
3. Export DLQ rows if needed: `GET /admin/jobs?status=dlq` (save output).
4. Redeploy API with the pre-async `sync-now` (inline pipeline mode).
5. Run `alembic downgrade` for the #209 migration to drop `pipeline_jobs`.

This sequence does not require `docker compose down -v` and does not delete
document data or search indexes.

### Partial rollback: API only

If the async API contract must be reverted independently of the worker
containers, redeploy only the API image. Workers that cannot claim new jobs
(because `sync-now` no longer enqueues) will idle and can be stopped after
the queue drains.

---

## 10. Final Validation Checklist (before `feature/pipeline-jobs` → `main`)

### Schema and migrations

- [ ] `alembic upgrade head` passes on a clean Postgres database.
- [ ] `alembic downgrade` from head passes and drops `pipeline_jobs`.
- [ ] `pytest tests/integration/` passes with the `migrated_engine` fixture
  against the new schema.
- [ ] No existing migrations are modified; new migration is appended only.

### API contract

- [ ] `POST /admin/ingestion/{source_id}/sync-now` returns `{"queued": N, "job_ids": [...]}`.
- [ ] `GET /admin/jobs/{job_id}` returns correct status.
- [ ] `GET /admin/jobs?source_id=<uuid>&status=done` lists completed jobs.
- [ ] `GET /admin/jobs?status=dlq` lists DLQ jobs.
- [ ] `POST /admin/jobs/{job_id}/retry` re-queues a DLQ job.
- [ ] All new routes are admin-only; non-admin requests return 403.
- [ ] Callers that only check HTTP 200 on sync-now are unaffected.

### Worker behavior

- [ ] `tomorrowland-pipeline-worker` starts, logs structured JSON, serves `GET /health`.
- [ ] `tomorrowland-slow-worker` starts, logs structured JSON, serves `GET /health`.
- [ ] Worker claims a job, processes it, sets `status = 'done'`.
- [ ] SIGTERM during active job: job finishes, worker exits with code 0.
- [ ] Retry: simulate a transient failure; confirm `attempts` increments and
  `next_attempt_at` is set.
- [ ] DLQ: exhaust `max_attempts`; confirm `status = 'dlq'` and `dlq_reason`.
- [ ] `tomorrowland_dlq_depth` gauge is non-zero when DLQ rows exist.

### Metrics and logs

- [ ] `GET /metrics` on worker health port returns all four new metric families.
- [ ] Prometheus scrape from the monitoring profile picks up worker endpoints.
- [ ] Log lines include all required structured fields.
- [ ] No sensitive fields (document content, tokens, user IDs) appear in logs.

### Air-gapped and minimal deployments

- [ ] Stack starts with `JOB_QUEUE_BACKEND=db` (default) without Kafka.
- [ ] Workers start in a Compose environment with Kafka disabled or absent.
- [ ] Air-gap wrapper (`scripts/tomorrowland-airgap.sh`) is unaffected.

### Static analysis and CI

- [ ] `ruff check --fix src/ tests/ migrations/` passes with no errors.
- [ ] `ruff format src/ tests/ migrations/` produces no diff.
- [ ] `mypy src --strict` passes.
- [ ] `pytest` passes at the 90% coverage floor.
- [ ] `bash scripts/production-audit.sh` passes.
- [ ] `bash scripts/check-pr-cleanliness.sh feature/pipeline-jobs` passes.

### Final integration sign-off

- [ ] Integration branch rebased on latest `main` with no conflicts.
- [ ] Final PR body includes integration validation summary (ruff, mypy,
  pytest, production-audit).
- [ ] Review routing: Claude (architecture/migration/security) + Codex
  (correctness/tests/CI).

---

## References

- `docs/implementation/phase-03d-worker-pipeline.md` — original synchronous pipeline plan
- `docs/operations/pipeline-workers.md` — operator guide (created alongside this plan)
- `docs/operations/production-compose.md` — Compose service layout and limitations
- `src/services/pipeline/worker.py` — current `PipelineWorker` class
- `src/services/pipeline/slow_worker.py` — current `SlowWorker` class
- `src/services/pipeline/kafka_consumer.py` — NiFi Kafka drain (separate from job queue)
- `AGENTS.md` → Feature branch policy for multi-issue tracks
