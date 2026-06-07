# Translation Versions Implementation Plan

## Goal

Expand manual translation from a single high-quality state into versioned
translation history. Users can request a new translation, keep reading the
current version while it runs, and choose original, fast, or high-quality/manual
versions in document preview.

Design source: `docs/design/translation-versions-spec.md`.

## Phase Placement

Branch: `developer/phase-05c-translation-versions`

Status: In progress (follows completed Phase 05b).

Frontend implementation belongs in `developer/ui-02-document-preview`, as
described in `docs/implementation/phase-08b-frontend-ui.md`.

## Dependencies

- Phase 03e preview APIs.
- Phase 05a view tracking and preview service.
- Phase 05b translation queue and slow worker.
- Existing document permission checks.
- Existing search reindexing utilities.

## Backend Scope

### Compatibility Rule

Keep `documents.translation_quality` as a summary field for existing search and
preview surfaces:

- `null`: original only or no translated content.
- `fast`: at least one fast translation exists.
- `pending_high`: a high-quality/manual version is queued or running.
- `high`: at least one high-quality/manual version is available.

The UI should prefer version metadata when the new endpoints are available.

### Data Model

Add a `document_translation_versions` table:

```sql
CREATE TABLE document_translation_versions (
    id UUID PRIMARY KEY,
    documant_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    label TEXT NOT NULL,
    source_language TEXT NULL,
    target_language TEXT NOT NULL,
    quality TEXT NOT NULL,
    request_type TEXT NOT NULL,
    status TEXT NOT NULL,
    provider TEXT NULL,
    requested_by_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    requested_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE NULL,
    completed_at TIMESTAMP WITH TIME ZONE NULL,
    error_summary TEXT NULL,
    request_note TEXT NULL,
    source_content_hash TEXT NULL,
    translated_text TEXT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (documant_id, version_number)
);

CREATE INDEX ix_translation_versions_doc_id
    ON document_translation_versions (documant_id);
CREATE INDEX ix_translation_versions_status
    ON document_translation_versions (status);
CREATE INDEX ix_translation_versions_requested_by
    ON document_translation_versions (requested_by_id);
```

Constraints:

- `quality IN ('fast', 'high')`
- `request_type IN ('ingestion', 'manual', 'auto_enrich')`
- `status IN ('available', 'pending', 'running', 'failed', 'canceled')`

Storage note:

- Store translated text in Postgres `TEXT` for the first implementation.
- If preview payloads become too large, add a later storage abstraction with
  `text_storage_ref` without changing the UI contract.

### Version Creation

Fast ingestion:

- Optionally backfill a `fast` version from already indexed fast translations
  when the source text is available.
- If backfill is not practical in the first PR, start versioning for new manual
  high-quality translations and document the compatibility behavior.

Manual request:

- Create a pending version with the next `version_number`.
- Deduplicate same document/target-language requests while one is pending or
  running.
- Keep the current preview version selected.
- Return the pending version record.

Auto-enrich:

- Create an `auto_enrich` high-quality version instead of only mutating
  `documents.translation_quality`.
- Reuse the same worker path as manual requests.

Worker:

- Move version from `pending` to `running`.
- Extract source text.
- Translate to target language.
- Store translated text on the version row.
- Mark version `available`.
- Update `documents.translation_quality` summary.
- Reindex canonical search payload using the newest available high-quality
  version for the target language chosen by product defaults.
- On failure, mark only the version `failed`; do not set the document status to
  failed and do not send enrichment failures to DLQ.

### API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/documents/{documant_id}/translation-versions` | Document access | List versions |
| POST | `/documents/{documant_id}/translation-versions` | Document access | Request manual translation |
| POST | `/documents/{documant_id}/translation-versions/{version_id}/retry` | Admin or allowed requester | Retry failed version |
| GET | `/preview/{documant_id}?translation_version_id=...` | Document access | Render selected version |

Compatibility endpoint:

- Keep `POST /documents/{documant_id}/translate` as an alias for creating a
  high-quality manual version until clients migrate.

Contracts are defined in `docs/design/translation-versions-spec.md`.

### Preview Behavior

- Without `translation_version_id`, return the default version.
- With a valid available version, render that version.
- With pending/failed/unavailable version, return metadata plus a safe fallback
  to original/default content.
- Include `translation_versions` metadata in preview responses when available.
- Preserve document permission enforcement exactly as regular preview.

### Search Behavior

Initial implementation:

- Search indexes one canonical translated representation per document.
- Canonical version is newest available high-quality version when present,
  otherwise fast translation, otherwise original.
- Search result metadata can include selected/default translation quality but
  does not expose all versions.

Later extension:

- Multi-version search can index each version separately if product need
  emerges.

## Frontend Scope

Implement in UI Phase 02:

- Translation version selector in document toolbar.
- Request translation dialog.
- Version status menu with original, fast, high-quality/manual, pending, and
  failed states.
- Preview rerender when selecting an available version.
- URL support for `translation_version`.
- Toast when a pending version becomes available.
- Safe fallback when a linked version is unavailable.

## Validation

### Unit Tests

- Version numbering increments per document.
- Pending/running deduplication works for same target language.
- Default version selection follows spec priority.
- Summary `translation_quality` is updated from versions.
- Worker failure marks version failed without failing the document.

### Migration Tests

- Table, constraints, indexes, and uniqueness exist.
- Multiple versions per document are allowed.
- Duplicate version numbers per document are rejected.
- Long translated text can be stored.

### API Tests

- User with document access can list versions.
- User without document access cannot infer versions.
- Manual request creates pending version.
- Duplicate pending request returns existing pending version or a clear
  already-queued response.
- Retry works only for authorized users.
- Preview renders selected available version.
- Preview falls back safely for pending/failed/invalid versions.

### Worker/Search Tests

- Manual version moves pending -> running -> available.
- Auto-enrich creates a version.
- Available version reindexes canonical search content.
- Failed translation preserves previous searchable content.

### UI Tests

- Request translation and keep current preview visible.
- Select original, fast, and manual versions.
- Pending and failed versions are understandable and not selectable as content.
- Deep link to a version works when authorized.
- Invalid deep link falls back safely.

## Acceptance Criteria

- Manual translation creates a version record.
- Users can list and select available translation versions.
- Pending versions do not interrupt reading.
- Failed versions do not break preview or search.
- Existing translation endpoints remain backward compatible.
- Permission checks protect every version endpoint.
- Search remains stable while versioned translation is introduced.

Stop after opening the PR for Reviewer-agent review.
