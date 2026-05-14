# Pipeline Worker Operations Guide

> **Status**: planning scope — worker containers do not exist yet. This document
> defines operator expectations for the `feature/pipeline-jobs` track (#235).
> Update this doc when #214, #215, and #216 land.

---

## Overview

Tomorrowland's ingestion pipeline is split across three worker roles:

| Role | Process | Current state |
|------|---------|---------------|
| **api** | FastAPI / Uvicorn (`services.api.asgi:app`) | Running |
| **pipeline-worker** | Fast-path indexing worker | Planned (#214) |
| **slow-worker** | High-quality translation enrichment | Planned (#215) |
| **vector-worker** | Dedicated vector re-indexing (future) | Deferred |

Today, pipeline and slow enrichment run synchronously inside the API process.
After the `feature/pipeline-jobs` track merges, they run as separate
long-running worker containers that claim jobs from a PostgreSQL job queue.

---

## Service Roles

### api

The API service handles all HTTP traffic: authentication, document access,
admin operations, search, RAG, preview, download, and job enqueueing.

After the pipeline-jobs track lands, the API no longer runs pipeline work
inline. `POST /admin/ingestion/{source_id}/sync-now` scans the source and
enqueues jobs; workers perform extraction, translation, chunking, and indexing.

The API's Prometheus endpoint (`GET /metrics`) continues to expose all existing
metrics. Worker metrics are exposed on separate per-worker health ports.

### pipeline-worker

Processes `job_type = 'pipeline'` jobs from the `pipeline_jobs` table. One job
corresponds to one document. The worker runs the full ingestion pipeline:
extraction → translation (fast) → chunking → Elasticsearch indexing → Qdrant
vector indexing → intelligence → alert matching.

Vector indexing is soft-failure: if Qdrant is unavailable, the document is
still marked `done` for full-text search purposes.

### slow-worker

Processes `job_type = 'slow'` jobs. Re-translates documents with a
high-quality translation and re-indexes them in Elasticsearch and Qdrant.
Intended for off-peak enrichment after fast indexing completes.

The slow-worker creates translation versions (tracked in
`translation_versions`) so operators can see version history.

### vector-worker (future / deferred)

A future dedicated worker for vector re-indexing, re-embedding after model
changes, and batch Qdrant refresh. Not part of the `feature/pipeline-jobs`
track; tracked separately.

---

## Starting and Scaling Workers

### Starting with Docker Compose

Workers are defined under the `workers` Compose profile. The standard stack
does not start them unless the profile is active:

```bash
# Start API and infrastructure only (current default):
docker compose up -d

# Start everything including workers:
docker compose --profile workers up -d

# Start only workers (API must already be running):
docker compose --profile workers up -d pipeline-worker slow-worker
```

### Scaling worker concurrency

Each worker process can run multiple jobs concurrently. Set the environment
variable in `.env` or as a Compose override:

```bash
# Run 4 parallel pipeline jobs per worker container:
PIPELINE_WORKER_CONCURRENCY=4

# Run 2 parallel slow enrichment jobs per worker container:
SLOW_WORKER_CONCURRENCY=2
```

For higher throughput, run multiple replicas of the worker container. Because
workers claim jobs with `SELECT … FOR UPDATE SKIP LOCKED`, multiple replicas
do not produce duplicate processing:

```bash
docker compose --profile workers up -d --scale pipeline-worker=3
```

### Checking worker health

Each worker serves a health endpoint on its configured port:

```bash
# Default ports (configure via PIPELINE_WORKER_HEALTH_PORT, SLOW_WORKER_HEALTH_PORT):
curl -fsS http://localhost:8001/health    # pipeline-worker
curl -fsS http://localhost:8002/health    # slow-worker
```

A healthy worker returns:

```json
{"status": "ok", "worker_type": "pipeline"}
```

### Stopping workers gracefully

Send SIGTERM to allow the worker to finish its current job before exiting:

```bash
docker compose --profile workers stop pipeline-worker
docker compose --profile workers stop slow-worker
```

Workers finish in-progress jobs (up to 30 seconds), then exit with code 0.
Jobs that were in-flight but not finished within the timeout are reset to
`pending` on next worker startup.

---

## Inspecting Queued, Retry, and Dead-Letter Jobs

All job inspection uses the admin API. Requires an admin JWT.

### Queue depth by status

```bash
# All jobs for a source:
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/admin/jobs?source_id=<uuid>"

# Only pending jobs:
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/admin/jobs?source_id=<uuid>&status=pending"

# Only DLQ jobs:
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/admin/jobs?status=dlq"
```

Response includes `total` and a `jobs` array with per-job status, attempts,
error, and timestamps.

### Single job status

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/admin/jobs/<job-id>"
```

### Re-queueing a dead-letter job

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/admin/jobs/<job-id>/retry"
```

This resets `status` to `pending`, clears `dlq_at` and `dlq_reason`, and
resets `attempts` to 0. The job will be claimed by the next available worker.

### Prometheus metrics

Workers expose job queue metrics at `GET /metrics` on the health port. The
key metrics for job inspection:

| Metric | Meaning |
|--------|---------|
| `tomorrowland_job_queue_depth{worker_type,status}` | Current jobs per status |
| `tomorrowland_dlq_depth{worker_type}` | DLQ backlog (feeds `TomorrowlandDlqPending` alert) |
| `tomorrowland_job_duration_seconds` | Job processing time histogram |
| `tomorrowland_job_attempts_total` | First attempts vs retries |

Grafana's **Ingestion and Indexing** dashboard will include DLQ trend panels
once the `feature/pipeline-jobs` track lands.

### Reading worker logs

Follow structured JSON logs from running workers:

```bash
docker compose logs -f pipeline-worker
docker compose logs -f slow-worker
```

Each log line for a job event includes:
- `worker_type`, `job_id`, `doc_id`, `source_id`
- `attempt` (1-based), `outcome` (done/failed/dlq/retry)
- `duration_ms`, `correlation_id`

---

## When Ollama, Qdrant, or Elasticsearch Are Unavailable

### Elasticsearch unavailable

- The pipeline-worker **cannot complete** a job when Elasticsearch is
  unavailable. Full-text indexing is required for `status = 'done'`.
- The worker logs the error, increments `attempts`, and sets
  `next_attempt_at` for exponential backoff retry.
- After `max_attempts` failures, the job moves to DLQ.
- The API continues to serve existing search results from the last successful
  index state.

**Operator action**: restore Elasticsearch health, then let workers retry
automatically. Re-queue DLQ jobs with `POST /admin/jobs/{job_id}/retry` if
they accumulated before the service recovered.

### Qdrant unavailable

- Qdrant indexing is **soft-failure** (best-effort). If Qdrant is unavailable,
  the pipeline-worker logs the vector indexing failure but still marks the job
  `done` after successful Elasticsearch indexing.
- Vector search results will be stale or incomplete until Qdrant recovers and
  a re-indexing pass runs.
- The future `vector-worker` (deferred) will handle targeted re-indexing
  after Qdrant recovers.

**Operator action**: restore Qdrant health. Re-trigger a source sync to
re-enqueue documents for vector indexing once the worker implementation is
confirmed to handle partial re-indexing. Track this gap until the vector-worker
is built.

### Ollama unavailable

- Intelligence features (summaries, tags, Q&A) run best-effort after
  successful indexing. Ollama unavailability does not block `status = 'done'`.
- Documents are fully text-searchable and vector-indexed without Ollama.
- The pipeline-worker logs the intelligence failure and continues.

**Operator action**: restore Ollama and pull the configured model
(`OLLAMA_MODEL`). Intelligence enrichment is not retroactively applied to
already-indexed documents; a future re-enrichment mechanism is tracked
separately.

### LibreTranslate unavailable

- Fast-path translation failure falls back to the original document text
  (existing behavior, preserved from the synchronous pipeline).
- The document is indexed without translation; `translation_quality` is `null`.
- The slow-worker will later attempt high-quality translation when scheduled.

**Operator action**: restore LibreTranslate. The slow-worker will re-process
pending high-quality translation jobs automatically.

---

## How Sync Counts Differ from Indexing Counts

After the `feature/pipeline-jobs` track lands, these two counts are distinct:

| Count | Where to find it | Meaning |
|-------|-----------------|---------|
| **Sync count** (`queued`) | `POST /admin/ingestion/{source_id}/sync-now` response | Documents discovered in this sync run and enqueued |
| **Indexed count** | `GET /admin/jobs?source_id=<uuid>&status=done` total | Jobs completed successfully |
| **Failed count** | `GET /admin/jobs?source_id=<uuid>&status=failed` total | Jobs that failed but may retry |
| **DLQ count** | `GET /admin/jobs?status=dlq` total | Jobs exhausted retries; need operator attention |

A sync that discovers 100 documents will show `"queued": 100`. After workers
run, the indexed count may be lower if some documents failed or are in DLQ.
The difference is always accounted for in the job status breakdown.

**Note (current behavior)**: Before this track lands, `sync-now` returns
`{"synced": N}` which reflects documents processed inline. There is no
separate DLQ count. After the track lands, operators gain fine-grained
visibility through the job status API.

---

## Air-Gapped Deployment Implications

### Job queue backend

The default job queue backend is PostgreSQL (`JOB_QUEUE_BACKEND=db`). No
additional services are required beyond what the current air-gapped runtime
already includes (Postgres, Elasticsearch, Qdrant, Ollama).

Kafka is **not required** for the job queue in this track. If Kafka is
present (for NiFi ingestion), workers can optionally use it as a transport
by setting `JOB_QUEUE_BACKEND=kafka`, but this is not the default.

### Image bundles

Worker containers use the same Python application image as the API. No new
base images are required. The `tomorrowland-images-<version>.tar` bundle
already included in the air-gapped release artifacts will include worker
image layers when they are added to the Compose file.

### Offline model availability

Pipeline workers call Ollama for intelligence enrichment. In air-gapped
environments, the Ollama model bundle must be loaded before workers start
attempting intelligence steps. Workers handle Ollama unavailability as
best-effort and do not fail the job, but intelligence enrichment will silently
produce no output until the model is loaded.

To load an Ollama model bundle offline:

```bash
bash scripts/tomorrowland-airgap.sh load-ollama /path/to/ollama-bundle.tar
```

### Compose profile in air-gapped mode

The `docker-compose.airgap.yml` file must include worker services under the
`workers` profile after the feature track lands. The air-gapped wrapper
(`scripts/tomorrowland-airgap.sh`) should expose a `start-workers` subcommand
or update the profile documentation when the feature is promoted. Track this
as a follow-up in #216 or a child issue.

---

## Troubleshooting

| Symptom | Likely cause | Action |
|---------|-------------|--------|
| Jobs stuck in `pending` indefinitely | Workers not running | `docker compose --profile workers ps`; start workers |
| Jobs stuck in `running` after restart | Abandoned claims from crash | Workers reset stale `running` rows on startup; wait for next poll or restart worker |
| DLQ depth growing | Persistent service failure | Check Elasticsearch/Qdrant health; re-queue after service recovery |
| Worker exits immediately | Config error or DB connection issue | `docker compose logs pipeline-worker`; verify `DATABASE_URL` in `.env` |
| `GET /health` returns 502 | Worker not started or crashed | Check `docker compose --profile workers ps` and logs |
| Sync count ≠ indexed count | Jobs still in flight, failed, or DLQ | `GET /admin/jobs?source_id=<uuid>` for status breakdown |
| Intelligence missing on indexed docs | Ollama unavailable during indexing | Restore Ollama, pull model; retroactive enrichment not automatic |

---

## See Also

- `docs/implementation/pipeline-jobs-runtime-split.md` — full implementation plan (#235)
- `docs/operations/production-compose.md` — Compose service layout and general operations
- `docs/operations/air-gapped-deployment.md` — offline deployment guide
- `src/services/pipeline/worker.py` — `PipelineWorker` class (current synchronous impl)
- `src/services/pipeline/slow_worker.py` — `SlowWorker` class (current synchronous impl)
