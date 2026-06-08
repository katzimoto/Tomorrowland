# OpenCode + DeepSeek Mission: Issue #425 — RabbitMQ Sub-A

## Identity and Repo

You are working on the Tomorrowland repo: `katzimoto/Tomorrowland`.

- **Child issue:** #425 — RabbitMQ Service + Client + Topology (Sub-A)
- **Parent tracker:** #432 — RabbitMQ stage-based job bus
- **Feature branch:** `feature/rabbitmq-job-bus`
- **PR target:** `feature/rabbitmq-job-bus` (NOT `main`)

Do not merge or PR to `main`. All work for this feature accumulates on the
feature branch and will be integrated in one final PR.

---

## Step 0 — Shared Memory (read before anything else)

Before opening a single source file, read these in order:

1. `docs/memory/current-state.md` — find the 2026-05-23 RabbitMQ entry; note
   feature branch, sub-issue map, and next action.
2. `docs/memory/decisions.md` — scan for RabbitMQ or pipeline bus entries.
3. `docs/memory/handoffs.md` — check for any cross-agent handoff targeting #425
   or #432.

This is non-optional. These files hold durable state that prevents re-deriving
context the last agent already resolved.

---

## Step 1 — Required Reading (after shared memory)

Read in this order. Stop when you have enough context — do not read all files
speculatively.

1. `AGENTS.md` — branch policy, PR format, commit conventions.
2. `docs/agents/token-efficiency.md` — context budget rules. Key new rules:
   - `graphify query` before `rg` for cross-file questions.
   - Load only the task range you need from the plan (Tasks 1–5 for this issue).
   - Write `Memory Written` section in your handoff.
3. `docs/agents/coding-behavior.md` — execution discipline (think before coding,
   surgical edits, verifiable goals).
4. GitHub issue #425 body — full scope and acceptance criteria.
5. GitHub issue #432 body — skim only for overall architecture; do not load the
   full parent context.
6. **Plan: `docs/superpowers/plans/2026-05-23-rabbitmq-job-bus.md`, Tasks 1–5
   only** (lines ~53–407). Do not read Tasks 6–18.

Use `graphify query "RabbitMQ pipeline"` if you need to understand how the
existing pipeline connects to services. Use `rg` for exact symbol searches.

---

## Step 2 — Branch Setup

```bash
git fetch origin
git checkout feature/rabbitmq-job-bus 2>/dev/null || git checkout -b feature/rabbitmq-job-bus origin/main
git status --short
```

If `feature/rabbitmq-job-bus` already exists on origin, rebase onto it:

```bash
git pull --rebase origin feature/rabbitmq-job-bus
```

---

## Goal

Implement Sub-A of the RabbitMQ stage-based job bus: the foundation layer that
all subsequent sub-issues (B–G) depend on. No business logic, no consumers, no
publishers — only the infrastructure wiring.

Deliverables (Tasks 1–5 from the plan):

| Task | Deliverable |
|------|-------------|
| 1 | Feature branch confirmed / created |
| 2 | `pika>=1.3,<2` added to `pyproject.toml`; lockfile updated |
| 3 | RabbitMQ settings added to `src/shared/config.py` |
| 4 | `rabbitmq` service added to `docker-compose.yml`; `.env.example` updated |
| 5 | `src/shared/rabbit.py` implemented + `tests/unit/test_rabbit_client.py` passing |

---

## Allowed Changes

```
pyproject.toml                         — add pika dependency
uv.lock                                — regenerated automatically
src/shared/config.py                   — add rabbitmq_url, rabbitmq_enabled, rabbitmq_user, rabbitmq_pass
docker-compose.yml                     — add rabbitmq service block
.env.example                           — add RABBITMQ_* keys
src/shared/rabbit.py                   — new file
tests/unit/test_rabbit_client.py       — new file
```

## Forbidden Changes

```
src/services/pipeline/worker.py        — DO NOT TOUCH (Sub-C scope)
src/services/pipeline/kafka_consumer.py — DO NOT TOUCH
src/services/api/routers/             — DO NOT TOUCH (Sub-B scope)
migrations/                            — DO NOT TOUCH (Sub-B scope)
any frontend file                      — DO NOT TOUCH
spec.md, spec-v4.pdf                   — DO NOT READ OR TOUCH
```

---

## Implementation Detail

### Config (`src/shared/config.py`)

Add to the `Settings` class (follow the existing pattern of other optional
service URLs):

```python
rabbitmq_url: str = Field(
    default="amqp://guest:guest@localhost:5672/",
    alias="RABBITMQ_URL",
)
rabbitmq_enabled: bool = Field(default=False, alias="RABBITMQ_ENABLED")
```

The plan (Task 3) has the exact field names and defaults. Follow it exactly.

### Docker Compose (`docker-compose.yml`)

Add a `rabbitmq` service using image
`rabbitmq:3.13-management-alpine`. Expose ports 5672 and 15672. Add a
healthcheck. The plan (Task 4) has the exact block — copy it verbatim.

Also add `RABBITMQ_URL`, `RABBITMQ_ENABLED`, `RABBITMQ_DEFAULT_USER`,
`RABBITMQ_DEFAULT_PASS` to `.env.example` with safe defaults.

### `src/shared/rabbit.py`

Implement `RabbitClient` with these public methods:

- `connect() -> None` — opens `pika.BlockingConnection`; no-op when
  `enabled=False`.
- `declare_topology() -> None` — idempotent exchange + queue declaration;
  no-op when not connected.
- `publish(exchange, routing_key, body, properties) -> None` — basic_publish;
  no-op when not connected.
- `close() -> None` — closes channel + connection gracefully.
- `__enter__` / `__exit__` — context manager calling `connect` / `close`.

**Topology (declare in this order, all durable):**

Exchanges:
- `pipeline` — `direct`, durable
- `pipeline.retry` — `direct`, durable, `x-dead-letter-exchange=pipeline`
- `pipeline.dead` — `fanout`, durable

Queues (one per stage, repeat for each of: `parse`, `translate`, `embed`,
`index`, `intelligence`, `alert`):
- `pipeline.<stage>` — bound to `pipeline` exchange, routing key
  `<stage>`, dead-letter → `pipeline.retry`, DLX routing key `<stage>`
- `pipeline.<stage>.retry` — bound to `pipeline.retry`, routing key
  `<stage>`, TTL 30 000 ms, dead-letter → `pipeline` exchange
- `pipeline.<stage>.dead` — bound to `pipeline.dead`, routing key `<stage>`

**`enabled=False` behaviour:** when `Settings.rabbitmq_enabled` is `False`,
`connect()`, `declare_topology()`, and `publish()` must be silent no-ops.
`close()` must be safe to call in any state. This is the default — the existing
stack must be completely unaffected.

The plan (Task 5) has the complete implementation; follow it exactly rather than
improvising topology names.

### Tests (`tests/unit/test_rabbit_client.py`)

Mock `pika.BlockingConnection` throughout. Required test cases (all from
the plan Task 5):

1. `test_declare_topology_creates_all_queues` — verify
   `exchange_declare` and `queue_declare` call counts.
2. `test_declare_topology_creates_bindings` — verify `queue_bind` call
   count (3 bindings × 6 stages = 18).
3. `test_connect_raises_on_refused` — `pika.BlockingConnection` raises
   → `RabbitConnectionError` propagated.
4. `test_noop_when_disabled` — `enabled=False` → `connect()` +
   `declare_topology()` make zero pika calls.

Run after implementing:

```bash
uv run pytest tests/unit/test_rabbit_client.py -v
```

Expected: 4 passed.

Also run linting and type-check on the new file:

```bash
uv run ruff check src/shared/rabbit.py
uv run ruff format --check src/shared/rabbit.py
uv run mypy src/shared/rabbit.py --strict
```

All must be clean before committing.

---

## Commit Strategy

One commit per task (matching the plan):

```bash
git commit -m "chore: add pika dependency for RabbitMQ"
git commit -m "feat(rabbit): add RabbitMQ settings to config"
git commit -m "feat(rabbit): add RabbitMQ service to docker-compose"
git commit -m "feat(rabbit): RabbitClient with topology declaration and no-op disabled mode"
```

End every commit message with:

```
Co-Authored-By: DeepSeek <noreply@deepseek.com>
```

---

## Acceptance Checklist

Before opening the PR, verify every item:

- [ ] `pika>=1.3,<2` in `pyproject.toml`; `uv run python -c "import pika"` succeeds.
- [ ] `RABBITMQ_URL`, `RABBITMQ_ENABLED` present in `Settings` with correct defaults.
- [ ] `rabbitmq` service in `docker-compose.yml` with healthcheck.
- [ ] `.env.example` updated with all `RABBITMQ_*` keys.
- [ ] `src/shared/rabbit.py` exists with `RabbitClient`.
- [ ] `enabled=False` makes `connect()` / `declare_topology()` / `publish()` silent no-ops.
- [ ] All 4 unit tests pass (`uv run pytest tests/unit/test_rabbit_client.py -v`).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict` clean on `src/shared/rabbit.py`.
- [ ] No files outside `Allowed Changes` were modified.
- [ ] No changes to `src/services/pipeline/worker.py` or `kafka_consumer.py`.

---

## Pull Request

Open a PR targeting **`feature/rabbitmq-job-bus`** (not `main`).

Suggested title:
```
feat(rabbit): Sub-A — RabbitMQ service, RabbitClient, topology (#425)
```

PR body template:

```markdown
## Summary

Sub-A of the RabbitMQ stage-based job bus (#432).

- Added `pika>=1.3` dependency.
- Added `RABBITMQ_URL` / `RABBITMQ_ENABLED` settings to `shared/config.py`.
- Added `rabbitmq` Docker service (management UI on :15672, AMQP on :5672).
- Implemented `RabbitClient` in `src/shared/rabbit.py`:
  - Idempotent topology declaration (6 stages × 3 queue types = 18 queues).
  - `enabled=False` → all methods are silent no-ops (existing stack unaffected).
  - Context manager support.
- 4 unit tests with mocked pika.

## Tests

```bash
uv run pytest tests/unit/test_rabbit_client.py -v
# 4 passed
uv run ruff check src/shared/rabbit.py && uv run mypy src/shared/rabbit.py --strict
# clean
```

## Context Loaded
- `docs/memory/current-state.md` (2026-05-23 RabbitMQ entry)
- `docs/memory/decisions.md`
- `AGENTS.md`, `docs/agents/token-efficiency.md`, `docs/agents/coding-behavior.md`
- GitHub issues #425, #432 (skim)
- Plan Tasks 1–5 only (`docs/superpowers/plans/2026-05-23-rabbitmq-job-bus.md`)

## Context Skipped
- Plan Tasks 6–18 (Sub-B through Sub-G)
- All frontend files
- `spec.md`, `spec-v4.pdf`
- `src/services/pipeline/worker.py`

## Token Efficiency Notes
- Read `docs/memory/` before source files: yes
- Used graphify/rg before opening files: yes
- Read more than one plan: no
- Read broad source areas: no

## Memory Written
- `docs/memory/current-state.md` — updated Sub-A status to Done; noted Sub-B (#426) is unblocked.
- `docs/memory/decisions.md` — no new decisions (topology names follow plan exactly).

Closes #425
Part of #432
```

---

## Final Report Format

When done, report:

1. Branch name and latest commit SHA.
2. PR link.
3. Files changed and line-count delta.
4. Exact test command and result.
5. Linting result.
6. Any deviation from the plan and reason.
7. Shared memory updated: yes/no + what was written.

If you cannot complete a task, stop at that task, report the exact blocker, and
do not proceed to the next task.
