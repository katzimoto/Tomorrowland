# Admin Source UX Implementation Plan

Feature track: `feature/admin-source-ux`  
Related issues: #87, #170, #171  
PRs: #99 (dropped), #242 (original plan), #243 (merged — #170)

---

## Current state

- **#99** — dropped. Merged as partial commits into `feature/admin-source-ux` but
  the PR is dead. Do not revive.
- **#170 / PR #243** — merged into `feature/admin-source-ux`. Structured
  connection validation with status classification (`ok`, `unreachable`,
  `auth_failed`, `permission_denied`, `config_invalid`), validation stored in
  `ingestion_sources` metadata, frontend test-connection with error display.
- **#87 remaining** — any scope not covered by #170 should be recreated as a
  fresh focused PR, avoiding overlap with the validation work in #243.
- **#171** — not yet started. Planned for sync/failure status UI.

---

## Scope boundaries

### #170 — Connector validation and test-connection UX (DONE)

**Status:** Merged via PR #243.

Backend:
- `POST /admin/sources/{source_id}/test-connection` returns structured result.
- `_classify_connection_error()` helper maps exceptions to status types.
- Validation stored in `last_validation_status`, `last_validation_error`, `last_validated_at`.

Frontend:
- "Test Connection" button with loading / success / error states.
- Error messages from structured response displayed inline.
- `Source` type includes validation fields.

### #87 remaining — Admin source sync usability polish (recreate as new PR)

Anything not covered by #170. Avoid duplicating #243 validation logic.

Possible remaining scope:
- Source list already shows sync state (`last_sync_status`, counts) from #99
  partial merge. Verify all sync metadata renders correctly.
- Ensure sync error display is consistent with new validation error handling.
- Any missing frontend polish for sync state rendering.

### #171 — Connector sync and failure status UI (NOT STARTED)

**Depends on:** nothing from #170 (independent feature).

Backend:
- `GET /admin/sources/{source_id}/sync-jobs` — paginated recent syncs.
- `GET /admin/sources/{source_id}/sync-jobs/{job_id}` — per-item results.
- Enrich DLQ records with `source_id` and `job_id`.

Frontend:
- Sync job history table on source detail page.
- Per-job document status: `ok`, `skipped`, `failed`, `pending`.
- DLQ quick-link from failed job rows.

---

## API contract changes (landed)

### Test connection

```http
POST /admin/sources/{source_id}/test-connection
Authorization: Bearer <token>
```

Response `200 OK`:
```json
{
  "source_id": "<uuid>",
  "status": "ok",
  "checked_at": "2026-05-13T12:00:00Z",
  "details": {"config_valid": true}
}
```

Response `200 OK` (validation failure):
```json
{
  "source_id": "<uuid>",
  "status": "unreachable",
  "checked_at": "2026-05-13T12:00:00Z",
  "error": "Source path does not exist: /path/to/missing"
}
```

Status values: `ok`, `unreachable`, `auth_failed`, `permission_denied`, `config_invalid`.

---

## API contract changes (still needed for #87/#171)

### List sources (already includes validation fields)
```http
GET /admin/sources
Authorization: Bearer <token>
```

Response includes:
```json
  "last_validation_status": "ok",
  "last_validation_error": null,
  "last_validated_at": "2026-05-13T12:00:00Z"
```

---

## Secret redaction and sanitized-error rules

- `_sanitize_source_error()` redacts sensitive config values (`password`,
  `api_token`, `api_key`, `secret`, `private_key`) from error messages.
- Sensitive values are matched by exact string replacement — avoid
  single-character values that could match common text.
- All connector errors returned to the frontend are sanitized before leaving
  the endpoint.
- The test-connection endpoint returns errors in the `error` field of a `200`
  response, not as HTTP exception details.

---

## Frontend surfaces affected

| Surface | Issue | Status |
|---------|-------|--------|
| Admin sources list | #87/#170 | Done (validation fields, test button) |
| Source create/edit modal | #170 | Partial (error display) — inline hints pending |
| Sync job history table | #171 | Not started |
| Source detail page | #171 | Not started |
| DLQ quick-link | #171 | Not started |

---

## Merge order inside `feature/admin-source-ux`

1. ~~#242 — Original plan doc~~ (merged)
2. ~~PR #243 / #170 — Connector validation~~ (merged)
3. **Next: #87 remaining** — Sync usability polish (fresh PR, avoid duplicating #243)
4. **Then: #171** — Sync/failure status UI

After all items land, a final integration PR merges `feature/admin-source-ux -> main`.

---

## Validation checklist before `feature/admin-source-ux -> main`

- [ ] #87 remaining PR merged (or verified unnecessary).
- [ ] #171 PR merged.
- [ ] `pytest` suite passes (no regressions).
- [ ] `ruff check` and `ruff format` pass.
- [ ] `mypy src --strict` passes (pre-existing errors exempted).
- [ ] Frontend build, lint, and typecheck pass.
- [ ] Manual smoke: create source, test connection, trigger sync, view results.
- [ ] Manual smoke: sanitized errors do not leak secrets.
- [ ] `CHANGELOG.md` updated for the admin source UX track.

---

## Operator documentation checklist

This is a separate docs task (not part of any specific issue). Candidate docs to update:

- `docs/operations/production-compose.md` — how to test connections, interpret
  validation statuses and sync summaries, handle sanitized errors.
- `docs/context/frontend.md` — admin source UX surfaces (source list, test
  connection, sync history).
- `docs/context/backend-api.md` — test-connection and sync job API contracts.
- `README.md` — brief admin source management section if missing.

### Key concepts operators should understand

- **Validation statuses:** `ok`, `unreachable`, `auth_failed`,
  `permission_denied`, `config_invalid`. Indicate whether a source
  configuration is valid and reachable.
- **Sync summary counts:** `indexed`, `skipped`, `failed` — documents
  processed per sync run.
- **Sanitized errors:** Connector secrets are redacted from error messages
  before they reach the admin UI. An error like "Source path does not exist"
  or "Authentication failed" indicates the issue without exposing credentials.
- **Retry and DLQ:** Failed documents land in the Dead Letter Queue (DLQ) for
  manual retry. The DLQ is accessible from the admin API.
