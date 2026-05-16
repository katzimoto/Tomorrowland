# #210 Kafka-backed pipeline transport recommendation

> Status: planning only — no implementation
> Branch: `claude/plan-kafka-pipeline-transport-D1DZC`
> Depends on: #209 (pipeline_jobs schema)
> Blocks: #213, #214, #215, #216

---

## Verdict

**Recommended architecture: DB-only for Phase 1 (#209), with a pre-wired
`JOB_QUEUE_BACKEND` toggle for an optional Hybrid DB + Kafka wake-up event in
Phase 2.**

Do not introduce a Kafka producer for pipeline jobs in the first implementation.
Do not use Kafka-only under any phase.

---

## Why this fits Tomorrowland

1. **Redpanda is already mandatory.** Both `docker-compose.yml` and
   `docker-compose.airgap.yml` include the Redpanda service without a Compose
   profile gate. There is no "Kafka-free" deployment today. Adding an optional
   Kafka wake-up event in Phase 2 does not increase the infrastructure footprint.

2. **No Python Kafka client is installed.** `pyproject.toml` contains no
   `confluent-kafka`, `aiokafka`, or equivalent dependency. The existing
   `NiFiKafkaDrain` uses a Protocol-based consumer interface satisfied by
   in-process fakes in tests. Adding a producer for Phase 2 requires one new
   dependency (`confluent-kafka` or `aiokafka`), but Phase 1 needs none.

3. **DB polling is safe at this scale.** Document indexing workloads are
   low-frequency (tens to hundreds per sync, not thousands per second).
   `SELECT … FOR UPDATE SKIP LOCKED` on a small `pipeline_jobs` table is
   sufficient and well-understood in the team's existing SQLAlchemy Core stack.

4. **Phase 1 must not block air-gapped deploys.** Redpanda already ships in the
   air-gap archive, so a Phase 2 Kafka wake-up event requires no new image
   bundling work. But Phase 1 should not require a running broker at all, even
   though one is present.

5. **The existing plan already reserved this path.** `pipeline-jobs-runtime-split.md`
   documents `--queue-type db|kafka` and `JOB_QUEUE_BACKEND=db|kafka`. Phase 2
   implements the `kafka` branch of that toggle without changing any
   repository interfaces.

---

## Current Kafka/Redpanda usage found

| Component | Location | Role |
|-----------|----------|------|
| Redpanda broker | `docker-compose.yml`, `docker-compose.airgap.yml` | NiFi event delivery; hard dependency in all compose stacks |
| `NiFiKafkaDrain` | `src/services/pipeline/kafka_consumer.py` | Drains NiFi events from a Kafka topic; creates documents and hands off to `PipelineWorker.process_document` |
| `KafkaConsumer` Protocol | `src/services/pipeline/kafka_consumer.py:39` | Fake-testable consumer interface; no live Kafka client imported |
| `DatabaseDeadLetterSink` | `src/services/pipeline/kafka_consumer.py:69` | Writes sanitized NiFi event failures to the `dlq` table |
| `DocumentEvent`, `IntelligenceEvent` | `src/shared/events.py` | Pydantic event models for the `documents.raw` and `documents.intelligence` conceptual topics |
| `kafka_broker` config | `src/shared/config.py:21` | `KAFKA_BROKER` env var, default `kafka:9092`; already in Settings |
| `INGEST_MODE` config | `src/shared/config.py:48` | `hybrid | watch | poll` — controls folder/NiFi ingestion mode, unrelated to job queue |

**Key gap:** No Kafka producer exists anywhere in the Python codebase. The
existing consumer is Protocol-based with no live `confluent-kafka` or `aiokafka`
import. Any Phase 2 producer must add a client library and a concrete
implementation.

**Scope boundary:** Current Kafka usage is entirely in the NiFi ingestion path
(inbound events → document creation). It does not touch pipeline job dispatch,
worker lifecycle, retry, or DLQ for the post-creation processing pipeline.

---

## Options compared

### A. DB-only queue

Workers poll `pipeline_jobs` on a configurable interval (default 2 s for
pipeline, 5 s for slow). Claims use `SELECT … FOR UPDATE SKIP LOCKED`.

**Pros**
- No new dependencies or infrastructure changes.
- ACID semantics: enqueue and job state update are in the same transaction.
- SQL inspection for operators (`psql` or admin API).
- Full compatibility with the existing SQLAlchemy Core repository pattern.
- Rollback is a single Alembic downgrade.
- Worker can restart at any time without offset state loss.
- Idempotent by construction: `SKIP LOCKED` prevents double-claim.

**Cons**
- Polling adds latency (0–poll_interval seconds before a job is noticed).
- Poll frequency creates a small DB read load; acceptable at document
  indexing scale but not at high-throughput event stream scale.
- No push notification; a new job is not immediately visible to an idle worker.

**Failure behavior**
- Worker crashes mid-job: row stays `status = 'running'`. A stale-job sweep
  on worker startup resets rows older than `claimed_at + timeout` to `pending`.
- DB unavailable: workers idle and retry; no job is lost or duplicated.
- Backpressure: natural; workers only claim when they have capacity.

**Operational simplicity:** High. Standard SQL tooling.

**Testability:** High. In-process SQLite `migrated_engine` fixture covers all paths.

**Scaling limit:** Suitable for single-digit workers processing hundreds of
jobs per minute. Throughput ceiling is reached when `SKIP LOCKED` contention on
`pipeline_jobs` becomes the bottleneck, which is far beyond document indexing
volumes.

---

### B. Kafka-only queue

Job state lives exclusively in Kafka partitions. Workers are Kafka consumer
group members. No `pipeline_jobs` DB table. Job status is derived from offset
position.

**Pros**
- Near-zero latency from publish to consume.
- Natural fan-out to multiple workers via consumer group partitioning.
- High throughput ceiling.

**Cons**
- No durable job state: retries require Kafka retry topics, not a simple DB
  update. Retry semantics are complex (exponential backoff via scheduled
  topics or delayed re-publish).
- No admin visibility without a separate Kafka UI or custom tooling. The
  `GET /admin/jobs` API cannot be built without a secondary store.
- DLQ is a Kafka DLQ topic; requires operator Kafka expertise to inspect and
  re-process.
- Duplicate delivery is inherent (at-least-once). Workers must deduplicate,
  but without a DB job row there is nothing to check against.
- `confluent-kafka` (C extension) must be added as a runtime dependency and
  included in the airgap image.
- Consumer offset management across restarts requires a stable `group.id`
  and careful commit timing.
- `KAFKA_BROKER` must be available at startup; any brief Redpanda outage
  during a sync call loses jobs unless a DB fallback is added — at which
  point it is no longer Kafka-only.

**Failure behavior**
- Kafka broker unavailable: jobs published to Kafka are lost unless buffered
  separately. No fallback. Unacceptable for durable job semantics.
- Consumer crash before offset commit: message is redelivered. Without a DB
  job row there is no idempotency guard; the document pipeline may run twice.

**Admin visibility:** Poor without a secondary store or Kafka UI.

**Data-loss risk:** High if Redpanda is restarted, misconfigured, or its
topic retention expires.

**Verdict: rejected.** Kafka-only is not suitable for durable job semantics
at Tomorrowland's scale and operational profile.

---

### C. Hybrid DB + Kafka wake-up event

The `pipeline_jobs` table is the authoritative source of job state. When a job
is enqueued, a lightweight wake-up event is published to Kafka. Workers consume
the wake-up event and immediately attempt to claim the DB row. The DB polling
loop runs in parallel as a fallback for stranded jobs (Kafka missed or down).

**Pros**
- Sub-second latency for the common path (Kafka delivers before the poll interval).
- DB remains the authoritative state store: retries, DLQ, admin visibility, and
  rollback all work identically to DB-only.
- Duplicate Kafka delivery is safe: worker claims the DB row with
  `SELECT … FOR UPDATE SKIP LOCKED`; a second worker seeing the same event
  finds the row already claimed.
- Kafka unavailable: DB polling fallback ensures no job is stranded.
- No large payloads in events: only IDs are published.
- Fits existing Redpanda deployment with no new services.

**Cons**
- Adds a Kafka producer dependency (`confluent-kafka` or `aiokafka`).
- The outbox problem: if Kafka publish fails after the DB commit, the wake-up
  is lost (handled by DB polling fallback, but introduces a latency tail).
- Worker must subscribe to a Kafka topic *and* run a DB poller; slightly more
  complex runner loop.
- Topic offset management, consumer group naming, and partition count must be
  decided and documented.

**Failure behavior**
- Kafka publish fails after DB commit: DB polling detects the pending job
  within `poll_interval`. No job loss; tail latency only.
- Kafka broker unavailable: DB polling fallback covers all jobs; throughput
  and latency degrade to polling-baseline.
- Worker consumes event but crashes before marking job complete: DB row stays
  `running`; stale-job sweep reclaims it. Offset is not committed until job
  is durably complete.
- Kafka sends duplicate event: second worker attempts `SELECT … FOR UPDATE SKIP LOCKED`;
  row is already claimed; worker skips without processing.
- DB commit fails after Kafka publish: Kafka event references a job that does
  not exist. Workers attempt DB claim, find no row, log a warning, skip.

**Idempotency:** Strong. The DB `SKIP LOCKED` claim is the single gate.

**Backpressure:** Worker capacity limits DB claims regardless of Kafka delivery
rate. Workers that are saturated simply do not commit offsets; the partition
lag grows until workers drain.

**Operational complexity:** Moderate. Adds a topic, a consumer group, and an
optional producer. All job visibility and retry tooling remains SQL-based.

---

## Recommended #209 implementation path

### Phase 1 — DB-only durable job queue (implement in #209 + #213–#216)

Build the `pipeline_jobs` table and the full `JobQueue` repository layer backed
exclusively by DB polling. Workers use `SELECT … FOR UPDATE SKIP LOCKED`.
`JOB_QUEUE_BACKEND` defaults to `db`. No Kafka producer is written. No
`confluent-kafka` dependency is added.

Deliverables:
- Alembic migration: `pipeline_jobs` table + indexes (owned by #209).
- `JobQueue` repository: `enqueue`, `claim`, `ack`, `nack`, `list_by_status` (owned by #210 per the plan).
- Async `sync-now` API: enqueue instead of inline run (owned by #213).
- `pipeline-worker` and `slow-worker` runners with DB polling (owned by #214, #215).
- Retry, DLQ, and metrics (owned by #216).

All of Phase 1 must pass with `KAFKA_BROKER` unset or Redpanda stopped. No
pipeline job must depend on a live broker.

### Phase 2 — Hybrid Kafka wake-up event (follow-up issue, not part of #209–#216)

Add an optional Kafka producer inside the `enqueue` path. When
`JOB_QUEUE_BACKEND=kafka` (or `hybrid`), the `JobQueue.enqueue` method also
publishes a `pipeline.document.process.v1` event to Kafka after the DB insert
commits. Workers subscribe to the topic and attempt DB claims on event receipt.
DB polling runs in parallel as the fallback.

Phase 2 does not change repository interfaces or the DB schema. It is a thin
layer on top of Phase 1.

**Do not build Phase 2 inside the `feature/pipeline-jobs` track.** Open a
separate issue after Phase 1 ships and the team has operational experience with
DB-only polling.

### Phase 3 — (optional, future) Kafka consumer group auto-scaling

If throughput demands grow, add Kafka consumer group rebalancing to distribute
work across dynamically scaled worker replicas. Requires Phase 2. Not needed
now.

---

## Event schema

For Phase 2, if a Kafka wake-up event is added:

```json
{
  "event_type": "pipeline.document.process.v1",
  "job_id": "<uuid>",
  "doc_id": "<uuid>",
  "source_id": "<uuid>",
  "job_type": "pipeline",
  "correlation_id": "<uuid>",
  "created_at": "<RFC3339>"
}
```

**Constraints enforced at serialization time:**
- `job_id`, `doc_id`, `source_id`, `correlation_id`: UUID strings only. No
  other fields from the `pipeline_jobs` row are included.
- `job_type`: enum string (`pipeline` or `slow`), never a raw config value.
- `created_at`: RFC 3339 UTC timestamp.
- **Forbidden fields:** document content, extracted text, file path, connector
  credentials, source configuration, translation output, raw exception messages,
  user IDs, JWT values.

If a field validation error occurs during serialization, the event is dropped
and the job proceeds as DB-only (fallback path). A counter
`tomorrowland_kafka_publish_failures_total` is incremented; no exception is
raised.

---

## Topic names

| Topic | Purpose | Retention |
|-------|---------|-----------|
| `pipeline.document.process.v1` | Wake-up events for pipeline-worker jobs | 24 h or until consumed; short because DB is authoritative |
| `pipeline.document.slow.v1` | Wake-up events for slow-worker jobs | 24 h or until consumed |

No retry topic is needed: retries are managed by the DB (`next_attempt_at`
backoff). No outbox topic is needed: DB insert is the durable record.

**Existing NiFi topics** (`documents.raw`, `documents.intelligence` as
referenced in `shared/events.py`) are unchanged and unrelated to pipeline job
wake-up events.

---

## Idempotency and duplicate handling

Workers handle all scenarios using the `SELECT … FOR UPDATE SKIP LOCKED` DB
claim as the single gate:

| Scenario | Worker action |
|----------|--------------|
| Duplicate Kafka delivery (at-least-once) | Second worker attempts DB claim; `SKIP LOCKED` returns no row; worker skips silently |
| Event for already-running job | DB row has `status = 'running'`; not returned by the claim query (which filters `status = 'pending'`); skip |
| Event for already-succeeded job | DB row has `status = 'done'`; not claimable; skip |
| Event for dead-lettered job | DB row has `status = 'dlq'`; not claimable without an explicit admin retry; skip |
| Event referencing missing DB job | `SELECT` returns no row; log a warning with `job_id` only; skip; offset committed |
| Stale running job (worker crashed) | Stale-job sweep on worker startup resets `status = 'running'` rows older than `claimed_at + stale_timeout` back to `pending` |
| Kafka consumer restart | Consumer resumes from last committed offset; any unprocessed events are re-delivered; idempotency gate handles them |

Offset commits happen only **after** the DB `ack` (status → `done` or `dlq`) is
committed. A worker that crashes between DB `ack` and Kafka commit will
re-receive the event on restart, attempt a DB claim, find the row
already done/dlq, and skip.

---

## Retry / DLQ ownership

**DB owns all retry and DLQ state.** Kafka retry topics are not used.

| Concern | Owner | Mechanism |
|---------|-------|-----------|
| Retry count | `pipeline_jobs.attempts` | Incremented on each `nack` |
| Max attempts | `pipeline_jobs.max_attempts` (default 3) | Configurable per-job-type at enqueue time |
| Backoff schedule | `pipeline_jobs.next_attempt_at` | `now() + 2^attempts seconds` |
| DLQ transition | Worker `nack` with `is_terminal=True` | Sets `status = 'dlq'`, `dlq_at`, `dlq_reason` |
| Error summary | `pipeline_jobs.error` | Sanitized exception class + message; no stack trace; no document content |
| DLQ inspection | Admin API | `GET /admin/jobs?status=dlq` |
| Manual re-queue | Admin API | `POST /admin/jobs/{job_id}/retry` |
| DLQ alert | Prometheus | `tomorrowland_dlq_depth` gauge → existing `TomorrowlandDlqPending` rule |

**Error sanitization rule:** `dlq_reason` and `error` columns store only
exception class name + truncated message (≤ 256 chars). No stack traces, no
document content, no connector credentials, no file paths beyond what is already
in structured correlation logs.

---

## Transactional outbox decision

**Phase 1: no outbox.** DB insert is the durable record. No Kafka publish
occurs. There is no publish-fail-after-commit risk.

**Phase 2: direct publish after DB commit (simple hybrid), not a formal
transactional outbox table.**

Rationale: a full transactional outbox table (write event to DB inside the
same transaction, separate relay process reads and publishes) adds schema
complexity and a second polling process. For Tomorrowland's use case, the
DB polling fallback already handles the case where Kafka publish fails —
jobs will be processed within `poll_interval` seconds regardless. The latency
tail (DB polling kicks in instead of Kafka) is acceptable; message loss is not
possible because DB is authoritative.

Failure mode coverage for Phase 2:

| Failure | Outcome |
|---------|---------|
| DB commit succeeds, Kafka publish fails | Job sits pending; DB poller picks it up within `poll_interval`; no loss |
| Kafka publish succeeds, DB commit fails | Kafka event references a non-existent job; worker finds no DB row; logs warning and skips; no phantom job |
| Kafka unavailable during sync | `enqueue` publishes to DB only; DB poller handles the job; system degrades gracefully to DB-only mode |
| Worker consumes event but crashes before marking job complete | Offset not committed; event redelivered on restart; idempotency gate handles it |

If the team later decides that polling latency is unacceptable and a formal
outbox relay with sub-second guaranteed delivery is needed, the outbox table can
be introduced in a dedicated migration without touching the existing schema.

---

## Worker design

### Phase 1: DB polling worker (one runner supports both modes)

Both `pipeline-worker` and `slow-worker` run the same loop structure:

```
loop:
  job = job_queue.claim(job_type=self.type, timeout=stale_timeout)
  if job is None:
    sleep(poll_interval)
    continue
  try:
    process(job)
    job_queue.ack(job.id)
  except TransientError:
    job_queue.nack(job.id, is_transient=True)  # backoff, no attempt count
  except Exception:
    job_queue.nack(job.id, is_transient=False)  # counts toward max_attempts
```

### Phase 2: hybrid worker (DB poll + Kafka consumer in same runner)

The runner adds a Kafka consumer thread (or coroutine) that feeds a shared
in-process queue. The DB polling loop reads from both:

```
on kafka_event(event):
  wake_queue.put(event.job_id)  # hint only; DB claim is the gate

loop:
  # Prioritize Kafka hints, fall back to DB poll on timeout
  job_id = wake_queue.get(timeout=poll_interval) or None
  job = job_queue.claim(job_type=self.type, job_id=job_id)
  ...
  if kafka_event:
    consumer.commit(kafka_event)  # only after DB ack
```

A single process handles both paths. No separate Kafka consumer service is
needed.

**Offset commit timing:** Kafka offset is committed only after `job_queue.ack`
returns successfully. This guarantees at-least-once processing in the DB before
the Kafka partition advances.

**Safe shutdown:**
1. Stop accepting new Kafka events (pause consumer).
2. Finish any in-progress job (up to `shutdown_timeout`, default 30 s).
3. Commit the offset for the completed job.
4. Exit with code 0.
5. On `SIGKILL` or timeout expiry: offset is not committed; event is
   redelivered on next startup; idempotency gate handles it.

**Multiple workers / no double processing:** `SELECT … FOR UPDATE SKIP LOCKED`
is the exclusive lock. Multiple workers may receive the same Kafka wake-up
event; only one will win the DB claim. Others see no row and skip.

---

## Compose / airgap / operations impact

### Current state

Redpanda is in the default service set for both `docker-compose.yml` and
`docker-compose.airgap.yml`. It is not gated behind a Compose profile. The
`KAFKA_BROKER` env var defaults to `kafka:9092` in all environments.

### Phase 1 impact (DB-only)

- **No changes to Compose files.** Workers are added as a `workers` profile
  service per the existing plan (workers start only when `--profile workers` is
  passed, or after Phase 1 is fully merged into `feature/pipeline-jobs`).
- **Kafka is not a startup dependency for workers.** Worker `depends_on`
  should include `postgres`, `elasticsearch`, `qdrant`, but NOT `kafka`.
- **Local dev without Kafka:** `docker compose up` (without `--profile workers`)
  starts no workers; sync-now enqueues to DB; jobs stay pending until a worker
  is started.
- **Troubleshooting stuck jobs:** `SELECT * FROM pipeline_jobs WHERE status IN ('running', 'dlq')` via psql or admin API.

### Phase 2 impact (Hybrid)

- Workers gain a `depends_on: kafka` entry (soft startup dependency, not
  `service_healthy` required — workers must tolerate broker unavailability).
- One new env var: `JOB_QUEUE_BACKEND=hybrid` (or `kafka`).
- Topic creation: `pipeline.document.process.v1` and `pipeline.document.slow.v1`
  must exist before workers start. Add `rpk topic create` to an init container
  or operator runbook; do not create topics inside Python startup code.
- **Airgap:** Redpanda is already bundled. No new images required. The operator
  runbook (`docs/operations/air-gapped-deployment.md`) gains a note about topic
  pre-creation.
- **Running without Kafka:** set `JOB_QUEUE_BACKEND=db`; workers behave exactly
  as Phase 1.

### Troubleshooting guide

| Symptom | Check | Fix |
|---------|-------|-----|
| Jobs stuck in `pending` | Are workers running? | `docker compose --profile workers up` |
| Jobs stuck in `running` | Worker crashed? | Stale-job sweep runs on worker restart; or manually: `UPDATE pipeline_jobs SET status='pending', claimed_at=NULL WHERE status='running' AND claimed_at < now() - interval '10 minutes'` |
| Jobs in `dlq` | DLQ reason | `GET /admin/jobs?status=dlq`; admin retry via `POST /admin/jobs/{id}/retry` |
| Kafka publish lag (Phase 2) | `tomorrowland_kafka_publish_failures_total` | Check broker health; DB polling fallback is active; no jobs are lost |
| No wake-up events delivered (Phase 2) | Consumer group lag | `rpk group describe <group>` |

---

## Security and data-leakage constraints

These constraints apply to all phases:

1. **Events contain IDs only.** `job_id`, `doc_id`, `source_id`,
   `correlation_id` are UUID strings. No filenames, titles, content, or
   connector config fields.
2. **`dlq_reason` and `error` columns are sanitized.** Exception class name
   + truncated message only. No stack traces in the DB or in events.
3. **Kafka events are not logged in full.** Workers log `job_id` and `job_type`
   only when consuming an event. `doc_id` and `source_id` are logged at `DEBUG`
   level only.
4. **No connector credentials in events or logs.** Source config is loaded from
   the DB by `source_id`; credentials are never republished.
5. **`NiFiKafkaDrain` is unaffected.** The existing NiFi event ingestion path
   (`src/services/pipeline/kafka_consumer.py`) is separate from pipeline job
   dispatch and must not be modified in this track.
6. **Topics are plaintext (PLAINTEXT://kafka:9092) in the default stack.**
   If TLS is required, it is an operator responsibility via `KAFKA_BROKER`
   override; the Python client must not hardcode the protocol.

---

## Tests to require

All tests must pass without a live Kafka broker. Tests requiring Kafka behavior
use the Protocol-based fake consumer/producer pattern already established in
`tests/unit/test_kafka_consumer.py`.

| Test | Assertion |
|------|-----------|
| `test_pipeline_event_contains_ids_only` | Serialized `pipeline.document.process.v1` event has no text, path, title, credentials, or exception messages; only UUID strings and a timestamp |
| `test_duplicate_event_is_safe` | Two workers receive the same wake-up event; only one successfully claims the DB row; the second finds no claimable row and returns without processing |
| `test_kafka_publish_failure_does_not_lose_job` | `enqueue` inserts DB row; Kafka producer raises; DB row remains `pending`; DB poll loop claims and processes it |
| `test_invalid_event_schema_does_not_kill_worker_loop` | Worker receives a malformed event (missing fields, wrong types); worker logs a warning, skips, commits offset; loop continues |
| `test_offset_committed_only_after_db_ack` | Worker processes event; Kafka `commit` is called only after `job_queue.ack` returns; if `ack` raises, `commit` is not called |
| `test_kafka_unavailable_sync_creates_db_job` | `sync-now` is called with Redpanda stopped (producer raises on connect); `pipeline_jobs` row is created; response returns `{"queued": 1}` |
| `test_db_polling_fallback_processes_job_without_kafka` | Worker starts with `JOB_QUEUE_BACKEND=db` (no Kafka); job is enqueued; worker claims and completes it via polling |
| `test_no_raw_content_in_events_or_logs` | Log output captured during a full pipeline run contains no `content_english`, raw file text, source passwords, or LDAP credentials |
| `test_stale_running_job_reset_on_startup` | Worker finds a `running` row with `claimed_at` older than `stale_timeout`; resets it to `pending`; processes it successfully |
| `test_event_for_missing_db_job_is_skipped` | Worker receives a wake-up event whose `job_id` does not exist in `pipeline_jobs`; logs a warning; skips; commits offset; loop continues |

---

## Follow-up issues to create

Open after #216 ships and DB-only polling is running in production:

- **#2xx — Phase 2: Hybrid Kafka wake-up event for pipeline jobs**
  Add `confluent-kafka` dependency, `JobQueue.enqueue` Kafka publish path,
  hybrid worker loop, `JOB_QUEUE_BACKEND=hybrid` mode, topic pre-creation docs.
  Target: `feature/pipeline-jobs` or a new `feature/pipeline-kafka` branch.

---

## opencode implementation prompt for Phase 1 (DB-only job queue)

Paste-ready prompt for the implementer picking up #209 (schema) and the
`JobQueue` repository layer:

```
Implement Phase 1 of the pipeline job queue for Tomorrowland.

Context:
- Plan: docs/implementation/pipeline-jobs-runtime-split.md
- Transport recommendation: docs/implementation/issue-210-kafka-transport-recommendation.md
- Feature branch: feature/pipeline-jobs
- No Kafka producer. No confluent-kafka dependency. DB polling only.

Step 1 — Migration (#209)
Create migrations/versions/<timestamp>_add_pipeline_jobs.py with upgrade() and
downgrade(). Schema from the plan (Section 3):

  pipeline_jobs: id UUID PK, job_type TEXT, doc_id UUID, source_id UUID,
  status TEXT CHECK('pending','running','done','failed','dlq'), attempts INT,
  max_attempts INT, created_at TIMESTAMPTZ, claimed_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ, error TEXT, dlq_at TIMESTAMPTZ, dlq_reason TEXT,
  next_attempt_at TIMESTAMPTZ

  Indexes:
    idx_pipeline_jobs_claim ON (job_type, status, next_attempt_at) WHERE status='pending'
    idx_pipeline_jobs_source ON (source_id, status)

  downgrade(): drops pipeline_jobs and its indexes.

Step 2 — JobQueue repository layer
Create src/services/pipeline/job_queue.py with:

  class JobQueue:
    def enqueue(self, *, job_type, doc_id, source_id, correlation_id,
                max_attempts=3) -> UUID
    def claim(self, *, job_type, stale_timeout_seconds=600) -> PipelineJob | None
      # SELECT … FOR UPDATE SKIP LOCKED
      # Also reset stale running rows (claimed_at < now() - stale_timeout)
    def ack(self, job_id: UUID) -> None
      # status='done', completed_at=now()
    def nack(self, job_id: UUID, *, error: str, is_transient: bool) -> None
      # is_transient=True: reset to pending, no attempt count increment
      # is_transient=False: increment attempts; if >= max_attempts set dlq
      # backoff: next_attempt_at = now() + 2^attempts seconds
    def list_by_status(self, *, status, source_id=None, limit=50) -> list[PipelineJob]

  PipelineJob: Pydantic BaseModel matching the table columns.

  Constraints (from recommendation doc):
  - Use shared.db.db_uuid() for all UUID binding.
  - Use SQLAlchemy bound parameters; no string interpolation.
  - dlq_reason truncated to 256 chars; no stack traces; no document content.
  - All methods accept a Connection or Engine parameter (pass engine.begin()).

Step 3 — Tests
Create tests/unit/test_job_queue.py and tests/integration/test_job_queue.py.
Cover: enqueue creates row, claim returns pending job, claim skips running rows,
ack marks done, nack increments attempts and sets backoff, nack at max_attempts
moves to dlq, stale running row is reset by claim, two workers claim different jobs,
duplicate claim returns None for second worker.

Conventions:
- from __future__ import annotations at top of every file.
- ruff line length 100, mypy strict.
- No SQLModel. SQLAlchemy Core only.
- Migration must have both upgrade() and downgrade().
- Do not touch kafka_consumer.py, worker.py, or slow_worker.py.
```

---

## Context Loaded

- `AGENTS.md`
- `docs/agents/token-efficiency.md`
- `docs/implementation/pipeline-jobs-runtime-split.md` (primary plan)
- `src/services/pipeline/kafka_consumer.py`
- `src/services/pipeline/worker.py`
- `src/services/pipeline/slow_worker.py`
- `src/shared/events.py`
- `src/shared/config.py`
- `docker-compose.yml`
- `docker-compose.airgap.yml`
- `migrations/versions/1914954ae9d7_add_dlq_and_audit_tables.py`
- `migrations/versions/9a65b7c3d4e5_allow_event_dlq_without_document.py`
- `tests/unit/test_kafka_consumer.py`
- `CHANGELOG.md` (relevant lines only)

## Context Skipped

- `frontend/` — no frontend work in this track
- `spec.md`, `spec-v4.pdf` — not authorized
- Other implementation phase docs (phase-00 through phase-10f)
- OCR/RAG/translation docs
- `docs/design/` specs unrelated to pipeline jobs

## Token Efficiency Notes

- Used `rg` before opening files: yes
- Read more than one plan: no (only `pipeline-jobs-runtime-split.md`)
- Read broad source areas: no (targeted to pipeline, events, config, compose)
