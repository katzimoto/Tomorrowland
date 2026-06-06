# Plan: Fix 15 Audited Issues

**Date:** 2026-06-01
**Branch:** TBD
**Based on:** `main` (after `fix/pipeline-bugs-15` merges)

## Summary

A comprehensive codebase audit found 15 issues across three severity tiers:
critical disconnected infrastructure (tombstones, ProviderRegistry, full_resync),
medium observability gaps (silent errors, premature state transitions, no timeouts),
and low code-quality issues (bare excepts, sanitized error logs, missing test
skeletons).  This plan groups fixes into three phases.  Each phase is a
self-contained PR that can be reviewed and merged independently.

---

## Phase 1: Wiring Dead Infrastructure

**Goal:** Connect tombstone detection into live sync loops, wire index cleanup,
add full_resync mode, fix slow_worker state machine and poll loop, fix RabbitMQ
reconnect overhead.

**Risk:** Medium
**Estimated files changed:** 7

### Issue 1 — Wire tombstone detection into connector sync loop

**Files:** `src/services/api/routers/admin/ingestion.py`,
`src/services/pipeline/scheduler.py`

The `tombstone_missing_documents()` function in `sync_repository.py` is fully
implemented but **never called** from production code.  Connectors only create
and update documents; upstream deletions are silently invisible.

**Part A — Add `sync_mode` parameter to the `sync_now` API route**

In `ingestion.py`, `sync_now()` (line 121):

- Add optional `sync_mode: str = "incremental"` query parameter.
- Validate: `if sync_mode not in ("incremental", "full_resync"): raise HTTPException(422, ...)`
- Pass to `SyncRunCreate(sync_mode=sync_mode)` (currently hardcoded `"incremental"`).

**Part B — Collect seen external_ids and call tombstone detection**

In `_sync_source()` (scheduler) and `sync_now()` (API route), after iterating
all connector documents:

```python
seen_external_ids: set[str] = set()
for item in documents:
    seen_external_ids.add(item.external_id)
    # ... existing create/update logic ...

# After iteration, when sync_mode == "full_resync":
if sync_mode == "full_resync":
    from services.connectors.sync_repository import tombstone_missing_documents
    tombstone_missing_documents(
        connection,
        source_id,
        seen_external_ids,
        reason="not_found_in_sync",
        index_cleanup=build_index_cleanup(qdrant, meili),
    )
```

**Edge cases:**
- `incremental` mode must NOT run tombstone detection (partial syncs can't
  determine deletions).
- Documents that reappear after being tombstoned are handled by the existing
  `clear_tombstone_and_reactivate()` — called before `create()` if the doc
  already exists with `status='deleted'`.

**Verification:**
- `pytest tests/integration/test_sync_now_lifecycle.py -q`
- `pytest tests/unit/test_sync_lifecycle.py -q`
- `mypy src/services/api/routers/admin/ingestion.py src/services/pipeline/scheduler.py --strict`

---

### Issue 2 — Wire index_cleanup callback when tombstones are created

**Files:** `src/services/connectors/sync_repository.py` (new helper),
`src/services/api/routers/admin/ingestion.py`, `src/services/pipeline/scheduler.py`

When documents are tombstoned, their vectors (Qdrant) and search entries
(Meilisearch) must be removed.  The `tombstone_missing_documents()` function
accepts an `index_cleanup` callback, but no production caller passes one.

**New helper in `sync_repository.py`:**

```python
from collections.abc import Callable
from uuid import UUID

def build_index_cleanup(
    qdrant_client=None,
    meili_provider=None,
) -> Callable[[UUID], None]:
    """Return a callback that removes a document from search indexes."""

    def cleanup(document_id: UUID) -> None:
        doc_id_str = str(document_id)
        if qdrant_client is not None:
            try:
                qdrant_client.delete_by_doc_id(doc_id_str)
            except Exception:
                logger.warning("qdrant delete_by_doc_id failed for %s", doc_id_str, exc_info=True)
        if meili_provider is not None:
            try:
                meili_provider.delete_documents_by_filter(f"document_id = {doc_id_str}")
            except Exception:
                logger.warning("meili delete failed for %s", doc_id_str, exc_info=True)

    return cleanup
```

**Wire in `sync_now()` (API route):**
- Has access to `request.app.state.qdrant_client` and `request.app.state.meili_provider`.
- Pass `build_index_cleanup(qdrant_client, meili_provider)` as `index_cleanup`.

**Wire in `_sync_source()` (scheduler):**
- Accept optional `qdrant_client` and `meili_provider` parameters (default `None`).
- Pass them to `build_index_cleanup()` when building the callback.
- In `_run_scheduled_syncs()`, pass them from `app.state` if available.

**Verification:**
- `pytest tests/unit/test_sync_lifecycle.py -q`
- `python3 -m mypy src/services/connectors/sync_repository.py --strict`

---

### Issue 3 — Add SlowWorker poll loop

**Files:** `src/services/pipeline/slow_worker.py`

`SlowWorker` has no `_run_loop` or `poll_once` — enrichment jobs only get
picked up if the `EnrichConsumer` RabbitMQ consumer is running.  There's no
background fallback.

**Change:** Add a `poll_once()` static/module-level function and a `while True`
loop at the bottom of the file.

```python
def poll_once(engine, settings, llm_provider=None, qdrant_client=None):
    """Claim and process one enrich_document job, or sleep if none."""
    job_repo = PipelineJobRepository(engine)
    job = job_repo.claim_next(worker_type="enrich")
    if job is None:
        return False

    worker = SlowWorker(
        engine=engine,
        llm_provider=llm_provider or build_llm_provider(settings),
        qdrant_client=qdrant_client or QdrantSearchClient(url=settings.qdrant_url),
    )
    worker.process_document(job.document_id, job.content_text)
    return True


if __name__ == "__main__":
    settings = Settings()
    engine = sa.create_engine(settings.postgres_url)
    poll_interval = int(os.environ.get("SLOW_WORKER_POLL_SECONDS", "10"))

    logger.info("slow_worker polling every %ds", poll_interval)
    while True:
        try:
            processed = poll_once(engine, settings)
            if not processed:
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            break
        except Exception:
            logger.exception("slow_worker poll iteration failed")
            time.sleep(poll_interval)
```

**Verification:**
- `pytest tests/unit/test_slow_worker.py -q`
- Manual: run `python -m services.pipeline.slow_worker` and verify it polls.

---

### Issue 4 — Fix slow_worker premature `update_indexed` call

**Files:** `src/services/pipeline/slow_worker.py` (lines 156-180)

After enrichment succeeds, `slow_worker.py:180` calls:
```python
self._doc_repo.update_indexed(doc.id, "indexed", "high")
```

But enrichment runs **before** indexing.  If Meilisearch/Qdrant indexing fails
later, the document shows as `indexed` with no vectors or search entries.

**Fix:** Replace `update_indexed` with `update_translation_quality`:

```python
# Before (line 180):
self._doc_repo.update_indexed(doc.id, "indexed", "high")

# After:
self._doc_repo.update_translation_quality(doc.id, "high")
```

This keeps the document in its current status (e.g. `pending`) and only
transitions to `indexed` when `index_worker.py` or `worker.py` successfully
completes.

**Verification:**
- `pytest tests/unit/test_slow_worker.py -q`
- Check no other callers depend on the old state transition by searching:
  `rg "translation_quality.*high" src/services/`

---

### Issue 5 — Fix scheduler RabbitMQ reconnect on already-connected client

**Files:** `src/services/pipeline/scheduler.py` (lines 108-115)

The `_publish_scheduled_rabbit_messages()` function always calls `connect()` +
`declare_topology()` even when a shared client is already connected.

**Fix:** Add an `is_connected` guard:

```python
def _publish_scheduled_rabbit_messages(
    engine, settings, pending, rabbit=None,
):
    from shared.rabbit import RabbitClient, RabbitConnectionError

    if rabbit is None:
        rabbit = RabbitClient(settings.rabbitmq_url, enabled=True)

    if not getattr(rabbit, "_connected", False):
        try:
            rabbit.connect()
            rabbit.declare_topology()
        except RabbitConnectionError:
            logger.warning(...)
            return rabbit
```

**Verification:**
- Existing scheduler tests still pass.
- Manual: check logs for duplicate "connecting" messages on scheduler ticks
  with multiple sources.

---

## Phase 2: Error Handling & Observability

**Goal:** Add logging to silent error paths, add timeouts to prevent hangs,
add trackable failure states, add test skeletons for blocked features.

**Risk:** Very low
**Estimated files changed:** 10

### Issue 6 — Log full errors before sanitizing in `_sanitize_source_error`

**Files:** `src/services/api/_helpers.py` (line 70)

The sanitizer aggressively redacts paths, IPs, and credentials from error
messages before they reach the UI/logs.  The full error is never logged.

**Fix:** Add a debug log before sanitization:

```python
def _sanitize_source_error(message: str, source_row=None) -> str:
    logger.debug("source_error_raw: %s", message)  # <-- ADD
    # ... existing sanitization ...
```

**Verification:**
- Existing tests still pass.
- Set `LOG_LEVEL=DEBUG` and verify raw messages appear before sanitized ones.

---

### Issue 7 — Add thread pool timeout to IntelligenceWorker

**Files:** `src/services/intelligence/worker.py` (lines 262-265)

The thread pool processes LLM tasks with no timeout.  A hung Ollama call blocks
enrichment forever.

**Fix:** Add `timeout=120` to `future.result()`:

```python
for future in as_completed(futures):
    try:
        future.result(timeout=120)
    except TimeoutError:
        logger.error(
            "Intelligence task timed out after 120s for document_id=%s", document_id
        )
        future.cancel()
        # Cancel remaining futures to avoid resource leak
        for f in futures:
            f.cancel()
        break
```

---

### Issue 8 — Fix worst bare `except Exception` blocks

Target the 12 most egregious files (5+ bare excepts each, no logging):

**Files & changes:**

| File | Change |
|------|--------|
| `src/services/auth/ldap_client.py` | 8 bare excepts → add `logger.warning(..., exc_info=True)` |
| `src/services/extraction/mime_detector.py` | 3 bare excepts → add `logger.debug(..., exc_info=True)` |
| `src/services/extraction/xls.py` | 1 bare except → add `logger.debug(..., exc_info=True)` |
| `src/services/extraction/zip_extractor.py` | 1 bare except → add `logger.debug(..., exc_info=True)` |
| `src/services/extraction/tar_extractor.py` | 1 bare except → add `logger.debug(..., exc_info=True)` |
| `src/services/extraction/ocr.py` | 1 bare except → add `logger.debug(..., exc_info=True)` |

**Skipped:** `rag/reranker.py`, `rag/service.py`, `preview/service.py`,
`pipeline/*` (already have logging), `extraction/pdf.py` (optional import).

---

### Issue 9 — Track per-task enrichment failures

**Files:** `src/services/intelligence/worker.py` (lines 181-265),
`src/services/pipeline/slow_worker.py` (lines 140-156)

Currently `slow_worker.py` sets `translation_quality = "high"` even if every
intelligence task failed.  The pipeline job always succeeds.

**Fix:** In `IntelligenceWorker.process_document()`, return a summary dict:

```python
def process_document(self, document_id, content, source_id=None) -> dict[str, int]:
    """Returns {"succeeded": N, "failed": M} for each task outcome."""
    results = {"succeeded": 0, "failed": 0}
    # ... existing task execution ...
    for task in tasks:
        try:
            # ...
            results["succeeded"] += 1
        except Exception:
            results["failed"] += 1
    return results
```

Then in `slow_worker.py:140-156`, only set `translation_quality = "high"` if
at least one task succeeded:

```python
results = self._intelligence.process_document(doc.id, doc.content_text)
if results["succeeded"] > 0:
    self._doc_repo.update_translation_quality(doc.id, "high")
else:
    logger.warning("All intelligence tasks failed for document_id=%s", doc.id)
```

**Verification:**
- `pytest tests/unit/test_intelligence_worker_profile.py -q`
- `pytest tests/unit/test_slow_worker.py -q`

---

### Issue 10 — Add positive test skeleton for folder-scoped chat

**Files:** `tests/integration/test_chat_api.py`

Add a skipped test that documents the expected behavior once folder scope is
implemented:

```python
@pytest.mark.skip(reason="Blocked: folder_id not yet indexed in vector payloads")
def test_folder_scope_happy_path(migrated_engine: Engine) -> None:
    """When folder_id is indexed in Qdrant + Meilisearch, folder-scoped chat
    should return results filtered to the specified folder."""
    # Placeholder: create a doc with folder_id, index it, query with scope
    pass
```

---

## Phase 3: Deeper Architecture (Deferred)

These issues require design review and cross-team coordination.  They are
documented here for tracking but not in scope for the fix branch.

### Issue 11 — ProviderRegistry adapters (#578)
**Status:** Deferred to dedicated issue #578.

Requires: concrete `OllamaAdapter`, `OpenAIAdapter` implementing
`BaseModelProviderAdapter`, wiring into chat/RAG/embedding consumers,
backward compatibility with config-based model selection.

### Issue 12 — Folder-scoped chat
**Status:** Deferred.

Requires: `folder_id` indexed in Qdrant vector payloads, Meilisearch
filterable attributes, schema migration.

### Issue 13 — Full_resync UI toggle
**Status:** Partially addressed by Phase 1 (API parameter).

The frontend toggle (source admin UI checkbox/dropdown) is a separate
follow-up.  The API will accept the parameter; the UI can be added later.

---

## Skipped / Intentional

| Issue | Reason |
|-------|--------|
| IntelligenceWorker silent failures | Docstring explicitly says "best-effort — failures are logged and swallowed, never block ingestion." This is correct behavior for an enrichment pipeline. |
| 96 of 108 bare excepts | Remaining ones are in connectors (network errors), extraction (file format errors), optional imports — silently catching is appropriate. |

---

## Verification Checklist (per PR)

- [ ] `uv run ruff check --fix src/ tests/` — clean
- [ ] `uv run ruff format src/ tests/` — clean
- [ ] `uv run mypy src --strict` — clean on modified files
- [ ] `uv run pytest tests/unit/ tests/integration/ -q` — all passing
- [ ] `bash scripts/check-pr-cleanliness.sh main` — clean
- [ ] No changes to `CHANGELOG.md`, `README.md`, or frontend files unless required

---

## PR Ordering

| Order | PR | Contents | Est. Δ files | Risk |
|-------|----|----------|-------------|------|
| 1 | `fix/audit-phase2` | Issues #6–#10 (error handling, observability) | ~10 | Very low |
| 2 | `fix/audit-phase1` | Issues #1–#5 (tombstone, full_resync, slow_worker) | ~7 | Medium |
| 3 | `fix/audit-phase3` | Issues #11–#13 (deferred) | N/A | High |

Phase 2 first because it's safe, independently valuable, and the improved
logging will help debug Phase 1 if anything goes wrong.
