# Weak Points Audit — dead & untested code

> Generated 2026-06-07. Method: `vulture` (min-confidence 60) cross-referenced
> against real usage in `src/` + `tests/`, plus import/entrypoint/compose
> tracing for whole-module deadness; coverage from the full `pytest --cov` suite.
> **Verify each item before deleting** — some are intentional public surface or
> framework-wired in ways static analysis can't see.

## 1. Dead / unused code

### Orphaned modules (no import, no entrypoint, no compose reference)
- **`src/services/pipeline/scheduler.py`** — not in `[project.scripts]` (every
  other worker is: parse/translate/embed/index/intelligence/alert/enrich), not
  in `docker-compose`, not imported anywhere. Its `_sync_source` (which #628
  even modified) is called from nowhere in-repo. Strongest dead-code finding.
- **`src/shared/events.py`** — the Pydantic event schemas `DocumentEvent`,
  `IntelligenceEvent`, `TranslationQuality` have **zero** uses outside the file.
  The live pipeline passes dict payloads over RabbitMQ, not these classes.

### Repository methods written but never wired to a route/service
- `services/comments/repository.py`: `list_comments`, `count_comments`,
  `soft_delete`, `can_delete`
- `services/related/repository.py`: `get_document_text`, `user_can_access_any`

### Unused model / schema classes
- `services/annotations/models.py`: `AnnotationReply`
- `services/documents/models.py`: `DocumentVersionFamily`,
  `DocumentTranslationVersion`, and the `normalize_tag` helper

### Unused provider / service methods
- `services/search/meili_provider.py`: `drop_shadow_index`, `wait_for_task`
- `services/intelligence/adapters/base.py`: `check_health`
- `services/api/_helpers.py`: `alerts_check_on_ingest`
- `services/connectors/sync_repository.py`: `is_terminal`

### Status (2026-06-07)
- **DELETED** (verified: 0 refs in src/tests/scripts/migrations; imports + `mypy --strict`
  clean afterwards): `pipeline/scheduler.py`, `services/comments/` (whole package),
  `shared/events.py` (whole module — nothing imports it). ~780 lines removed.
- **Confirmed-dead, safe to delete next** (0 refs everywhere; concrete functions, low risk):
  `related/repository.py::{get_document_text, user_can_access_any}`,
  `api/_helpers.py::alerts_check_on_ingest`,
  `search/meili_provider.py::{drop_shadow_index, wait_for_task}`,
  and the unused pydantic models `documents/models.py::{DocumentVersionFamily,
  DocumentTranslationVersion}`, `annotations/models.py::AnnotationReply`.
- **CORRECTED — keep (vulture false positives found on inspection):**
  `documents/models.py::normalize_tag` is a `@field_validator("tag")` (pydantic calls it);
  `intelligence/adapters/base.py::check_health` is an adapter-**interface** method (polymorphic);
  `connectors/sync_repository.py::is_terminal` is a state-machine utility — **do not delete**.

### NOT dead (vulture false positives — do not remove)
- **FastAPI route handlers** under `services/api/routers/**` (registered via
  decorators, called by the framework) — ~120 flagged, all live.
- **Pydantic validators** (`validate_*`, `_validate_*`) — called by pydantic.
- **stdlib overrides**: `handle_data/starttag/endtag` (HTMLParser),
  `do_GET`/`log_message` (BaseHTTPRequestHandler), `signum`/`frame` (signal
  handlers), pika callback params (`properties`).
- Worker entrypoint modules (`asgi.py`, `*_consumer.py`, `*_worker.py`) — wired
  via `[project.scripts]` / `docker/backend.Dockerfile`.

## 2. Untested code (coverage gaps)

Full SQLite suite: **77% total** (gate = 90%), and **37 failed / 1750 passed**
— so the `Pytest` job fails on *both* coverage and real test failures.

### Per-file verdict — ADD TESTS vs DELETE vs LEAVE

| File | Cover | Verdict | Why |
|---|---|---|---|
| `pipeline/scheduler.py` | 0% | **DELETE** | orphaned — no entrypoint, no import, `_sync_source` called nowhere |
| `services/comments/repository.py` | 0% | **DELETE** | router not registered; `CommentRepository` imported nowhere; superseded by annotations (frontend comment UI uses the annotations API) |
| `services/comments/models.py` | 0% | **DELETE** | same — dead with the repository |
| `shared/events.py` (event classes) | low | **DELETE** | `DocumentEvent`/`IntelligenceEvent`/`TranslationQuality` unused; pipeline uses dict payloads |
| `related/repository.py` (2 methods) | — | **DELETE** | `get_document_text`, `user_can_access_any` never called |
| `meili_provider.py` (2 methods) | — | **DELETE/verify** | `drop_shadow_index`, `wait_for_task` unused in-repo (confirm no ops script uses them) |
| `auth/ldap_client.py` | 15% | **ADD TESTS** | security-critical (LDAP auth + group sync); mock the ldap3 conn, cover bind/search/failure |
| `vault/service.py` | 17% | **ADD TESTS** | secrets storage — security-sensitive; cover encrypt/decrypt/rotate/missing-key |
| `api/routers/vault.py` | 29% | **ADD TESTS** | secrets endpoints; integration tests (auth + CRUD + 404/403) |
| `pipeline/parse_worker.py` | 23% | **ADD TESTS** | core ingest stage; mime branches + failure/retry |
| `pipeline/translation_worker.py` | 41% | **ADD TESTS + FIX** | the 7 `test_translation_worker` failures are the stale `process_document` re-raise contract — wrap in `pytest.raises` (same fix as the integration tests in #643), then add coverage |
| `pipeline/enrich_worker.py` | 39% | **ADD TESTS** | consumer wrapper around slow_worker; cover retry/DLQ |
| `pipeline/consumer_base.py` | 54% | **ADD TESTS** | shared retry/DLQ/ack logic — high-leverage; cover mark_retry rowcount=0, dead-letter, commit ordering |
| `pipeline/publisher.py` | 54% | **ADD TESTS** | message bodies carry content_text/translated_text — assert payloads |
| `api/routers/admin/ingestion.py` | 24% | **ADD TESTS** | sync-now + FOR UPDATE lock + outcome states |
| `api/routers/admin/ldap.py` | 25% | **ADD TESTS** | group-mapping CRUD |
| `api/routers/admin/sources.py` | 43% | **ADD TESTS** | source CRUD + permissions |
| `api/routers/chat.py` | 54% | **ADD TESTS** | RAG streaming, scope validation, citation paths |
| `api/asgi.py` | 0% | **LEAVE** | thin ASGI loader (Dockerfile entrypoint); at most a 1-line import smoke test |
| `pipeline/alert_consumer.py`, `embed_worker.py`, `intelligence_consumer.py` | 0% | **LEAVE entrypoint, TEST logic** | the `main()` wrappers are entrypoints (pyproject scripts); test the underlying consumer/worker classes instead |

### Failing-test cleanup (separate from coverage — these are red, not just untested)
37 failures, almost all the **stale worker re-raise contract** I fixed for the
integration tests but not the unit copies:
- `unit/test_slow_worker.py` ×7, `unit/test_translation_worker.py` ×7 → wrap
  `process_document` calls in `pytest.raises(RuntimeError)` (mirror #643).
- `unit/test_index_consumer.py` ×2, `test_rag_trace`, `test_document_repository_metadata`,
  `test_extraction_fixture_corpus`, `integration/test_sync_now_lifecycle` ×1 each,
  `unit/test_compose_volumes.py` ×4 (compose-shape assertions) → triage individually.

### Recommended order
1. **Fix the 37 reds** (mostly the worker contract — cheap, mechanical).
2. **Delete** the dead modules/members above (removes untested code → raises the
   coverage denominator for free).
3. **Add tests** for the security-critical gaps first (`ldap_client`, `vault`),
   then the pipeline core (`consumer_base`, `publisher`, workers).
