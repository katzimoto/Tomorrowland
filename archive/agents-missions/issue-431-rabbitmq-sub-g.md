# OpenCode + DeepSeek Mission: Issue #431 — RabbitMQ Sub-G

## Identity and Repo

You are working on the Tomorrowland repo: `katzimoto/Tomorrowland`.

- **Child issue:** #431 — Air-gap Compose + Validation Script (Sub-G)
- **Parent tracker:** #432 — RabbitMQ stage-based job bus
- **Feature branch:** `feature/rabbitmq-job-bus`
- **PR target:** `feature/rabbitmq-job-bus` (NOT `main`)
- **Blocked by:** #430 (Sub-F) — retry tiers must be merged first (Sub-G validates the full topology)

Verify before starting:
```bash
git fetch origin
git log origin/feature/rabbitmq-job-bus --oneline | head -25
# Must show Sub-F commit: "feat(rabbit): retry tier exchange…"
```

---

## Step 0 — Shared Memory (read before anything else)

1. `docs/memory/current-state.md` — check Sub-A through Sub-F status; confirm all are Done.
2. `docs/memory/handoffs.md` — any handoff from Sub-F targeting #431.

---

## Step 1 — Required Reading

1. `AGENTS.md`
2. `docs/agents/token-efficiency.md`
3. `docs/agents/coding-behavior.md`
4. GitHub issue #431 (full body)
5. **Plan Task 18 only** (`docs/superpowers/plans/2026-05-23-rabbitmq-job-bus.md`, lines ~1897–end)
6. `docker-compose.yml` — understand current RabbitMQ and worker service definitions
7. `docker-compose.airgap.yml` — understand existing air-gap compose structure (if it exists)
8. `scripts/tomorrowland-airgap.sh` — understand current image manifest (if it exists)

Check what exists:
```bash
ls scripts/ docker-compose*.yml 2>/dev/null
```

---

## Step 2 — Branch Setup

```bash
git fetch origin
git checkout feature/rabbitmq-job-bus
git pull --rebase origin feature/rabbitmq-job-bus
```

---

## Goal

Implement Sub-G: air-gap deployment support for RabbitMQ and the validation script
that smoke-tests the full queue topology on a clean stack.

| Task | Deliverable |
|------|-------------|
| 18a | RabbitMQ service added to `docker-compose.airgap.yml` |
| 18b | `rabbitmq:3.13-management-alpine` added to the air-gap image manifest |
| 18c | `scripts/validate-rabbitmq.sh` — smoke-tests all queues + workers |

---

## Allowed Changes

```
docker-compose.airgap.yml           — add rabbitmq service (same def as docker-compose.yml)
scripts/tomorrowland-airgap.sh      — add rabbitmq image to save/load manifest
scripts/validate-rabbitmq.sh        — new file
```

## Forbidden Changes

```
docker-compose.yml                            — already has rabbitmq (added in Sub-A/C); read-only here
src/services/pipeline/worker.py               — DO NOT TOUCH
src/services/pipeline/kafka_consumer.py       — DO NOT TOUCH
src/shared/rabbit.py                          — Sub-A/F own this; read-only
any frontend file                             — DO NOT TOUCH
spec.md, spec-v4.pdf                          — DO NOT READ OR TOUCH
```

---

## Implementation Detail

### Task 18a — Air-gap compose

Open `docker-compose.airgap.yml`. Add a `rabbitmq:` service block that is
**identical** to the one in `docker-compose.yml`. Do not deviate from the
existing service definition — the air-gap stack must be fully compatible.

If `docker-compose.airgap.yml` does not exist yet, create it with the same
structure as `docker-compose.yml` but for the air-gap subset of services.

The plan (Task 18, lines ~1899–1903) describes the intent: same service definition,
pre-loaded image in the air-gap bundle.

### Task 18b — Air-gap image manifest

Open `scripts/tomorrowland-airgap.sh`. Find where Docker images are saved/loaded
(look for `docker save` / `docker load` calls or an `IMAGES` array). Add:
```
rabbitmq:3.13-management-alpine
```
to the image list so it is included in the air-gap tarball.

If the script does not exist, create a minimal one that saves all required images
to a tarball (see the pattern from existing services in the repo).

### Task 18c — `scripts/validate-rabbitmq.sh`

Create an executable smoke-test script. The plan (Task 18, lines ~1905–end) has
the full implementation. Follow it exactly.

The script must:
1. Check broker is reachable via management API (`GET /api/overview`).
2. Verify all **6 stage queues** exist: `document.{parse,translate,embed,index,intelligence,alert}.requested`
3. Verify all **6 DLQ queues** exist: `document.{parse,...}.dead`
4. Verify all **6 retry queues** exist: `document.{parse,...}.retry`
5. Report pass/fail per queue; exit 1 on any missing queue.

Configuration via environment variables with defaults:
```bash
RABBITMQ_MGMT_URL="${RABBITMQ_MGMT_URL:-http://localhost:15672}"
RABBITMQ_USER="${RABBITMQ_USER:-tomorrowland}"
RABBITMQ_PASS="${RABBITMQ_PASS:-changeme}"
```

Make executable:
```bash
chmod +x scripts/validate-rabbitmq.sh
```

Verify syntax:
```bash
bash -n scripts/validate-rabbitmq.sh
```

### CHANGELOG.md

Add a feature entry for the full RabbitMQ job bus. This is the only sub-issue
that touches `CHANGELOG.md`. Entry format (follow existing entries):

```markdown
## [Unreleased]

### Added
- RabbitMQ stage-based job bus (#432): parse → translate → embed → index → intelligence/alert pipeline with per-stage queues, 30s retry tiers, DLQ, admin monitoring routes, and air-gap support.
```

---

## Commit Strategy

```bash
git commit -m "feat(rabbit): air-gap compose and image manifest for RabbitMQ"
git commit -m "feat(rabbit): validate-rabbitmq.sh smoke-test script"
git commit -m "docs: CHANGELOG entry for RabbitMQ stage-based job bus (#432)"
```

End each with:
```
Co-Authored-By: DeepSeek <noreply@deepseek.com>
```

---

## Acceptance Checklist

- [ ] `rabbitmq` service in `docker-compose.airgap.yml` matches `docker-compose.yml`.
- [ ] `rabbitmq:3.13-management-alpine` in `scripts/tomorrowland-airgap.sh` image list.
- [ ] `scripts/validate-rabbitmq.sh` exists and is executable.
- [ ] Script verifies all 18 queues: 6 stage + 6 DLQ + 6 retry.
- [ ] Script uses env vars with safe defaults; exits 1 on missing queue.
- [ ] `bash -n scripts/validate-rabbitmq.sh` passes (no syntax errors).
- [ ] `CHANGELOG.md` has entry for #432.
- [ ] No changes to `worker.py`, `kafka_consumer.py`, or any Python source.

---

## After This PR — Final Integration

Sub-G is the last sub-issue. After it merges into `feature/rabbitmq-job-bus`,
open a final integration PR from `feature/rabbitmq-job-bus` → `main`. That PR
closes #432. Before opening it:

```bash
uv run pytest tests/ -q   # all pass
uv run ruff check src/
uv run mypy src/ --strict
npm run --prefix frontend build   # if frontend was not touched, can skip
```

Update `docs/memory/current-state.md`:
- Mark RabbitMQ job bus (#432) as **Done**.
- Note: integration PR opened targeting `main`.

---

## Pull Request

Target: **`feature/rabbitmq-job-bus`**

Suggested title:
```
feat(rabbit): Sub-G — air-gap compose, validate script, CHANGELOG (#431)
```

PR body template:

```markdown
## Summary

Sub-G (final) of the RabbitMQ stage-based job bus (#432).

- RabbitMQ service added to `docker-compose.airgap.yml`.
- `rabbitmq:3.13-management-alpine` added to air-gap image manifest.
- `scripts/validate-rabbitmq.sh`: smoke-tests all 18 queues (6 stage + 6 DLQ + 6 retry).
- `CHANGELOG.md` entry for the full feature.

## Verification

```bash
bash -n scripts/validate-rabbitmq.sh   # syntax OK
# (live test requires running stack — skipped in CI, run manually)
```

## Context Loaded
- `docs/memory/current-state.md` (all sub-issues A–F confirmed Done)
- Plan Task 18 only
- `docker-compose.yml`, `docker-compose.airgap.yml`, `scripts/tomorrowland-airgap.sh`

## Context Skipped
- Plan Tasks 1–17 (Sub-A through Sub-F)
- All Python source files (no code changes)

## Token Efficiency Notes
- Read `docs/memory/` before source files: yes
- Used graphify/rg before opening files: yes
- Read more than one plan: no
- Read broad source areas: no

## Memory Written
- `docs/memory/current-state.md` — Sub-G Done; RabbitMQ job bus feature branch complete; integration PR needed for main.
- `docs/memory/decisions.md` — no new decisions.

Closes #431
Part of #432
```

---

## Final Report Format

1. Branch + latest commit SHA.
2. PR link.
3. Files changed.
4. `bash -n` result.
5. Integration PR status (opened/not yet).
6. Shared memory updated: yes/no + what.
