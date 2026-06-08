# OpenCode + DeepSeek Mission: Issue #430 — RabbitMQ Sub-F

## Identity and Repo

You are working on the Tomorrowland repo: `katzimoto/Tomorrowland`.

- **Child issue:** #430 — Retry Tiers + Prometheus Alert Rules (Sub-F)
- **Parent tracker:** #432 — RabbitMQ stage-based job bus
- **Feature branch:** `feature/rabbitmq-job-bus`
- **PR target:** `feature/rabbitmq-job-bus` (NOT `main`)
- **Blocked by:** #427 (Sub-C) — `BaseConsumer` must be merged first

Sub-F is parallel with Sub-D (#428) and Sub-E (#429).

Verify before starting:
```bash
git fetch origin
git log origin/feature/rabbitmq-job-bus --oneline | head -20
# Must show Sub-C commit: "feat(rabbit): BaseConsumer…"
```

---

## Step 0 — Shared Memory (read before anything else)

1. `docs/memory/current-state.md` — check Sub-A through Sub-C status.
2. `docs/memory/handoffs.md` — any handoff from Sub-C targeting #430.

---

## Step 1 — Required Reading

1. `AGENTS.md`
2. `docs/agents/token-efficiency.md`
3. `docs/agents/coding-behavior.md`
4. GitHub issue #430 (full body)
5. **Plan Tasks 16–17 only** (`docs/superpowers/plans/2026-05-23-rabbitmq-job-bus.md`, lines ~1789–1896)
6. `src/shared/rabbit.py` — `declare_topology` method (read-only; Task 16 extends it)
7. `src/services/pipeline/consumer_base.py` — `_on_message` failure branch (read-only; Task 16 modifies it)

Use `graphify query "retry exchange dead letter"` before opening files.

---

## Step 2 — Branch Setup

```bash
git fetch origin
git checkout feature/rabbitmq-job-bus
git pull --rebase origin feature/rabbitmq-job-bus
```

---

## Goal

Implement Sub-F: replace immediate nack-to-DLQ with a timed retry tier (30s backoff)
and add Prometheus alert rules for queue health.

| Task | Deliverable |
|------|-------------|
| 16 | Retry exchange + per-stage retry queues in `rabbit.py`; updated `_on_message` in `consumer_base.py` |
| 17 | `monitoring/alerts/rabbitmq.yml` — 3 Prometheus alert rules |

---

## Allowed Changes

```
src/shared/rabbit.py                           — extend declare_topology with retry exchange
src/services/pipeline/consumer_base.py         — update _on_message failure branch
monitoring/alerts/rabbitmq.yml                 — new file
```

## Forbidden Changes

```
src/services/pipeline/worker.py                — DO NOT TOUCH
src/services/pipeline/kafka_consumer.py        — DO NOT TOUCH
src/services/api/routers/                      — Sub-B/E scope
migrations/                                    — Sub-B owns
any frontend file                              — DO NOT TOUCH
spec.md, spec-v4.pdf                           — DO NOT READ OR TOUCH
```

---

## Implementation Detail

### Task 16 — Retry tier exchange

**Part A: extend `src/shared/rabbit.py` `declare_topology()`**

Add a `tomorrowland.documents.retry` topic exchange after the main exchange
declaration. For each of the 6 stage queues, add a retry queue with:
- Name: `<queue>.replace("requested", "retry")` e.g. `document.parse.retry`
- Durable: true
- `x-dead-letter-exchange`: main exchange (`pipeline` exchange name)
- `x-dead-letter-routing-key`: the original queue name
- `x-message-ttl`: 30 000 (30 seconds)
- Bound to `tomorrowland.documents.retry` exchange with routing key = original queue name

The plan (Task 16, lines ~1795–1821) has the exact block. Follow it exactly —
do not invent exchange or queue names.

After editing `rabbit.py`, run existing tests to confirm topology test still passes:
```bash
uv run pytest tests/unit/test_rabbit_client.py -q
```

**Part B: update `src/services/pipeline/consumer_base.py` `_on_message` failure branch**

Replace the unconditional `basic_nack(requeue=False)` on failure with:

```
if attempt < min(3, max_attempts):
    # Publish to retry exchange with incremented attempt counter
    # basic_ack the current delivery (message moves to retry queue via TTL)
    # job_repo.mark_retry(...)
else:
    # job_repo.mark_dead_letter(...)
    # basic_nack(requeue=False) → message routes to DLQ
```

The published retry message body must have `"attempt": attempt + 1` so the
consumer knows it is a retry. Use `basic_publish` to `tomorrowland.documents.retry`
exchange with routing key = `self.queue_name`.

The plan (Task 16, lines ~1823–1842) has the exact code block.

After editing `consumer_base.py`, run consumer base tests:
```bash
uv run pytest tests/unit/test_consumer_base.py -q   # 4 passed
```

Verify type-check:
```bash
uv run mypy src/shared/rabbit.py src/services/pipeline/consumer_base.py --strict
```

### Task 17 — Prometheus alert rules

Create `monitoring/alerts/rabbitmq.yml` with 3 alert rules:

1. **TomorrowlandRabbitQueueBacking** — `severity: warning`
   Queue depth > 100 for > 10 minutes on any non-DLQ queue.
   Expr: `tomorrowland_rabbit_queue_depth{queue!~".*dead.*"} > 100`

2. **TomorrowlandRabbitDlqPending** — `severity: critical`
   Any message in any DLQ for > 1 minute.
   Expr: `tomorrowland_rabbit_queue_depth{queue=~".*dead.*"} > 0`

3. **TomorrowlandWorkerHeartbeatStale** — `severity: critical`
   Worker heartbeat not updated in > 2 minutes.
   Expr: `time() - tomorrowland_worker_heartbeat_timestamp_seconds > 120`

The plan (Task 17, lines ~1855–1893) has the exact YAML. Copy it verbatim —
metric names must match what the workers emit.

`monitoring/alerts/` directory may not exist yet. Create it:
```bash
mkdir -p monitoring/alerts
```

---

## Commit Strategy

```bash
git commit -m "feat(rabbit): retry tier exchange with 30s TTL backoff before DLQ"
git commit -m "feat(rabbit): Prometheus alert rules for queue depth, DLQ, and worker heartbeat"
```

End each with:
```
Co-Authored-By: DeepSeek <noreply@deepseek.com>
```

---

## Acceptance Checklist

- [ ] `tomorrowland.documents.retry` exchange declared in `declare_topology()`.
- [ ] 6 `<stage>.retry` queues declared with 30s TTL and correct DLX routing.
- [ ] `_on_message` publishes to retry exchange on first N failures; nacks to DLQ on exhaustion.
- [ ] `test_rabbit_client.py` still passes (4 tests).
- [ ] `test_consumer_base.py` still passes (4 tests) — update test assertions if retry/nack path changed.
- [ ] `monitoring/alerts/rabbitmq.yml` exists with all 3 alert rules.
- [ ] `mypy --strict` clean on `rabbit.py` and `consumer_base.py`.
- [ ] `worker.py` and `kafka_consumer.py` untouched.

---

## Pull Request

Target: **`feature/rabbitmq-job-bus`**

Suggested title:
```
feat(rabbit): Sub-F — retry tier exchange + Prometheus alert rules (#430)
```

PR body template:

```markdown
## Summary

Sub-F of the RabbitMQ stage-based job bus (#432).

- Retry tier: `tomorrowland.documents.retry` exchange + 6 per-stage retry queues (30s TTL → republish to main exchange).
- `_on_message`: first N failures → retry exchange; attempt >= max_attempts → DLQ.
- `monitoring/alerts/rabbitmq.yml`: queue depth warning, DLQ critical, worker heartbeat critical.

## Tests

```bash
uv run pytest tests/unit/test_rabbit_client.py tests/unit/test_consumer_base.py -q
# all passed
uv run mypy src/shared/rabbit.py src/services/pipeline/consumer_base.py --strict
# clean
```

## Context Loaded
- `docs/memory/current-state.md`, `docs/memory/handoffs.md`
- Plan Tasks 16–17 only
- `src/shared/rabbit.py` (extend topology)
- `src/services/pipeline/consumer_base.py` (update failure branch)

## Context Skipped
- Plan Tasks 1–15 (Sub-A through Sub-E), Task 18 (Sub-G)

## Token Efficiency Notes
- Read `docs/memory/` before source files: yes
- Used graphify/rg before opening files: yes
- Read more than one plan: no
- Read broad source areas: no

## Memory Written
- `docs/memory/current-state.md` — Sub-F status to Done; Sub-G (#431) unblocked.
- `docs/memory/decisions.md` — no new decisions.

Closes #430
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
