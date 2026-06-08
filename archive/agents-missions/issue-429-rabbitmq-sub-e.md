# OpenCode + DeepSeek Mission: Issue #429 — RabbitMQ Sub-E

## Identity and Repo

You are working on the Tomorrowland repo: `katzimoto/Tomorrowland`.

- **Child issue:** #429 — Admin Monitoring (Sub-E)
- **Parent tracker:** #432 — RabbitMQ stage-based job bus
- **Feature branch:** `feature/rabbitmq-job-bus`
- **PR target:** `feature/rabbitmq-job-bus` (NOT `main`)
- **Blocked by:** #427 (Sub-C) — `BaseConsumer` + consumers must be merged first

Sub-E is parallel with Sub-D (#428). You do not need Sub-D to be merged, only Sub-C.

Verify before starting:
```bash
git fetch origin
git log origin/feature/rabbitmq-job-bus --oneline | head -20
# Must show Sub-C commit: "feat(rabbit): BaseConsumer…"
```

---

## Step 0 — Shared Memory (read before anything else)

1. `docs/memory/current-state.md` — check Sub-A through Sub-C status.
2. `docs/memory/handoffs.md` — any handoff from Sub-B or Sub-C targeting #429.

---

## Step 1 — Required Reading

1. `AGENTS.md`
2. `docs/agents/token-efficiency.md`
3. `docs/agents/coding-behavior.md`
4. GitHub issue #429 (full body)
5. **Plan Tasks 14–15 only** (`docs/superpowers/plans/2026-05-23-rabbitmq-job-bus.md`, lines ~1630–1788)
6. `src/services/api/routers/admin/jobs.py` — existing GET /admin/jobs routes (read-only; Task 15 adds POST)
7. `src/services/api/routers/admin/__init__.py` — understand how routers are registered

Use `graphify query "admin rabbit queue routes"` before opening files.

---

## Step 2 — Branch Setup

```bash
git fetch origin
git checkout feature/rabbitmq-job-bus
git pull --rebase origin feature/rabbitmq-job-bus
```

---

## Goal

Implement Sub-E: the two admin observability endpoints that let operators inspect
queue health and manually retry dead-lettered jobs.

| Task | Deliverable |
|------|-------------|
| 14 | `GET /admin/rabbit/queues` in `src/services/api/routers/admin/rabbit.py` + 1 unit test |
| 15 | `POST /admin/jobs/{job_id}/retry` added to existing `jobs.py` + integration test |

---

## Allowed Changes

```
src/services/api/routers/admin/rabbit.py         — new file (Task 14)
src/services/api/routers/admin/jobs.py           — add POST retry endpoint (Task 15)
src/services/api/routers/admin/__init__.py        — register rabbit router
tests/unit/test_admin_rabbit_routes.py            — new file
tests/integration/test_admin_jobs_routes.py       — add retry test
```

## Forbidden Changes

```
src/shared/rabbit.py                             — read-only
src/services/pipeline/consumer_base.py           — read-only
src/services/pipeline/worker.py                  — DO NOT TOUCH
src/services/pipeline/kafka_consumer.py          — DO NOT TOUCH
migrations/                                      — Sub-B owns; no new migrations
any frontend file                                — DO NOT TOUCH
spec.md, spec-v4.pdf                             — DO NOT READ OR TOUCH
```

---

## Implementation Detail

### Task 14 — `GET /admin/rabbit/queues`

**File:** `src/services/api/routers/admin/rabbit.py`

This endpoint calls the RabbitMQ management API (runs on port 15672) to read
live queue depth and consumer counts. It does NOT use `pika` — it uses
`urllib.request` to hit the HTTP management API with Basic auth.

The 6 stage queues to report on:
```
document.parse.requested
document.translate.requested
document.embed.requested
document.index.requested
document.intelligence.requested
document.alert.requested
```

Response shape:
```json
{
  "queues": [
    {
      "queue": "document.parse.requested",
      "depth": 3,
      "consumers": 1,
      "dlq": "document.parse.dead",
      "dlq_depth": 0
    },
    ...
  ]
}
```

On management API error (RabbitMQ not running, wrong credentials), return
`{"queues": [], "error": "<message>"}` — never 500.

The plan (Task 14, lines ~1632–1735) has the complete `_mgmt_get` helper and
router implementation. Follow it exactly — particularly the DLQ name derivation:
`queue.replace("requested", "dead")`.

**Settings used:** `settings.rabbitmq_user`, `settings.rabbitmq_pass` — these
must already be in `shared/config.py` from Sub-A.

**Register the router** in `src/services/api/routers/admin/__init__.py`:
```python
from services.api.routers.admin import rabbit as rabbit_router
router.include_router(rabbit_router.router)
```

**Test** (`tests/unit/test_admin_rabbit_routes.py`, 1 test):
Mock `_mgmt_get` to return a list of queue dicts. Assert response has `"queues"`
key and correct shape. The plan (Task 14, lines ~1634–1654) has the test.

```bash
uv run pytest tests/unit/test_admin_rabbit_routes.py -q   # 1 passed
uv run mypy src/services/api/routers/admin/rabbit.py --strict
```

### Task 15 — `POST /admin/jobs/{job_id}/retry`

**Add to existing `src/services/api/routers/admin/jobs.py`:**

```python
@router.post("/admin/jobs/{job_id}/retry")
def admin_retry_job(job_id: UUID, request: Request,
                    user: Annotated[TokenPayload, Depends(current_user)],
                    ) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as conn:
        row = conn.execute(
            sa.text("SELECT status FROM pipeline_jobs WHERE id = :id"),
            {"id": job_id.hex},
        ).mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if row["status"] != "dead_letter":
            raise HTTPException(
                status_code=409,
                detail=f"Job is not dead-lettered (status={row['status']})",
            )
        conn.execute(
            sa.text("""
                UPDATE pipeline_jobs
                SET status = 'pending', attempts = 0, last_error = NULL,
                    locked_by = NULL, locked_at = NULL,
                    run_after = :now, updated_at = :now
                WHERE id = :id AND status = 'dead_letter'
            """),
            {"id": job_id.hex, "now": datetime.now(UTC)},
        )
    return {"retried": str(job_id)}
```

**Guards:**
- Returns 404 if job not found.
- Returns 409 if job is not `dead_letter` status. Do not allow re-queuing
  running or pending jobs — that would create duplicates.

The plan (Task 15, lines ~1738–1784) has the complete implementation.

**Add test** to `tests/integration/test_admin_jobs_routes.py`:
- Seed a `dead_letter` job.
- POST `/admin/jobs/{id}/retry` → 200, `{"retried": "<id>"}`.
- Verify job status is now `pending`.
- Also test 409 when job is `pending` and 404 for unknown ID.

```bash
uv run pytest tests/integration/test_admin_jobs_routes.py -q
uv run mypy src/services/api/routers/admin/jobs.py --strict
```

---

## Commit Strategy

```bash
git commit -m "feat(rabbit): GET /admin/rabbit/queues route"
git commit -m "feat(rabbit): POST /admin/jobs/{id}/retry endpoint"
```

End each with:
```
Co-Authored-By: DeepSeek <noreply@deepseek.com>
```

---

## Acceptance Checklist

- [ ] `GET /admin/rabbit/queues` returns correct shape; graceful error when broker unreachable.
- [ ] `POST /admin/jobs/{id}/retry` resets `dead_letter` → `pending`; 409 for non-dead-letter; 404 for missing.
- [ ] `rabbit` router registered in `admin/__init__.py`.
- [ ] 1 unit test for queue route; at least 3 integration tests for retry route.
- [ ] `mypy --strict` clean on `rabbit.py` and `jobs.py`.
- [ ] No changes to `worker.py`, `kafka_consumer.py`, or consumer files.

---

## Pull Request

Target: **`feature/rabbitmq-job-bus`**

Suggested title:
```
feat(rabbit): Sub-E — admin queue monitoring + job retry endpoint (#429)
```

PR body template:

```markdown
## Summary

Sub-E of the RabbitMQ stage-based job bus (#432).

- `GET /admin/rabbit/queues`: calls RabbitMQ management API, reports depth + consumer count per stage queue + DLQ.
- `POST /admin/jobs/{id}/retry`: resets dead-lettered job to pending; guards against 409/404.

## Tests

```bash
uv run pytest tests/unit/test_admin_rabbit_routes.py \
              tests/integration/test_admin_jobs_routes.py -q
# all passed
```

## Context Loaded
- `docs/memory/current-state.md`, `docs/memory/handoffs.md`
- Plan Tasks 14–15 only
- `src/services/api/routers/admin/jobs.py` (read-only before Task 15 edit)
- `src/services/api/routers/admin/__init__.py`

## Context Skipped
- Plan Tasks 1–13 (Sub-A through Sub-D), Tasks 16–18 (Sub-F/G)
- All consumer files, all frontend files

## Token Efficiency Notes
- Read `docs/memory/` before source files: yes
- Used graphify/rg before opening files: yes
- Read more than one plan: no
- Read broad source areas: no

## Memory Written
- `docs/memory/current-state.md` — Sub-E status to Done.
- `docs/memory/decisions.md` — no new decisions.

Closes #429
Part of #432
```

---

## Final Report Format

1. Branch + latest commit SHA.
2. PR link.
3. Files changed + line-count delta.
4. Test + type-check results.
5. Any deviation from plan and reason.
6. Shared memory updated: yes/no + what.
