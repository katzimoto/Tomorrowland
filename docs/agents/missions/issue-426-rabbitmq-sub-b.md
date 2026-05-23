# OpenCode + DeepSeek Mission: Issue #426 — RabbitMQ Sub-B

## Identity and Repo

You are working on the Tomorrowland repo: `katzimoto/Tomorrowland`.

- **Child issue:** #426 — Publisher + DB State + sync-now + Admin Routes (Sub-B)
- **Parent tracker:** #432 — RabbitMQ stage-based job bus
- **Feature branch:** `feature/rabbitmq-job-bus`
- **PR target:** `feature/rabbitmq-job-bus` (NOT `main`)
- **Blocked by:** #425 (Sub-A) — must be merged into `feature/rabbitmq-job-bus` before starting

Verify Sub-A is merged before touching a line of code:
```bash
git fetch origin
git log origin/feature/rabbitmq-job-bus --oneline | head -10
# Must show: "feat(rabbit): RabbitClient with topology declaration…"
```

---

## Step 0 — Shared Memory (read before anything else)

1. `docs/memory/current-state.md` — find the 2026-05-23 RabbitMQ entry; check Sub-A status.
2. `docs/memory/handoffs.md` — any handoff from Sub-A agent targeting #426.
3. `docs/memory/decisions.md` — pipeline bus architecture decisions.

---

## Step 1 — Required Reading

1. `AGENTS.md`
2. `docs/agents/token-efficiency.md`
3. `docs/agents/coding-behavior.md`
4. GitHub issue #426 (full body)
5. GitHub issue #432 (skim — architecture overview only)
6. **Plan Tasks 6–9 only** (`docs/superpowers/plans/2026-05-23-rabbitmq-job-bus.md`, lines ~409–923)
7. `src/services/pipeline/jobs.py` — understand `PipelineJobRepository` before adding `set_rabbit_message_id`
8. `src/services/api/routers/admin/ingestion.py` — understand the sync-now loop before wiring publish

Use `graphify query "sync-now pipeline enqueue"` to trace the current ingestion flow. Use `rg` for symbol searches.

---

## Step 2 — Branch Setup

```bash
git fetch origin
git checkout feature/rabbitmq-job-bus
git pull --rebase origin feature/rabbitmq-job-bus
git status --short
```

---

## Goal

Implement Sub-B: the publish layer and admin visibility routes that sit between
the RabbitMQ client (Sub-A) and the consumers (Sub-C).

| Task | Deliverable |
|------|-------------|
| 6 | Migration: `stage TEXT`, `rabbit_message_id TEXT` columns on `pipeline_jobs` |
| 7 | `src/services/pipeline/publisher.py` + `set_rabbit_message_id` on `PipelineJobRepository` + 2 unit tests |
| 8 | sync-now publishes to RabbitMQ when `RABBITMQ_ENABLED=true`; existing tests still pass |
| 9 | `GET /admin/jobs`, `GET /admin/jobs/{job_id}` routes + 3 integration tests |

---

## Allowed Changes

```
migrations/versions/<ts>_pipeline_jobs_stage_rabbit.py   — new migration file
src/services/pipeline/jobs.py                            — add set_rabbit_message_id method
src/services/pipeline/publisher.py                       — new file
src/services/api/routers/admin/ingestion.py              — wire RabbitMQ publish (additive only)
src/services/api/routers/admin/jobs.py                   — new file
src/services/api/routers/admin/__init__.py               — register jobs router
tests/unit/test_publisher.py                             — new file
tests/integration/test_admin_jobs_routes.py              — new file
```

## Forbidden Changes

```
src/shared/rabbit.py                          — Sub-A owns this; read-only
src/services/pipeline/worker.py               — DO NOT TOUCH
src/services/pipeline/kafka_consumer.py       — DO NOT TOUCH
src/services/pipeline/consumer_base.py        — Sub-C scope
src/services/pipeline/parse_worker.py         — Sub-C scope
any frontend file                             — DO NOT TOUCH
spec.md, spec-v4.pdf                          — DO NOT READ OR TOUCH
```

---

## Implementation Detail

### Task 6 — Migration

Find the current Alembic head before writing the file:
```bash
uv run alembic heads
```

Create `migrations/versions/<timestamp>_pipeline_jobs_stage_rabbit.py`. Use the
printed revision as `down_revision`. Add two nullable `TEXT` columns:
- `stage` — current pipeline stage label (e.g. `"parsed"`, `"embedded"`)
- `rabbit_message_id` — RabbitMQ message UUID for observability

The plan (Task 6, lines ~411–466) has the exact migration body. Copy it verbatim,
substituting the real `down_revision`.

Verify round-trip:
```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```

### Task 7 — `DocumentPublisher` + `set_rabbit_message_id`

**`set_rabbit_message_id` in `jobs.py`:** Add after `mark_running_stage`. The
plan (lines ~529–545) has the exact implementation. It `UPDATE`s
`rabbit_message_id` and `updated_at` by `id`.

**`src/services/pipeline/publisher.py`:** `DocumentPublisher` wraps
`PipelineJobRepository` + `RabbitClient`. It has one public method per stage
(`publish_parse`, `publish_translate`, `publish_embed`, `publish_index`,
`publish_intelligence`, `publish_alert`), all delegating to `_publish(stage, ...)`.

Key invariant: `_publish` calls `rabbit.publish(routing_key, payload)` and
**only** calls `job_repo.set_rabbit_message_id` when the returned `message_id`
is truthy. When `RABBITMQ_ENABLED=false`, `rabbit.publish` returns `""` (no-op)
so no message ID is stored — the DB-poll path is unaffected.

Routing keys (must match exactly):
```
parse       → document.parse.requested
translate   → document.translate.requested
embed       → document.embed.requested
index       → document.index.requested
intelligence → document.intelligence.requested
alert       → document.alert.requested
```

The plan (lines ~547–663) has the complete class. Follow it exactly — do not
invent routing key names.

Tests (`tests/unit/test_publisher.py`, 2 tests):
1. `test_publish_parse_stores_message_id` — `rabbit.publish` called with correct
   routing key + payload; `set_rabbit_message_id` called with returned ID.
2. `test_publish_parse_skips_rabbit_when_disabled` — `rabbit.enabled=False` →
   `publish` returns `""`; `set_rabbit_message_id` NOT called.

```bash
uv run pytest tests/unit/test_publisher.py -q  # 2 passed
uv run mypy src/services/pipeline/publisher.py src/services/pipeline/jobs.py --strict
```

### Task 8 — Wire publish into sync-now

Open `src/services/api/routers/admin/ingestion.py`. Inside the per-document
loop, **after** `job_repo.enqueue_document(...)`, add the RabbitMQ publish block
from the plan (lines ~683–701). Guard with `if settings.rabbitmq_enabled:`.

**Critical:** The publish call must be additive. The existing `enqueue_document`
call must not be removed or moved. When `RABBITMQ_ENABLED=false` (the default),
the code path must be identical to what exists today.

Run regression:
```bash
uv run pytest tests/ -k "ingestion or sync_now" -q   # all pass
uv run pytest tests/ -q                              # full suite; all pass
```

### Task 9 — Admin jobs routes

**`src/services/api/routers/admin/jobs.py`:** Two endpoints:
- `GET /admin/jobs` — filterable by `status`, `job_type`, `stage`, `source_id`;
  paginated (`limit`, `offset`); returns `{"jobs": [...], "total": N}`.
- `GET /admin/jobs/{job_id}` — returns job detail or 404.

The `_row_to_job` helper converts raw DB row to dict. Use `to_uuid` from
`shared.db` for UUID columns. The plan (lines ~795–897) has the complete
implementation; follow it exactly.

**Register in `src/services/api/routers/admin/__init__.py`:**
```python
from services.api.routers.admin import jobs as jobs_router
router.include_router(jobs_router.router)
```

Tests (`tests/integration/test_admin_jobs_routes.py`, 3 tests):
1. `test_admin_list_jobs_returns_jobs` — seed a job; GET /admin/jobs?status=pending → 200, job in list.
2. `test_admin_get_job_detail` — seed a job; GET /admin/jobs/{id} → 200, correct fields.
3. `test_admin_get_job_404` — GET /admin/jobs/{random-uuid} → 404.

```bash
uv run pytest tests/integration/test_admin_jobs_routes.py -q  # 3 passed
uv run mypy src/services/api/routers/admin/jobs.py --strict
```

---

## Commit Strategy

```bash
git commit -m "feat(rabbit): add stage and rabbit_message_id columns to pipeline_jobs"
git commit -m "feat(rabbit): DocumentPublisher and set_rabbit_message_id"
git commit -m "feat(rabbit): publish to RabbitMQ from sync-now when RABBITMQ_ENABLED=true"
git commit -m "feat(rabbit): GET /admin/jobs and GET /admin/jobs/{job_id} routes"
```

End every commit message with:
```
Co-Authored-By: DeepSeek <noreply@deepseek.com>
```

---

## Acceptance Checklist

- [ ] Migration applies and rolls back cleanly (`alembic upgrade head` / `downgrade -1` / `upgrade head`).
- [ ] `set_rabbit_message_id` in `PipelineJobRepository`.
- [ ] `DocumentPublisher` with 6 `publish_*` methods.
- [ ] `RABBITMQ_ENABLED=false` (default) → no rabbit calls in sync-now; all existing ingestion tests pass.
- [ ] `GET /admin/jobs` and `GET /admin/jobs/{job_id}` registered and returning correct shape.
- [ ] 2 publisher unit tests pass; 3 admin jobs integration tests pass.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` clean on all new files.
- [ ] No changes to `worker.py`, `kafka_consumer.py`, or `shared/rabbit.py`.

---

## Pull Request

Target: **`feature/rabbitmq-job-bus`**

Suggested title:
```
feat(rabbit): Sub-B — publisher, migration, sync-now wiring, admin jobs routes (#426)
```

PR body template:

```markdown
## Summary

Sub-B of the RabbitMQ stage-based job bus (#432).

- Migration: `stage` + `rabbit_message_id` columns on `pipeline_jobs`.
- `DocumentPublisher`: DB-first publish with 6 per-stage methods.
- sync-now: publishes to RabbitMQ when `RABBITMQ_ENABLED=true` (no-op otherwise).
- `GET /admin/jobs` + `GET /admin/jobs/{job_id}` admin routes.

## Tests

```bash
uv run pytest tests/unit/test_publisher.py tests/integration/test_admin_jobs_routes.py -q
# 2 + 3 = 5 passed
uv run pytest tests/ -k "ingestion" -q
# all pass (regression)
```

## Context Loaded
- `docs/memory/current-state.md` (Sub-A done entry)
- `docs/memory/decisions.md`, `docs/memory/handoffs.md`
- `AGENTS.md`, `docs/agents/token-efficiency.md`, `docs/agents/coding-behavior.md`
- GitHub issues #426, #432 (skim)
- Plan Tasks 6–9 only
- `src/services/pipeline/jobs.py`, `src/services/api/routers/admin/ingestion.py`

## Context Skipped
- Plan Tasks 1–5 (Sub-A), Tasks 10–18 (Sub-C through Sub-G)
- All frontend files
- `spec.md`, `spec-v4.pdf`

## Token Efficiency Notes
- Read `docs/memory/` before source files: yes
- Used graphify/rg before opening files: yes
- Read more than one plan: no
- Read broad source areas: no

## Memory Written
- `docs/memory/current-state.md` — updated Sub-B status to Done; noted Sub-C (#427) is unblocked.
- `docs/memory/decisions.md` — no new decisions.

Closes #426
Part of #432
```

---

## Final Report Format

1. Branch + latest commit SHA.
2. PR link.
3. Files changed + line-count delta.
4. Exact test commands and results.
5. Migration round-trip result.
6. Any deviation from the plan and reason.
7. Shared memory updated: yes/no + what was written.
