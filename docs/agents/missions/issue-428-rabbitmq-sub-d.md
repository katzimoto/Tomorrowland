# OpenCode + DeepSeek Mission: Issue #428 — RabbitMQ Sub-D

## Identity and Repo

You are working on the Tomorrowland repo: `katzimoto/Tomorrowland`.

- **Child issue:** #428 — Intelligence + Alert Consumers (Sub-D)
- **Parent tracker:** #432 — RabbitMQ stage-based job bus
- **Feature branch:** `feature/rabbitmq-job-bus`
- **PR target:** `feature/rabbitmq-job-bus` (NOT `main`)
- **Blocked by:** #427 (Sub-C) — `BaseConsumer` must be merged first

Verify before starting:
```bash
git fetch origin
git log origin/feature/rabbitmq-job-bus --oneline | head -20
# Must show Sub-C commit: "feat(rabbit): BaseConsumer with ack/nack/dead-letter…"
```

---

## Step 0 — Shared Memory (read before anything else)

1. `docs/memory/current-state.md` — check Sub-A through Sub-C status.
2. `docs/memory/handoffs.md` — any handoff from Sub-C agent targeting #428.

---

## Step 1 — Required Reading

1. `AGENTS.md`
2. `docs/agents/token-efficiency.md`
3. `docs/agents/coding-behavior.md`
4. GitHub issue #428 (full body)
5. **Plan Task 13 only** (`docs/superpowers/plans/2026-05-23-rabbitmq-job-bus.md`, lines ~1536–1629)
6. `src/services/pipeline/consumer_base.py` — `BaseConsumer` interface (read-only)
7. `src/services/intelligence/worker.py` — `IntelligenceWorker.process_document` signature
8. `src/services/alerts/service.py` — `AlertMatcher.match_document` signature

Use `graphify query "intelligence worker alert"` before opening files.

---

## Step 2 — Branch Setup

```bash
git fetch origin
git checkout feature/rabbitmq-job-bus
git pull --rebase origin feature/rabbitmq-job-bus
```

---

## Goal

Implement Sub-D: thin consumer wrappers for the intelligence and alert pipeline stages.
These two stages run independently and in parallel after `IndexConsumer` publishes.

| Task | Deliverable |
|------|-------------|
| 13 | `intelligence_consumer.py`, `alert_consumer.py`, docker-compose entries, type-check clean |

---

## Allowed Changes

```
src/services/pipeline/intelligence_consumer.py   — new file
src/services/pipeline/alert_consumer.py          — new file
docker-compose.yml                               — add intelligence-worker (8085) + alert-worker (8086)
pyproject.toml                                   — add entrypoints for intelligence + alert workers
```

## Forbidden Changes

```
src/services/intelligence/worker.py    — DO NOT TOUCH (existing IntelligenceWorker; read-only)
src/services/alerts/service.py         — DO NOT TOUCH (existing AlertMatcher; read-only)
src/services/pipeline/consumer_base.py — DO NOT TOUCH (Sub-C owns this; read-only)
src/services/pipeline/worker.py        — DO NOT TOUCH
src/services/pipeline/kafka_consumer.py — DO NOT TOUCH
src/services/api/routers/              — Sub-B/E scope
any frontend file                      — DO NOT TOUCH
spec.md, spec-v4.pdf                   — DO NOT READ OR TOUCH
```

---

## Implementation Detail

### `IntelligenceConsumer`

File: `src/services/pipeline/intelligence_consumer.py`

```
queue_name  = "document.intelligence.requested"
worker_type = "intelligence-worker"
health_port = 8085
```

`handle_message` contract:
1. Get `content_text` from `job_repo.get_payload(document_id)`.
2. Call `self._intelligence.process_document(document_id, content)`.
3. Call `job_repo.mark_running_stage(job_id, "intelligence_done")`.

No publish — intelligence is a terminal stage (no downstream queue).

`__init__` takes: `rabbit: RabbitClient`, `job_repo: PipelineJobRepository`,
`intelligence_worker: IntelligenceWorker`, `health_port: int = 8085`.

The plan (Task 13, lines ~1540–1574) has the complete implementation.

**`main()` function:**
```python
def main() -> None:
    import logging
    from shared.config import Settings
    from shared.rabbit import RabbitClient
    from sqlalchemy import create_engine
    from services.pipeline.jobs import PipelineJobRepository
    from services.intelligence.worker import IntelligenceWorker
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    engine = create_engine(settings.postgres_url)
    with engine.connect() as conn:
        rabbit = RabbitClient(settings.rabbitmq_url, enabled=settings.rabbitmq_enabled)
        job_repo = PipelineJobRepository(conn)
        intelligence = IntelligenceWorker(settings)
        consumer = IntelligenceConsumer(rabbit, job_repo, intelligence)
        consumer.run()
```

### `AlertConsumer`

File: `src/services/pipeline/alert_consumer.py`

```
queue_name  = "document.alert.requested"
worker_type = "alert-worker"
health_port = 8086
```

`handle_message` contract:
1. Call `self._alert_matcher.match_document(document_id)`.
2. Call `job_repo.mark_running_stage(job_id, "alert_done")`.

No publish — alert is also a terminal stage.

`__init__` takes: `rabbit: RabbitClient`, `job_repo: PipelineJobRepository`,
`alert_matcher: AlertMatcher`, `health_port: int = 8086`.

The plan (Task 13, lines ~1576–1608) has the complete implementation.

Add a `main()` following the same pattern as `IntelligenceConsumer.main()`.

### docker-compose.yml

Add two services using the same template as parse-worker but:
- `intelligence-worker`: `command: tomorrowland-intelligence-worker`, health port 8085.
- `alert-worker`: `command: tomorrowland-alert-worker`, health port 8086.

Both depend on `rabbitmq: condition: service_healthy` and `postgres: condition: service_healthy`.

### pyproject.toml entrypoints

```toml
tomorrowland-intelligence-worker = "services.pipeline.intelligence_consumer:main"
tomorrowland-alert-worker = "services.pipeline.alert_consumer:main"
```

### Verification

```bash
uv run mypy src/services/pipeline/intelligence_consumer.py \
            src/services/pipeline/alert_consumer.py --strict
uv run pytest tests/ -q   # full suite; all pass
uv run ruff check src/services/pipeline/intelligence_consumer.py \
                  src/services/pipeline/alert_consumer.py
```

---

## Commit Strategy

```bash
git commit -m "feat(rabbit): IntelligenceConsumer and AlertConsumer"
```

End with:
```
Co-Authored-By: DeepSeek <noreply@deepseek.com>
```

---

## Acceptance Checklist

- [ ] `IntelligenceConsumer` wraps `IntelligenceWorker.process_document`; no publish.
- [ ] `AlertConsumer` wraps `AlertMatcher.match_document`; no publish.
- [ ] Both have `main()` entrypoints registered in `pyproject.toml`.
- [ ] `intelligence-worker` (8085) and `alert-worker` (8086) in docker-compose.
- [ ] `mypy --strict` clean on both files.
- [ ] Full test suite passes.
- [ ] `src/services/intelligence/worker.py` and `src/services/alerts/service.py` untouched.

---

## Pull Request

Target: **`feature/rabbitmq-job-bus`**

Suggested title:
```
feat(rabbit): Sub-D — IntelligenceConsumer and AlertConsumer (#428)
```

PR body template:

```markdown
## Summary

Sub-D of the RabbitMQ stage-based job bus (#432).

- `IntelligenceConsumer`: wraps existing `IntelligenceWorker` behind a RabbitMQ queue.
- `AlertConsumer`: wraps existing `AlertMatcher` behind a RabbitMQ queue.
- Both are terminal stages (no downstream publish).
- `main()` entrypoints + docker-compose services for ports 8085 + 8086.

## Tests

```bash
uv run pytest tests/ -q
# all pass
uv run mypy src/services/pipeline/intelligence_consumer.py \
            src/services/pipeline/alert_consumer.py --strict
# clean
```

## Context Loaded
- `docs/memory/current-state.md`, `docs/memory/handoffs.md`
- Plan Task 13 only
- `src/services/pipeline/consumer_base.py` (read-only)
- `src/services/intelligence/worker.py` (read-only, signature only)
- `src/services/alerts/service.py` (read-only, signature only)

## Context Skipped
- Plan Tasks 1–12 (Sub-A/B/C), Tasks 14–18 (Sub-E through Sub-G)

## Token Efficiency Notes
- Read `docs/memory/` before source files: yes
- Used graphify/rg before opening files: yes
- Read more than one plan: no
- Read broad source areas: no

## Memory Written
- `docs/memory/current-state.md` — Sub-D status to Done.
- `docs/memory/decisions.md` — no new decisions.

Closes #428
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
