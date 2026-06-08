# Phase 05: Preview And Enrichment

## Goal

Expand document preview support and implement high-quality translation flow.

## Sub-Phases

| Sub-Phase | Focus | PR | Status |
|---|---|---|---|
| 05a | Preview service with truncated snippets and per-user view tracking | #10 | ✅ Merged |
| 05b | Translation enrichment: manual request, auto-enrich threshold, slow worker | #12 | ✅ Merged |
| 05c | Translation versions and selectable preview versions | TBD | ⏳ Planned |

---

## Phase 05a: Preview Service & View Tracking

### Scope

- **Preview endpoint enhancement:** `GET /preview/{documant_id}` returns document
  metadata + truncated content snippet (first 2000 chars) + view statistics.
- **Per-user view tracking:** `document_views` table records each preview access
  by user and document.
- **User activity:** `GET /me/activity` returns the authenticated user's own
  document view history.
- **Admin activity:** `GET /admin/activity` (already implemented in Phase 04)
  shows global activity including document views.

### Preview Content Format

- **Text / Markdown / CSV / JSON / XML / RTF / Email:** plain text snippet,
  truncated to 2000 characters.
- **HTML:** sanitized plain-text snippet. Tags are stripped by the extractor;
  a defense-in-depth regex pass also removes scripts, event handlers, and
  `javascript:` URLs. Returns first 2000 chars.
- **PDF / DOCX / PPTX / XLSX / ODT:** plain text extraction result, truncated.
- **Archive (ZIP, TAR):** list of top-level filenames as string preview.

### View Tracking Behavior

- Every successful `GET /preview/{documant_id}` call inserts or updates a row in
  `document_views`.
- The table has `(documant_id, user_id)` uniqueness to prevent duplicate counting
  within a reasonable window. For Phase 05a MVP, a simple INSERT with
  `ON CONFLICT DO NOTHING` is sufficient.
- Global view count per document is derived as `COUNT(DISTINCT user_id)` from
  `document_views`.

### Migration

```sql
CREATE TABLE document_views (
    id UUID PRIMARY KEY,
    documant_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    viewed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(documant_id, user_id)
);
CREATE INDEX ix_document_views_doc_id ON document_views(documant_id);
CREATE INDEX ix_document_views_user_id ON document_views(user_id);
```

### Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/preview/{documant_id}` | User | Enhanced preview with snippet + view count |
| GET | `/me/activity` | User | Own document view history |

### Validation

- Preview returns correct snippet for each supported MIME type.
- View tracking increments on preview and deduplicates by user.
- User activity shows only own views; admin activity shows all views.
- Permission filtering: unauthorized documents return 403.

---

## Phase 05b: Translation Enrichment Pipeline

### Scope

- **Manual translation endpoint:** `POST /documents/{documant_id}/translate` queues
  a document for high-quality re-translation.
- **Auto-enrich threshold:** When a document's distinct viewer count exceeds
  `system_config.auto_enrich.threshold` (default: 5) and
  `translation_quality` is not `'high'`, auto-queue for enrichment.
- **Slow worker:** `SlowWorker` class re-translates, re-chunks, and re-indexes
  documents with `translation_quality = 'high'`.
- **Admin queue visibility:** `GET /admin/enrichment-queue` lists pending
  enrichments.

### Translation State Machine

```
null  --fast worker-->  "fast"
"fast" --manual/auto-->  "pending_high"  --slow worker-->  "high"
null  --manual/auto-->  "pending_high"  --slow worker-->  "high"
```

### Slow Worker Behavior

1. Extract text from source file (reuse extraction registry).
2. Translate via LibreTranslate with source language detection.
3. Chunk translated text.
4. Encode chunks with `MockEncoder`.
5. Re-index full document in the search index (originally Elasticsearch, now Meilisearch).
6. Re-index chunks in Qdrant (upsert overwrites existing points).
7. Update `documents.translation_quality = 'high'` and `status = 'indexed'`.
8. Log completion with correlation ID.

On failure: log error, set `status = 'failed'`, do **not** add to DLQ
(enrichment is best-effort).

### Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/documents/{documant_id}/translate` | User | Request high-quality translation |
| GET | `/admin/enrichment-queue` | Admin | View pending enrichments |

### Validation

- Manual request sets `translation_quality` to `pending_high`.
- Auto-enrich fires exactly once when threshold is crossed.
- Slow worker reindexes successfully.
- Slow worker failure does not break existing index or block ingestion.
- Re-enriched document updates both BM25 and vector indexes.

---

## Phase 05c: Translation Versions

Detailed plan: `docs/implementation/phase-05c-translation-versions.md`.

### Scope

- Add `document_translation_versions` persistence.
- Keep `documents.translation_quality` as a backward-compatible summary field.
- Create translation versions for manual and auto-enrich requests.
- Allow preview to render a selected translation version.
- Keep current preview content visible while new translation versions are
  pending.
- Preserve `POST /documents/{documant_id}/translate` as a compatibility alias until
  UI clients migrate.

### Data Model

```sql
CREATE TABLE document_translation_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    documant_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    label TEXT NOT NULL,
    source_language TEXT NULL,
    target_language TEXT NOT NULL DEFAULT 'en',
    quality TEXT NOT NULL CHECK (quality IN ('fast', 'high')),
    request_type TEXT NOT NULL CHECK (request_type IN ('ingestion', 'manual', 'auto_enrich')),
    status TEXT NOT NULL CHECK (status IN ('available', 'pending', 'running', 'failed', 'canceled')),
    provider TEXT NULL,
    requested_by_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    requested_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE NULL,
    completed_at TIMESTAMP WITH TIME ZONE NULL,
    error_summary TEXT NULL,
    request_note TEXT NULL,
    source_content_hash TEXT NULL,
    translated_text TEXT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    UNIQUE (documant_id, version_number)
);

CREATE INDEX ix_translation_versions_doc_id ON document_translation_versions (documant_id);
CREATE INDEX ix_translation_versions_status ON document_translation_versions (status);
CREATE INDEX ix_translation_versions_requested_by ON document_translation_versions (requested_by_id);
```

### Version State Machine

```
pending -> running -> available
pending -> running -> failed
pending -> canceled (admin only)
```

### Backend Changes

1. **Migration** — create `document_translation_versions` table with constraints and indexes.
2. **Model** — add `DocumentTranslationVersion` Pydantic model.
3. **Repository** — add `TranslationVersionRepository` with:
   - `create_version(documant_id, label, quality, request_type, requested_by_id, target_language='en')`
   - `list_versions(documant_id)`
   - `get_pending_versions(documant_id)`
   - `update_version_status(version_id, status, translated_text=None, error_summary=None)`
   - `get_next_version_number(documant_id)`
   - `find_pending_or_running(documant_id, target_language)` (deduplication)
4. **API endpoints**:
   - `GET /documents/{documant_id}/translation-versions` — list versions with permission check.
   - `POST /documents/{documant_id}/translation-versions` — create pending version, dedupe if pending/running exists for same target language.
   - `POST /documents/{documant_id}/translate` — compatibility alias that creates a `manual` high-quality version.
5. **PreviewService** — accept optional `translation_version_id`. If provided and version is `available`, return `translated_text` as snippet source. Otherwise fall back to default (extract from file).
6. **SlowWorker** — refactor to process pending versions:
   - Query pending versions instead of documents with `translation_quality = 'pending_high'`.
   - For each pending version: set `running`, extract, translate, store `translated_text`, set `available`.
   - Update `documents.translation_quality = 'high'` after first available high-quality version.
   - On failure: set version `failed`, log error, do NOT set document status to failed.
7. **Auto-enrich** — `_maybe_auto_enrich` creates an `auto_enrich` version instead of directly setting `translation_quality = 'pending_high'`.

### Validation

- Version migrations, constraints, and indexes are tested.
- Manual request creates a pending version.
- Duplicate pending request for same target language returns existing pending version (409 or 200 with existing).
- Slow worker marks versions available or failed without failing the document.
- Preview renders selected versions and falls back safely.
- Search remains stable while versioned translations are introduced.
- `POST /documents/{documant_id}/translate` backward compatibility preserved.

---

## Acceptance Criteria (All Sub-Phases)

- Supported file types return stable preview responses with truncated snippets.
- Manual and automatic enrichment queue work exactly once while pending.
- Re-enriched documents update both search indexes.
- Translation versions are persisted and selectable.
- Existing `POST /documents/{documant_id}/translate` remains backward compatible.
- All endpoints have integration tests.
- Coverage stays ≥ 90%.
