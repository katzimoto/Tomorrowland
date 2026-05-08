# Phase 05: Preview And Enrichment

## Goal

Expand document preview support and implement high-quality translation flow.

## Sub-Phases

| Sub-Phase | Focus | PR | Status |
|---|---|---|---|
| 05a | Preview service with truncated snippets and per-user view tracking | #10 | ✅ Merged |
| 05b | Translation enrichment: manual request, auto-enrich threshold, slow worker | #11 | ⏳ Planned |

---

## Phase 05a: Preview Service & View Tracking

### Scope

- **Preview endpoint enhancement:** `GET /preview/{doc_id}` returns document
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

- Every successful `GET /preview/{doc_id}` call inserts or updates a row in
  `document_views`.
- The table has `(doc_id, user_id)` uniqueness to prevent duplicate counting
  within a reasonable window. For Phase 05a MVP, a simple INSERT with
  `ON CONFLICT DO NOTHING` is sufficient.
- Global view count per document is derived as `COUNT(DISTINCT user_id)` from
  `document_views`.

### Migration

```sql
CREATE TABLE document_views (
    id UUID PRIMARY KEY,
    doc_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    viewed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(doc_id, user_id)
);
CREATE INDEX ix_document_views_doc_id ON document_views(doc_id);
CREATE INDEX ix_document_views_user_id ON document_views(user_id);
```

### Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/preview/{doc_id}` | User | Enhanced preview with snippet + view count |
| GET | `/me/activity` | User | Own document view history |

### Validation

- Preview returns correct snippet for each supported MIME type.
- View tracking increments on preview and deduplicates by user.
- User activity shows only own views; admin activity shows all views.
- Permission filtering: unauthorized documents return 403.

---

## Phase 05b: Translation Enrichment Pipeline

### Scope

- **Manual translation endpoint:** `POST /documents/{doc_id}/translate` queues
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
5. Re-index full document in Elasticsearch.
6. Re-index chunks in Qdrant (upsert overwrites existing points).
7. Update `documents.translation_quality = 'high'` and `status = 'indexed'`.
8. Log completion with correlation ID.

On failure: log error, set `status = 'failed'`, do **not** add to DLQ
(enrichment is best-effort).

### Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/documents/{doc_id}/translate` | User | Request high-quality translation |
| GET | `/admin/enrichment-queue` | Admin | View pending enrichments |

### Validation

- Manual request sets `translation_quality` to `pending_high`.
- Auto-enrich fires exactly once when threshold is crossed.
- Slow worker reindexes successfully.
- Slow worker failure does not break existing index or block ingestion.
- Re-enriched document updates both BM25 and vector indexes.

---

## Acceptance Criteria (Both Sub-Phases)

- Supported file types return stable preview responses with truncated snippets.
- Manual and automatic enrichment queue work exactly once while pending.
- Re-enriched documents update both search indexes.
- All endpoints have integration tests.
- Coverage stays ≥ 90%.
