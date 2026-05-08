# Phase 06: Intelligence Layer

## Goal

Add best-effort local LLM intelligence without blocking ingestion.

## Architecture Decision

**IntelligenceWorker (Option C)** — a standalone class called from `PipelineWorker` after `update_indexed()` completes. If Ollama fails, log warning and swallow exception. Ingestion is never blocked. No DLQ. No Kafka consumer (direct call for MVP).

## Scope

### In Scope

1. **Database schema** — 4 new tables:
   - `document_summaries` (doc_id PK, summary, model, timestamps)
   - `entities` (id PK, name, type with CHECK constraint)
   - `document_entities` (doc_id + entity_id PK, frequency)
   - `document_tags` (doc_id + tag PK)

2. **Ollama client** — `src/services/intelligence/ollama_client.py`
   - `generate(prompt: str, model: str | None = None) -> str`
   - Wraps `POST /api/generate` with 120s timeout
   - Returns raw response text

3. **Intelligence worker** — `src/services/intelligence/worker.py`
   - `IntelligenceWorker` class with `process_document(doc_id, content)`
   - Reads enabled tasks from `system_config` (feature.summarization, etc.)
   - Runs tasks in order: summarize → extract_entities → auto_tag
   - Each task: call Ollama, parse JSON where needed, upsert to Postgres, update ES
   - Failure behavior: log warning, skip remaining tasks, **no DLQ, no re-raise**

4. **Repository** — `src/services/intelligence/repository.py`
   - `IntelligenceRepository` with upsert methods for summaries, entities, tags
   - Entity deduplication by `(name, type)`

5. **API endpoints** — add to `src/services/api/main.py`
   - `GET /documents/{doc_id}/summary` — returns summary or 404
   - `GET /documents/{doc_id}/entities` — returns entity list
   - `GET /documents/{doc_id}/tags` — returns tag list
   - `POST /admin/intelligence/{doc_id}/trigger` — admin re-run intelligence

6. **Integration with PipelineWorker**
   - After `update_indexed()`, call `IntelligenceWorker.process_document()` with `content_english`
   - Only if document has `translation_quality` (fast or high) — skip raw untranslated docs

7. **Update ES index mapping**
   - Add `entities` keyword field alongside existing `summary` and `tags`

### Out of Scope / Deferred

- **Alert matching** — requires `subscriptions` table (Phase 07). We'll add the `alerts.check_on_ingest` flag to `system_config` but the actual matching logic is deferred. Phase 07 spec must be updated to include this.
- **Kafka topic consumer** — the spec mentions `documents.intelligence` Kafka topic. For MVP we call the worker directly. Kafka wiring is Phase 08.
- **Metrics** — `llm_request_duration_seconds`, `alert_notifications_created_total` are Phase 08 observability.

---

## Data Model

```sql
-- Auto-generated summary per document
CREATE TABLE document_summaries (
    doc_id UUID PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    summary TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Named entity registry (deduped by name + type)
CREATE TABLE entities (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('person', 'organization', 'location', 'date')),
    UNIQUE (name, type)
);

-- Document entity many-to-many
CREATE TABLE document_entities (
    doc_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    frequency INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (doc_id, entity_id)
);
CREATE INDEX ix_document_entities_entity_id ON document_entities (entity_id);

-- Auto-assigned topic tags
CREATE TABLE document_tags (
    doc_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (doc_id, tag)
);
CREATE INDEX ix_document_tags_tag ON document_tags (tag);
```

---

## New Files

| File | Purpose |
|------|---------|
| `src/services/intelligence/__init__.py` | Package init |
| `src/services/intelligence/ollama_client.py` | HTTP client for Ollama `/api/generate` |
| `src/services/intelligence/worker.py` | `IntelligenceWorker` — orchestrates tasks |
| `src/services/intelligence/repository.py` | `IntelligenceRepository` — DB upserts |
| `tests/unit/test_intelligence_repository.py` | Repository unit tests |
| `tests/unit/test_ollama_client.py` | Mocked Ollama client tests |
| `tests/integration/test_intelligence_api.py` | API endpoint tests |
| `tests/integration/test_intelligence_worker.py` | End-to-end worker tests |
| `tests/integration/test_intelligence_failure.py` | Failure/isolation tests |
| `migrations/versions/XXX_add_intelligence_tables.py` | Alembic migration |

---

## Updated Files

| File | Change |
|------|--------|
| `src/services/api/main.py` | Add `GET /documents/{doc_id}/summary`, `/entities`, `/tags`; add `POST /admin/intelligence/{doc_id}/trigger` |
| `src/services/pipeline/worker.py` | After `update_indexed()`, call `IntelligenceWorker.process_document(doc_id, translated_text)` |
| `src/services/search/elastic.py` | Update index mapping: add `entities` keyword field |
| `CHANGELOG.md` | Add Phase 06 entry |

---

## IntelligenceWorker Task Flow

```
process_document(doc_id, content):
  1. Check enabled tasks from system_config
  2. If no tasks enabled → return
  3. For each task:
     - Call Ollama with prompt + content slice
     - Parse response (JSON for entities/tags, plain text for summary)
     - Upsert to Postgres
     - Update Elasticsearch document
     - On any exception → log, break loop, do NOT re-raise
```

| Task | Prompt source | Content limit | Parses JSON? | Stores in | Updates ES? |
|------|-------------|---------------|--------------|-----------|-------------|
| Summarize | `llm.summarization_prompt` | 8000 chars | No | `document_summaries` | `summary` field |
| Extract Entities | `llm.entity_extraction_prompt` | 6000 chars | Yes `[{name,type}]` | `entities` + `document_entities` | `entities` keyword |
| Auto Tag | `llm.auto_tag_prompt` | 4000 chars | Yes `["tag1",...]` | `document_tags` (replace) | `tags` keyword |

---

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/documents/{doc_id}/summary` | Document access | Return summary or 404 |
| GET | `/documents/{doc_id}/entities` | Document access | Return entity list |
| GET | `/documents/{doc_id}/tags` | Document access | Return tag list |
| POST | `/admin/intelligence/{doc_id}/trigger` | Admin | Re-run intelligence on document |

---

## Integration with PipelineWorker

After `update_indexed()` in `PipelineWorker._run()`:

```python
if doc.translation_quality in ("fast", "high"):
    try:
        intelligence_worker.process_document(doc.id, translated)
    except Exception:
        logger.exception("Intelligence failed for doc_id=%s", doc.id)
        # Do NOT re-raise, do NOT set status=failed
```

---

## Validation

### Unit tests
- `test_intelligence_repository.py` — upsert summary, dedup entity, replace tags
- `test_ollama_client.py` — mocked httpx, timeout handling, JSON parsing

### Integration tests
- `test_intelligence_api.py` — GET summary/entities/tags, 404 when absent, permission filtering
- `test_intelligence_worker.py` — mocked Ollama, verify DB state + ES update after processing
- `test_intelligence_failure.py` — Ollama 503, verify ingestion not blocked, no DLQ

### Expected metrics
- **New tests:** 12-15
- **Total tests:** ~223-226
- **Coverage floor:** ≥ 90%

---

## Acceptance Criteria

- [ ] Enabled tasks update Postgres and Elasticsearch
- [ ] Disabled tasks are skipped
- [ ] Ollama failures are logged and do not block document ingestion
- [ ] Admin can re-trigger intelligence on any document
- [ ] All endpoints have integration tests
- [ ] Coverage stays ≥ 90%

---

## Deferred Work

- **Alert matching** → Phase 07 (requires subscriptions/notifications tables)
- **Kafka consumer** → Phase 08
- **Metrics** → Phase 08
