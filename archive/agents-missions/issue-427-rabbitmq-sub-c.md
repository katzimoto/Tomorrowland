# OpenCode + DeepSeek Mission: Issue #427 — RabbitMQ Sub-C

## Identity and Repo

You are working on the Tomorrowland repo: `katzimoto/Tomorrowland`.

- **Child issue:** #427 — BaseConsumer + Core Stage Workers (Sub-C)
- **Parent tracker:** #432 — RabbitMQ stage-based job bus
- **Feature branch:** `feature/rabbitmq-job-bus`
- **PR target:** `feature/rabbitmq-job-bus` (NOT `main`)
- **Blocked by:** #425 (Sub-A) and #426 (Sub-B) — both must be merged first

Verify before starting:
```bash
git fetch origin
git log origin/feature/rabbitmq-job-bus --oneline | head -15
# Must show Sub-A ("RabbitClient…") and Sub-B ("DocumentPublisher…") commits
```

---

## Step 0 — Shared Memory (read before anything else)

1. `docs/memory/current-state.md` — check Sub-A and Sub-B status.
2. `docs/memory/handoffs.md` — any handoff from Sub-B agent targeting #427.
3. `docs/memory/decisions.md` — pipeline bus decisions.

---

## Step 1 — Required Reading

1. `AGENTS.md`
2. `docs/agents/token-efficiency.md`
3. `docs/agents/coding-behavior.md`
4. GitHub issue #427 (full body)
5. GitHub issue #432 (skim)
6. **Plan Tasks 10–12 only** (`docs/superpowers/plans/2026-05-23-rabbitmq-job-bus.md`, lines ~924–1535)
7. `src/shared/rabbit.py` — understand `RabbitClient` interface (read-only)
8. `src/services/pipeline/publisher.py` — understand `DocumentPublisher` (read-only)
9. `src/services/pipeline/jobs.py` — `PipelineJobRepository.mark_retry`, `mark_dead_letter`, `get_max_attempts`

Use `graphify query "pipeline worker base consumer"` before opening source files.

---

## Step 2 — Branch Setup

```bash
git fetch origin
git checkout feature/rabbitmq-job-bus
git pull --rebase origin feature/rabbitmq-job-bus
```

---

## Goal

Implement Sub-C: the consumer layer that drives the four core pipeline stages.

| Task | Deliverable |
|------|-------------|
| 10 | `src/services/pipeline/consumer_base.py` + `tests/unit/test_consumer_base.py` (4 tests) |
| 11 | `parse_worker.py`, `translate_worker.py`, `embed_worker.py`, `index_worker.py` |
| 12 | `main()` entrypoints in each worker + docker-compose stage services (parse/translate/embed/index) |

---

## Allowed Changes

```
src/services/pipeline/consumer_base.py        — new file
src/services/pipeline/parse_worker.py         — new file
src/services/pipeline/translate_worker.py     — new file
src/services/pipeline/embed_worker.py         — new file
src/services/pipeline/index_worker.py         — new file
tests/unit/test_consumer_base.py              — new file
pyproject.toml                                — add [project.scripts] entrypoints
docker-compose.yml                            — add parse/translate/embed/index services
```

## Forbidden Changes

```
src/shared/rabbit.py                          — read-only (Sub-A)
src/services/pipeline/publisher.py            — read-only (Sub-B)
src/services/pipeline/jobs.py                 — read-only (no new methods needed)
src/services/pipeline/worker.py               — DO NOT TOUCH (existing sync worker)
src/services/pipeline/kafka_consumer.py       — DO NOT TOUCH
src/services/pipeline/intelligence_consumer.py — Sub-D scope
src/services/pipeline/alert_consumer.py       — Sub-D scope
src/services/api/routers/                     — Sub-B/E scope
migrations/                                   — Sub-B owns; no new migrations here
any frontend file                             — DO NOT TOUCH
spec.md, spec-v4.pdf                          — DO NOT READ OR TOUCH
```

---

## Implementation Detail

### Task 10 — `BaseConsumer`

`src/services/pipeline/consumer_base.py` is the heart of all stage workers.
Get it right — every consumer in Sub-C, Sub-D depends on it.

**Class shape:**
```python
class BaseConsumer(ABC):
    queue_name: ClassVar[str]       # overridden in each subclass
    worker_type: ClassVar[str]      # for metrics/logging

    def __init__(self, rabbit: RabbitClient,
                 job_repo: PipelineJobRepository,
                 health_port: int = 8080) -> None: ...

    @abstractmethod
    def handle_message(self, job_id: UUID, document_id: UUID,
                       source_id: UUID, attempt: int,
                       correlation_id: str) -> None: ...

    def run(self) -> None:
        """Connect, declare topology, start consuming. Blocks until SIGTERM."""

    def _on_message(self, ch, method, properties, body: bytes) -> None:
        """pika delivery callback — ack/nack/dead-letter logic lives here."""
```

**`_on_message` ack/nack contract (critical):**
1. Parse JSON body → `job_id`, `document_id`, `source_id`, `attempt`.
2. Call `handle_message(...)`.
3. On **success**: `basic_ack(delivery_tag)`.
4. On **failure** with `attempt < max_attempts`: `basic_nack(delivery_tag, requeue=False)`
   → message routes to retry exchange (30s TTL); `job_repo.mark_retry(job_id, exc)`.
5. On **failure** with `attempt >= max_attempts`: `job_repo.mark_dead_letter(job_id, exc)`;
   `basic_nack(delivery_tag, requeue=False)` → message routes to DLQ.

`prefetch_count=1` must be set before consuming — this ensures the worker
processes one message at a time and back-pressure is applied naturally.

**Health HTTP server:** A minimal `http.server.HTTPServer` on `health_port`
responding `200 OK` to `GET /health`. Start in a daemon thread inside `run()`.

**SIGTERM handler:** On `SIGTERM`, set a flag; the consume loop checks it and
calls `channel.stop_consuming()` then `connection.close()`.

The plan (Task 10, lines ~926–1207) has complete implementation + 4 tests. Follow exactly.

**Required tests** (`tests/unit/test_consumer_base.py`):
1. `test_success_acks_message` — `handle_message` succeeds → `basic_ack` called, `basic_nack` not called.
2. `test_failure_nacks_and_retries_when_attempts_remaining` — raises → `basic_nack(requeue=False)`, `mark_retry` called.
3. `test_failure_dead_letters_when_attempts_exhausted` — `attempt >= max_attempts` → `mark_dead_letter`, `basic_nack`.
4. `test_noop_ack_on_malformed_body` — non-JSON body → ack (don't retry forever on corrupt messages).

```bash
uv run pytest tests/unit/test_consumer_base.py -v   # 4 passed
uv run mypy src/services/pipeline/consumer_base.py --strict
```

### Task 11 — Four Stage Consumers

Each is a thin `BaseConsumer` subclass. Implement in order (parse → translate → embed → index).
The plan (Task 11, lines ~1209–1480) has complete implementations for all four.

**ParseConsumer** (`queue_name = "document.parse.requested"`, `worker_type = "parse-worker"`):
- Load document; get `content_text` from payload or extract from file.
- Call `job_repo.update_content_text(document_id, text)`.
- Call `job_repo.mark_running_stage(job_id, "parsed")`.
- Publish: `publisher.publish_translate(...)`.

**TranslateConsumer** (`queue_name = "document.translate.requested"`, `worker_type = "translate-worker"`):
- Get `content_text` from payload.
- Translate via `LibreTranslateClient`.
- Call `job_repo.update_translated_text(document_id, translated)`.
- Call `job_repo.mark_running_stage(job_id, "translated")`.
- Publish: `publisher.publish_embed(...)`.

**EmbedConsumer** (`queue_name = "document.embed.requested"`, `worker_type = "embed-worker"`):
- Chunk + encode (same logic as `vector_worker.py` — reuse `chunk_text` + `encoder.encode_batch`).
- `chunk_id` format: `f"{document_id}-{suffix}-{idx}"` (suffix="orig"|"tr").
- `job_repo.mark_running_stage(job_id, "embedded")`.
- Publish: `publisher.publish_index(...)`.

**IndexConsumer** (`queue_name = "document.index.requested"`, `worker_type = "index-worker"`):
- Index in Elasticsearch via `es_client.index_document(...)`.
- `job_repo.mark_running_stage(job_id, "indexed")`.
- Publish **both** `publisher.publish_intelligence(...)` and `publisher.publish_alert(...)`.
- `job_repo.mark_running_stage(job_id, "completed")`.

Type-check all four together:
```bash
uv run mypy src/services/pipeline/parse_worker.py \
            src/services/pipeline/translate_worker.py \
            src/services/pipeline/embed_worker.py \
            src/services/pipeline/index_worker.py --strict
```

### Task 12 — Entrypoints + Compose Services

**`main()` in each worker file** (identical pattern, deps differ):
```python
def main() -> None:
    import logging
    from shared.config import Settings
    from shared.rabbit import RabbitClient
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    # build rabbit, job_repo, domain deps from settings
    # instantiate Consumer, call consumer.run()
```

**`pyproject.toml`** under `[project.scripts]`:
```toml
tomorrowland-parse-worker = "services.pipeline.parse_worker:main"
tomorrowland-translate-worker = "services.pipeline.translate_worker:main"
tomorrowland-embed-worker = "services.pipeline.embed_worker:main"
tomorrowland-index-worker = "services.pipeline.index_worker:main"
```

**`docker-compose.yml`** — add 4 services (parse 8081, translate 8082, embed 8083, index 8084).
Template from plan Task 12 (lines ~1507–1526). Each depends on `rabbitmq: condition: service_healthy`
and `postgres: condition: service_healthy`.

```bash
uv run pytest tests/ -q   # full suite; all pass
```

---

## Commit Strategy

```bash
git commit -m "feat(rabbit): BaseConsumer with ack/nack/dead-letter and health endpoint"
git commit -m "feat(rabbit): ParseConsumer, TranslateConsumer, EmbedConsumer, IndexConsumer"
git commit -m "feat(rabbit): worker entrypoints and docker-compose services for stage workers"
```

End every commit with:
```
Co-Authored-By: DeepSeek <noreply@deepseek.com>
```

---

## Acceptance Checklist

- [ ] `BaseConsumer` with `prefetch_count=1`, correct ack/nack/dead-letter logic.
- [ ] Health HTTP server starts on `health_port` in daemon thread.
- [ ] SIGTERM handled gracefully.
- [ ] 4 `test_consumer_base.py` tests pass.
- [ ] 4 stage consumers implemented with correct `queue_name` + `worker_type`.
- [ ] `chunk_id` format in EmbedConsumer: `{document_id}-{orig|tr}-{idx}`.
- [ ] IndexConsumer publishes **both** intelligence and alert after indexing.
- [ ] `main()` entrypoints in all 4 workers; registered in `pyproject.toml`.
- [ ] 4 docker-compose services added.
- [ ] `mypy --strict` clean on all new files.
- [ ] `worker.py` and `kafka_consumer.py` untouched.

---

## Pull Request

Target: **`feature/rabbitmq-job-bus`**

Suggested title:
```
feat(rabbit): Sub-C — BaseConsumer + parse/translate/embed/index workers (#427)
```

PR body template:

```markdown
## Summary

Sub-C of the RabbitMQ stage-based job bus (#432).

- `BaseConsumer`: pika consume loop, prefetch_count=1, ack/nack/dead-letter, health HTTP, SIGTERM.
- `ParseConsumer`, `TranslateConsumer`, `EmbedConsumer`, `IndexConsumer`.
- `main()` entrypoints registered in `pyproject.toml`.
- docker-compose services for all 4 stage workers.

## Tests

```bash
uv run pytest tests/unit/test_consumer_base.py -v
# 4 passed
uv run pytest tests/ -q
# all pass
```

## Context Loaded
- `docs/memory/current-state.md`, `docs/memory/handoffs.md`
- `AGENTS.md`, `docs/agents/token-efficiency.md`, `docs/agents/coding-behavior.md`
- GitHub issues #427, #432 (skim)
- Plan Tasks 10–12 only
- `src/shared/rabbit.py`, `src/services/pipeline/publisher.py`, `src/services/pipeline/jobs.py`

## Context Skipped
- Plan Tasks 1–9 (Sub-A/B), Tasks 13–18 (Sub-D through Sub-G)
- `src/services/pipeline/worker.py` (unchanged sync worker)
- All frontend files

## Token Efficiency Notes
- Read `docs/memory/` before source files: yes
- Used graphify/rg before opening files: yes
- Read more than one plan: no
- Read broad source areas: no

## Memory Written
- `docs/memory/current-state.md` — Sub-C status to Done; Sub-D (#428), Sub-E (#429), Sub-F (#430) unblocked.
- `docs/memory/decisions.md` — no new decisions.

Closes #427
Part of #432
```

---

## Final Report Format

1. Branch + latest commit SHA.
2. PR link.
3. Files changed + line-count delta.
4. Test commands and results.
5. Any deviation from plan and reason.
6. Shared memory updated: yes/no + what.
