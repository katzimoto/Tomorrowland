# Admin Source UX Implementation Plan

Feature track: `feature/admin-source-ux`  
Related issues: #87, #170, #171  
Existing PR: #99

## Scope boundaries

### #87 — Admin source sync usability polish
**Owner:** codex/implement-admin-source-sync-usability-polish  
**Status:** PR #99 open against `feature/admin-source-ux`.

Backend:
- Add `last_sync_state` JSON column to `ingestion_sources` (migration `a7d9c2e4f6b8`).
- Add `GET /admin/sources/{source_id}/sync-state` endpoint.
- Add `POST /admin/sources/{source_id}/test-connection` endpoint.
- Sanitize connector errors before returning to frontend.

Frontend:
- Render last sync metadata (started at, finished at, document counts, status).
- Show sanitized error summaries in the source list.
- Add "Test Connection" button with loading / success / error states.

### #170 — Connector validation and test-connection UX
**Owner:** *unclaimed*  
**Depends on:** #87 backend contracts.

Backend:
- Extend `POST /admin/sources/{source_id}/test-connection` to validate credentials, reachability, and permissions for each connector type (`folder`, `smb`, `confluence`, `jira`, `nifi`).
- Return structured validation result: `ok`, `unreachable`, `auth_failed`, `permission_denied`, `config_invalid`.
- Store validation result in `ingestion_sources` metadata for quick reference.

Frontend:
- Test-connection result panel on source create/edit modal.
- Inline validation hints (e.g., "SMB share not reachable", "Confluence space not found").
- Disable "Save and Sync" until validation passes or user explicitly overrides.

### #171 — Connector sync and failure status UI
**Owner:** *unclaimed*  
**Depends on:** #87 backend contracts.

Backend:
- Add `GET /admin/sources/{source_id}/sync-jobs` endpoint (paginated recent syncs).
- Add `GET /admin/sources/{source_id}/sync-jobs/{job_id}` endpoint with detailed per-item results.
- Enrich DLQ records with `source_id` and `job_id` for tracing.

Frontend:
- Sync job history table on source detail page.
- Per-job document-level status: `ok`, `skipped`, `failed`, `pending`.
- DLQ quick-link from failed job rows.

## API contract changes

### Source validation / test connection

```http
POST /admin/sources/{source_id}/test-connection
Authorization: Bearer <token>
```

Response `200 OK`:
```json
{
  "source_id": "...",
  "status": "ok",
  "checked_at": "2026-05-13T12:00:00Z",
  "details": {
    "reachable": true,
    "auth_ok": true,
    "sample_items_found": 3
  }
}
```

Response `200 OK` (with validation failure):
```json
{
  "source_id": "...",
  "status": "unreachable",
  "checked_at": "2026-05-13T12:00:00Z",
  "details": {
    "reachable": false,
    "error_code": "CONNECTION_REFUSED",
    "message": "Unable to reach SMB server at the configured address."
  }
}
```

### Sync status / last sync metadata

```http
GET /admin/sources/{source_id}/sync-state
Authorization: Bearer <token>
```

Response `200 OK`:
```json
{
  "source_id": "...",
  "last_sync": {
    "started_at": "2026-05-13T11:55:00Z",
    "finished_at": "2026-05-13T11:58:00Z",
    "status": "completed",
    "summary": {
      "discovered": 42,
      "indexed": 40,
      "skipped": 1,
      "failed": 1
    }
  },
  "next_sync_scheduled": null,
  "dlq_unresolved_count": 1
}
```

### Sync job history

```http
GET /admin/sources/{source_id}/sync-jobs?page=1&page_size=10
Authorization: Bearer <token>
```

Response `200 OK`:
```json
{
  "jobs": [
    {
      "job_id": "...",
      "started_at": "2026-05-13T11:55:00Z",
      "finished_at": "2026-05-13T11:58:00Z",
      "status": "completed",
      "summary": {
        "discovered": 42,
        "indexed": 40,
        "skipped": 1,
        "failed": 1
      }
    }
  ],
  "total": 5
}
```

## Frontend surfaces affected

- `frontend/src/features/admin/AdminSourcesPage.tsx` — source list with sync metadata.
- `frontend/src/features/admin/AdminSourcesPage.test.tsx` — update tests for new columns/states.
- `frontend/src/features/admin/SourceFormModal.tsx` — *new or existing* create/edit modal with test-connection button.
- `frontend/src/features/admin/SourceDetailPage.tsx` — *new* job history, per-item status, DLQ link.
- `frontend/src/features/admin/SyncJobTable.tsx` — *new* reusable job history table.
- `frontend/src/i18n/locales/en.ts` and `he.ts` — new translation keys for validation statuses, sync labels, error messages.
- `frontend/src/api/admin.ts` — new API client methods for test-connection, sync-state, sync-jobs.

## Secret redaction and sanitized error rules

1. **Never return raw connector credentials** in any API response.
2. **Never log credentials** at `INFO` or higher levels.
3. **Sanitize error messages** before returning to frontend:
   - Remove hostnames, IPs, share paths, usernames from error text.
   - Replace with generic context: `<host>`, `<share>`, `<path>`, `<user>`.
4. **Store original errors** in DLQ / internal logs at `DEBUG` level only.
5. **Frontend must not render raw error text** directly; use mapped translation keys.
6. **Audit log** may record action + source_id but must not record credential values.

Example sanitization:

```python
# backend sanitization helper
def sanitize_connector_error(exc: Exception) -> str:
    message = str(exc)
    # remove URLs, IPs, paths
    message = re.sub(r"https?://\S+", "<url>", message)
    message = re.sub(r"\\[\w.-]+\\\w+", "<share>", message)
    return message
```

## Merge order inside `feature/admin-source-ux`

```text
1. PR #99  (#87 — admin source sync usability polish)
   - migration, backend endpoints, frontend list rendering, tests
2. PR for #170 (connector validation and test-connection UX)
   - extends #99 backend contracts
   - adds SourceFormModal validation UX
3. PR for #171 (connector sync and failure status UI)
   - extends #99 backend contracts
   - adds SourceDetailPage + SyncJobTable
4. Integration / cleanup PR
   - rebase latest main
   - full CI validation
   - docs update
   - CHANGELOG update
5. Final PR: feature/admin-source-ux -> main
```

## Existing PR #99 decision

**Decision: keep as-is, rebase onto `feature/admin-source-ux`.**

PR #99 already contains the foundational backend and frontend changes for #87. It is reviewable and does not depend on #170 or #171.

Action items:
- Rebase `codex/implement-admin-source-sync-usability-polish` onto latest `feature/admin-source-ux`.
- Run fresh CI validation (ruff, mypy, pytest, frontend lint/typecheck/tests).
- Merge #99 into `feature/admin-source-ux` after review passes.
- Do **not** retarget #99 to `main`.

## Final validation checklist before `feature/admin-source-ux -> main`

### Backend
- [ ] `ruff check --fix src/ tests/ migrations/`
- [ ] `ruff format src/ tests/ migrations/`
- [ ] `mypy src --strict`
- [ ] `pytest tests/unit/test_admin.py -q`
- [ ] `pytest tests/integration/test_admin.py -q`
- [ ] `pytest tests/unit/test_connector_*.py -q`
- [ ] Migration has upgrade + downgrade paths and passes `pytest tests/test_migrations.py -q`
- [ ] No raw credentials in API responses or logs at `INFO`+
- [ ] Sanitized error tests pass

### Frontend
- [ ] `npm --prefix frontend run lint`
- [ ] `npm --prefix frontend run typecheck`
- [ ] `npm --prefix frontend run test -- --run`
- [ ] `npm --prefix frontend run build`
- [ ] No placeholder copy on any admin surface
- [ ] No raw secrets rendered in UI

### Integration / docs
- [ ] `bash scripts/production-audit.sh`
- [ ] Admin docs updated (`docs/operations/production-compose.md` or new `docs/operations/admin-sources.md`)
- [ ] CHANGELOG.md updated
- [ ] `AGENTS.md` feature branch policy followed (no direct merge to main without integration PR)

## Documentation update checklist

### Operator docs to create or update

- [ ] **How to test a connector/source connection**
  - Navigate to Admin > Sources.
  - Select a source and click "Test Connection".
  - Interpret validation statuses: `ok`, `unreachable`, `auth_failed`, `permission_denied`, `config_invalid`.
  - Retry after fixing credentials or network issues.

- [ ] **Validation statuses and their meaning**
  - `ok`: connector can reach the source and authenticate.
  - `unreachable`: network or DNS failure; check host/port/URL.
  - `auth_failed`: credentials rejected; verify username/password/token.
  - `permission_denied`: authenticated but cannot list/read target scope.
  - `config_invalid`: required fields missing or malformed (e.g., missing `space_key`).

- [ ] **Sync summary counts**
  - `discovered`: total items found by the connector.
  - `indexed`: items successfully processed through the pipeline.
  - `skipped`: items skipped (already indexed with same SHA, or filtered out).
  - `failed`: items that failed extraction, translation, or indexing and were routed to DLQ.

- [ ] **Sanitized error behavior**
  - Frontend shows generic, redacted error messages.
  - Full error details are available in service logs at `DEBUG` level only.
  - Operators with log access can inspect the original exception for root-cause analysis.

- [ ] **Request / operation ID usage**
  - Every sync job and DLQ entry includes a `correlation_id`.
  - Use the correlation ID to trace a failed item from the admin UI through backend logs.
  - Example: `grep "correlation_id=<id>" docker compose logs api`.

- [ ] **Retry / DLQ limitations**
  - DLQ entries are not automatically retried in this release.
  - Operators can manually re-ingest corrected files or trigger a full source re-sync.
  - Follow-up issue for automatic retry with exponential backoff is deferred to a future phase.

### Target docs files

- `docs/operations/admin-sources.md` — *new*, primary operator guide for admin source UX.
- `docs/operations/production-compose.md` — add cross-reference to admin-sources doc.
- `CHANGELOG.md` — summarize feature track at integration time.

## Guardrails

- Do not merge partial admin source UX work directly to `main`.
- Do not expose connector secrets in docs, UI, API, logs, tests, or screenshots.
- Do not redesign the full admin UI in this track; keep changes scoped to source list, test-connection, and sync status.
- Keep validation/test-connection separate from ingestion; testing must be non-destructive.
- One branch — one active owner within the feature track.

## Acceptance criteria for this plan

- [x] Implementation plan exists and references #87/#170/#171.
- [x] Documentation update checklist is explicit.
- [x] Existing PR #99 has a documented keep/split/rebase decision.
- [x] Final validation checklist is documented.
- [x] PR targets `feature/admin-source-ux`, not `main`.
