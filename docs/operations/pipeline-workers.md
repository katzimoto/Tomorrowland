# Pipeline Worker Operations Guide

This guide covers the worker services that drive document ingestion,
translation, embedding, indexing, enrichment, and alert/intelligence
post-processing, the Prometheus metrics they emit, and how to interpret those
signals on-call.

---

## Worker Architecture

Tomorrowland's ingestion pipeline is served by a chain of RabbitMQ workers.
Each worker reads from its own stage queue, processes a message, and publishes
to the next stage. The canonical 7-stage pipeline is:

| Service | Module | Stage |
|---------|--------|-------|
| `parse-worker` | `services.pipeline.parse_worker` | Parse (extraction + chunking) |
| `translate-worker` | `services.pipeline.translate_worker` | Translate |
| `embed-worker` | `services.pipeline.embed_worker` | Embed (vector encoding) |
| `index-worker` | `services.pipeline.index_worker` | Index (Meilisearch + Qdrant) |
| `intelligence-worker` | `services.pipeline.intelligence_consumer` | Intelligence (summary, entities, tags) |
| `alert-worker` | `services.pipeline.alert_consumer` | Alert matching |
| `enrich-worker` | `services.pipeline.enrich_worker` | Enrich (re-translation) |
| `preview-worker` | `services.pipeline.preview_worker` | Preview render (mail/Office artifacts) |

**Queue transport**: RabbitMQ with per-stage queues, 30s retry tiers, and
dead-letter queues (DLQ). Each stage has a primary queue, a retry queue, and
a DLQ. Messages that exhaust their retry budget land in the DLQ for operator
attention.

**Job flow**: ingestion starts when a document is published to the parse queue
(from a sync-now API call or the scheduler). Each worker processes its stage,
marks progress via `pipeline_jobs.stage`, and publishes to the next queue.
`intelligence` and `alert` run in parallel after indexing. `enrich` is
triggered separately for frequently viewed documents. `preview` is triggered
on demand the first time a mail/Office document's preview manifest is
requested (the API enqueues the job; the worker writes the artifacts because
the API mounts `files_data` read-only). A failed render is a **terminal**
artifact state, not a job failure — the job still succeeds, so a broken file
never loops through retry/DLQ; an admin re-render is the only retry path.

`intelligence_document` and `alert_document` are **best-effort** stages: if
the model or alert service is unreachable, the stage is logged and the
document's ingestion status is unaffected.

All workers run a tight consume loop:

1. Emit heartbeat gauge (current Unix timestamp).
2. Consume from the stage queue with a 30-second timeout.
3. On success, acknowledge and publish to the next stage.
4. On failure, nack with retry routing or DLQ after max attempts.

---

## Metrics Reference

All metrics below are registered in `MetricsRegistry` in `src/shared/metrics.py`.
Metric names are reproduced exactly as registered.

### `tomorrowland_worker_heartbeat_timestamp_seconds`

**Type**: Gauge  
**Labels**: `worker_type`, `worker_id`

Set to the current Unix timestamp at the top of every loop iteration.
`worker_type` is one of `parse`, `translate`, `embed`, `index`,
`intelligence`, `alert`, or `enrich`; `worker_id` is the stable identifier
passed at startup (e.g. `parse-worker`, `index-worker`).

**How to use**: detect a stopped or stale worker:

```promql
time() - tomorrowland_worker_heartbeat_timestamp_seconds > 120
```

If the expression is true for a worker instance for longer than two minutes,
the process is stuck or has stopped.

---

### `tomorrowland_pipeline_queue_depth`

**Type**: Gauge  
**Labels**: `status`, `job_type`

Snapshot of the `pipeline_jobs` table, counted by `(status, job_type)`, taken
at the top of every loop iteration by the admin API. The snapshot is produced
by `PipelineJobRepository.count_by_status()` which issues a single
`COUNT … GROUP BY status, job_type` query.

Known `status` values: `pending`, `running`, `retry`, `dead_letter`.  
Known `job_type` values: `process_document`, `translate_document`,
`index_document`, `enrich_document`, `intelligence_document`, `alert_document`.

**How to use**:

```promql
# Total pending work across all job types
sum(tomorrowland_pipeline_queue_depth{status="pending"})

# Dead-letter backlog
sum(tomorrowland_pipeline_queue_depth{status="dead_letter"})

# Queue depth by job type
tomorrowland_pipeline_queue_depth{status="pending", job_type="process_document"}
tomorrowland_pipeline_queue_depth{status="pending", job_type="translate_document"}
```

A non-zero `dead_letter` depth requires operator attention; those jobs will not
be retried automatically.

---

### `tomorrowland_pipeline_jobs_claimed_total`

**Type**: Counter  
**Labels**: `worker_type`, `job_type`

Incremented each time a worker successfully claims a job from the queue.
Combined with `_succeeded_total` and `_retried_total` / `_dead_lettered_total`
this describes the overall throughput and error split.

```promql
# Per-minute claim rate for parse worker
rate(tomorrowland_pipeline_jobs_claimed_total{worker_type="parse"}[5m]) * 60
```

---

### `tomorrowland_pipeline_jobs_succeeded_total`

**Type**: Counter  
**Labels**: `worker_type`, `job_type`

Incremented when a job is marked succeeded. The stage matches the worker type:
`parse`, `translate`, `embed`, `index`, `intelligence`, `alert`, or `enrich`.

```promql
# Success rate as a fraction of claimed jobs (5-minute window)
rate(tomorrowland_pipeline_jobs_succeeded_total[5m])
  /
rate(tomorrowland_pipeline_jobs_claimed_total[5m])
```

---

### `tomorrowland_pipeline_jobs_retried_total`

**Type**: Counter  
**Labels**: `worker_type`, `job_type`

Incremented each time a job fails but still has attempts remaining and is
scheduled for retry. A sustained retry rate indicates a recurring transient
error (upstream service instability, intermittent timeouts, etc.).

```promql
rate(tomorrowland_pipeline_jobs_retried_total[5m])
```

---

### `tomorrowland_pipeline_jobs_dead_lettered_total`

**Type**: Counter  
**Labels**: `worker_type`, `job_type`

Incremented when a job exhausts all retry attempts and is moved to
`dead_letter` status. Dead-lettered jobs require manual operator action.

```promql
increase(tomorrowland_pipeline_jobs_dead_lettered_total[1h])
```

Alert when this rate is non-zero or rising. See the troubleshooting section
for remediation steps.

---

### `tomorrowland_pipeline_jobs_stale_lock_reaped_total`

**Type**: Counter  
**Labels**: `worker_type`

Incremented by the number of jobs reset from `running` back to `pending` by
`PipelineJobRepository.reap_stale_locks()`. Stale locks occur when a worker
process crashes or is killed while holding a `running` claim on a job.

`reap_stale_locks()` runs at the top of the loop whenever
`now − last_reap ≥ 60 s`. Each worker instance runs its own reap cycle.

An isolated spike (e.g. after a deploy restart) is normal. A sustained rate
of reaps indicates repeated worker crashes — investigate `worker_loop_errors_total`
and container exit codes.

```promql
rate(tomorrowland_pipeline_jobs_stale_lock_reaped_total[5m])
```

---

### `tomorrowland_pipeline_job_duration_seconds`

**Type**: Histogram  
**Labels**: `worker_type`, `job_type`, `stage`, `outcome`  
**Buckets**: 0.1 s, 0.5 s, 1 s, 2.5 s, 5 s, 10 s, 30 s, 60 s, 120 s, 300 s, 600 s

Measures wall-clock duration of each job attempt from claim to outcome.

| `worker_type` | `stage` | `outcome` values |
|--------------|---------|-----------------|
| `parse` | `parse` | `succeeded`, `retried`, `dead_lettered` |
| `translate` | `translate` | `succeeded`, `retried`, `dead_lettered` |
| `embed` | `embed` | `succeeded`, `retried`, `dead_lettered` |
| `index` | `index` | `succeeded`, `retried`, `dead_lettered` |
| `intelligence` | `intelligence` | `succeeded`, `retried`, `dead_lettered` |
| `alert` | `alert` | `succeeded`, `retried`, `dead_lettered` |
| `enrich` | `enrich` | `succeeded`, `retried`, `dead_lettered` |

```promql
# p95 job duration for parse worker
histogram_quantile(0.95,
  rate(tomorrowland_pipeline_job_duration_seconds_bucket{worker_type="parse"}[10m])
)

# p99 for embed
histogram_quantile(0.99,
  rate(tomorrowland_pipeline_job_duration_seconds_bucket{stage="embed"}[10m])
)
```

---

### `tomorrowland_worker_loop_errors_total`

**Type**: Counter  
**Labels**: `worker_type`, `error_type`

Incremented when an unhandled exception escapes the per-job try/except inside
the main loop (i.e. an error outside of normal job retry/dead-letter handling).
`error_type` is the Python exception class name. After incrementing, the loop
sleeps `poll_interval` and continues.

```promql
rate(tomorrowland_worker_loop_errors_total[5m])
```

A non-zero sustained rate means the worker loop is hitting unexpected errors
that are not being absorbed by the per-job error path. Check logs for full
tracebacks.

---

## Queue Depth Sampling

Queue depth is tracked via the `pipeline_jobs` table and RabbitMQ admin API.
Each worker reports its queue depth metrics via `GET /admin/rabbit/queues`.
The admin dashboard also shows live RabbitMQ queue depths per stage.

---

## Safe Labels and Cardinality

All pipeline worker metric labels are bounded, low-cardinality keywords. The
following **must never appear** as label values:

- Document IDs or UUIDs
- Raw file paths
- User data or user IDs
- Document content or excerpts
- Credentials or tokens
- Exception messages (use the exception class name only via `error_type`)

`worker_id` is the only label that varies per process instance; it is set to a
stable identifier at startup (e.g. the container name or a replica ordinal) and
must not be set to a per-request or per-document value.

The `safe_label_value()` helper in `src/shared/metrics.py` truncates values to
100 characters and coerces empty strings to `"unknown"`. Use it for any
operator-controlled label value.

---

## Stale Job Recovery

When a worker process is killed or crashes while processing a message, the
message is automatically re-routed by RabbitMQ after the connection drops
(consumer timeout). Stale `pipeline_jobs` rows in `running` state are reset
to `pending` on worker restart via `reap_stale_locks()`.

The reap check runs every 60 seconds. It looks for `running` jobs whose lock
timestamp is older than the configured timeout and resets them atomically.

**What stale locks mean operationally**:

- A single reap event after a deploy or container restart is expected.
- Repeated reaps of the same job indicate the job itself is causing crashes.
- Check `worker_loop_errors_total` and container exit codes.

---

## Restart Guidance

To restart a stuck worker safely using Docker Compose:

```bash
# Restart a specific worker without losing container config
docker compose restart parse-worker

# Restart translate-worker
docker compose restart translate-worker

# Restart embed-worker
docker compose restart embed-worker

# Restart index-worker
docker compose restart index-worker

# Restart intelligence-worker
docker compose restart intelligence-worker

# Restart alert-worker
docker compose restart alert-worker

# Restart enrich-worker
docker compose restart enrich-worker
```

`restart: unless-stopped` is set on all worker services, so a plain container
exit will be automatically restarted by Docker. Use `docker compose restart`
when you need to force a restart of a live but unresponsive container.

After restart, the worker's next loop iteration will reap any stale locks it
finds, returning orphaned `running` jobs to `pending` within 60 seconds.

To observe the worker after restart:

```bash
docker compose logs -f parse-worker
docker compose logs -f index-worker
```

Look for the startup log line `<worker-type> worker started` to confirm the
process is running, followed by periodic heartbeat and queue-depth updates.

Each log line for a job event includes:
- `worker_type`, `job_id`, `document_id`, `source_id`
- `attempt` (1-based), `outcome` (done/failed/dlq/retry)
- `duration_ms`, `correlation_id`

---

## Troubleshooting Playbook

### Worker stopped

**Signals**: `time() - tomorrowland_worker_heartbeat_timestamp_seconds > 120`

1. Check container status: `docker compose ps parse-worker translate-worker embed-worker index-worker intelligence-worker alert-worker enrich-worker`
2. Check recent logs: `docker compose logs --tail=100 parse-worker`
3. If the container is stopped: `docker compose restart parse-worker`
4. If it exits immediately, check for config/DB connection errors in the logs
   and verify `DATABASE_URL` in `.env`.

---

### Queue backlog growing

**Signals**: `tomorrowland_pipeline_queue_depth{status="pending"}` rising,
RabbitMQ queue depth growing (check `GET /admin/rabbit/queues`).

1. Confirm workers are running and heartbeating.
2. Check `worker_loop_errors_total` for loop errors.
3. Check that resource limits are not throttling the worker.
4. Scale workers if capacity is genuinely saturated:
    `docker compose up -d --scale parse-worker=2`

---

### Retry count increasing

**Signals**: `rate(tomorrowland_pipeline_jobs_retried_total[5m])` non-zero and rising.

1. Check which `job_type` is retrying: filter by `job_type` label.
2. For `process_document` retries: check Qdrant and Meilisearch health.
3. For `translate_document` retries: check LibreTranslate health.
4. For `intelligence_document` or `alert_document` retries: check Ollama or
   alert-matcher configuration respectively. These are best-effort; a sustained
   retry pattern indicates the downstream dependency is not configured.
5. Check worker logs for the exception class driving retries.
6. If a dependency is recovering, retries will clear automatically once it is
   healthy.

---

### Dead-letter count increasing

**Signals**: `increase(tomorrowland_pipeline_jobs_dead_lettered_total[1h]) > 0`

Dead-lettered jobs have exhausted all retry attempts and will not be
automatically retried.

1. Identify the failing `job_type` and `worker_type` from label values.
2. Check worker logs for the last error before dead-letter.
3. Fix the root cause (upstream service, bad document, config issue).
4. Re-queue affected jobs via the admin API:
   `POST /admin/jobs/<job-id>/retry`
5. Monitor `_succeeded_total` to confirm re-queued jobs complete.

---

### Stale locks repeatedly reaped

**Signals**: `rate(tomorrowland_pipeline_jobs_stale_lock_reaped_total[5m]) > 0`
sustained outside of a deploy window.

1. Check `worker_loop_errors_total` — sustained loop errors cause crash/restart
   cycles that produce stale locks.
2. Check container restart counts: `docker compose ps` (look at the `STATUS`
   column for recent restarts).
3. If a specific job is repeatedly crashing the worker, it will eventually
   exhaust its `max_attempts` and dead-letter; monitor
   `_dead_lettered_total`.

---

### Loop errors increasing

**Signals**: `rate(tomorrowland_worker_loop_errors_total[5m]) > 0`

Loop errors are unhandled exceptions outside of the per-job retry/dead-letter
path — typically infrastructure failures (DB connection lost, unexpected OS
errors).

1. Check logs for the full traceback: `docker compose logs -f parse-worker`
2. The `error_type` label gives the Python exception class for alerting.
3. Loop errors cause a `poll_interval` sleep before retrying; they do not
   immediately crash the worker, but a sustained rate indicates instability.

---

### Job duration p95/p99 high

**Signals**:
```promql
histogram_quantile(0.95,
  rate(tomorrowland_pipeline_job_duration_seconds_bucket[10m])
) > 30
```

1. Filter by `stage` to isolate which worker is slow.
2. For `parse`: check extraction time for large documents.
3. For `embed`: check Ollama embedding latency
   (`tomorrowland_ollama_duration_seconds`).
4. Very large documents will naturally fall in higher histogram buckets; check
   `tomorrowland_pipeline_document_bytes` for document size distribution.

---

## See Also

- `src/services/pipeline/parse_worker.py` — parse stage handler
- `src/services/pipeline/translate_worker.py` — translate stage handler
- `src/services/pipeline/embed_worker.py` — embed stage handler
- `src/services/pipeline/index_worker.py` — index stage handler
- `src/services/pipeline/intelligence_consumer.py` — intelligence stage handler
- `src/services/pipeline/alert_consumer.py` — alert stage handler
- `src/services/pipeline/enrich_worker.py` — enrich stage handler
- `src/shared/metrics.py` — `MetricsRegistry` with all metric definitions
- `docs/operations/production-compose.md` — Compose service layout
- `docs/operations/air-gapped-deployment.md` — offline deployment guide
- Issue #68 — Grafana dashboard panels and Prometheus alert rules (companion to this guide)
