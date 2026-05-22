---
name: tl-backend-integration-test
description: >
  Use this skill when writing, debugging, or fixing Tomorrowland backend integration tests —
  especially when tests return unexpected 404s on feature-flagged routes, connection errors
  to Meilisearch or other Docker services, 500s where you expected 422, or migration smoke
  test failures. Also invoke it when adding new integration tests for any FastAPI router,
  writing fixtures for new database tables, wiring up a new dual-gate feature flag, or
  adding JSON fields to a migration. Use it proactively at the start of any backend test
  task — several gotchas here look like code bugs but are actually test setup issues, and
  catching them early saves significant debugging time.
license: MIT
compatibility: claude-code, opencode
metadata:
  project: Tomorrowland
  audience: implementation-agents
---

# tl-backend-integration-test

## Purpose

Several project-specific patterns produce silent failures that are easy to mistake for code bugs. This skill describes them concisely so you can rule them out immediately rather than spending time bisecting the router code.

## Dual-gate feature flag

Feature-flagged routes check **two** independent guards. Missing either makes every request return 404:

1. `Settings.feature_<name>` — env-driven pydantic Settings field
2. `system_config` DB row — seeded by foundation migration, defaults to `False`

The production migration seeds the DB key as `False` for safety. Tests must override both explicitly:

```python
def _settings(**overrides):
    return Settings(
        feature_document_chat=True,         # gate 1: Settings field
        feature_meilisearch_search=False,   # prevent Docker DNS (see below)
        **overrides,
    )

def _setup_users(conn):
    # gate 2: system_config DB row
    conn.execute(
        "INSERT OR REPLACE INTO system_config (key, value) VALUES (?, ?)",
        ("feature.document_chat", "true"),
    )
```

If your test returns 404 on every request and the route is correct, check both gates first.

## Meilisearch env leakage

`.env` sets `FEATURE_MEILISEARCH_SEARCH=true`. Unless `_settings()` explicitly overrides this to `False`, tests will attempt a TCP connection to `meilisearch:7700` (Docker hostname), which hangs and then fails with a connection error in non-Docker environments.

Always add `feature_meilisearch_search=False` to `_settings()` in integration tests unless the test specifically exercises Meilisearch.

## UUID path params: 422 not 500

Route handlers must type path params as `UUID`, not `str`. FastAPI validates on entry and returns **422** for malformed input. If you type it `str` and call `UUID(str_param)` manually, a bad input raises `ValueError` → unhandled → **500**.

```python
# Correct — FastAPI validates; returns 422 for malformed UUID
async def get_session(session_id: UUID, connection: ...) -> ...:
    return repo.get(session_id)

# Wrong — raises ValueError → 500 on malformed input
async def get_session(session_id: str, connection: ...) -> ...:
    session_uuid = UUID(session_id)   # ← ValueError if invalid
```

Tests that verify rejection of bad UUIDs should assert **422**, not 400 or 500.

## JSON fields in migrations

Project convention for SQLite compat: use `sa.Text()` for JSON fields. Do not use `sa.JSON()`, `JSONB`, or `CheckConstraint` — they don't work reliably with the SQLite test driver.

```python
# Migration
sa.Column("scope_ids", sa.Text(), nullable=False, server_default="[]"),
sa.Column("citations", sa.Text(), nullable=True),
```

The repository must encode on write and decode on read:

```python
# Repository write
"scope_ids": json.dumps(obj.scope_ids),

# Repository read
scope_ids = json.loads(row["scope_ids"] or "[]")
```

No check constraint on JSON shape or enum columns — validation is app-layer only (Pydantic models).

## Ruff errors that appear in new backend code

Two errors that show up almost every time in new backend files:

**B904** — `raise` inside `except` without a cause:
```python
# Wrong
except ValueError:
    raise HTTPException(status_code=400, detail="invalid")

# Correct — chain the original exception
except ValueError as exc:
    raise HTTPException(status_code=400, detail="invalid") from exc

# Or suppress the context if it's irrelevant
    raise HTTPException(status_code=400, detail="invalid") from None
```

**E501** — lines over 100 chars. Ruff won't auto-fix these. Split strings across lines or extract to a variable.

## Verification order

Run in this order and fix each before moving on:

```bash
ruff check --fix src/ tests/
ruff format src/ tests/
mypy src --strict
pytest tests/unit/test_<area>.py -q --no-cov
pytest tests/integration/test_<area>.py -q --no-cov
```

The 90% coverage floor applies to the full suite only. `--no-cov` skips the check for targeted runs — that's expected and not a problem.
