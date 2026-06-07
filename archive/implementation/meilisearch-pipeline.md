# Meilisearch Indexing Pipeline — Decisions

> **Current state (June 2026):** Elasticsearch fully removed (PR #573, 2026-05-30).
> Meilisearch is the sole BM25 backend. The pipeline now uses RabbitMQ (not Kafka).
> The dual-write shadow-indexing migration completed — there is no longer an
> Elasticsearch path. The feature-flag gating (`FEATURE_MEILISEARCH_SHADOW_INDEX`)
> and ES client path were removed. The write flow below is historical;
> the current pipeline writes exclusively to Meilisearch via RabbitMQ consumers.

**Scope:** Write flow, task polling, stale chunk detection, translation patching,
document deletion, and production reindex strategy.
**Does not cover:** Index settings (#301), ACL filter (#302), multilingual routing (#304).
**Companion file:** `src/services/search/meili_provider.py`

---

## Separation of concerns

`MeilisearchSearchProvider` is a thin Meilisearch client wrapper. It knows how
to call the Meilisearch API. It does not know about:
- The document repository or DB state
- Retry scheduling or DLQ routing
- Kafka/event bus integration
- Pipeline worker orchestration

Those responsibilities belong to `PipelineWorker` (and its future Kafka-based
successor). The provider exposes clean primitives; the pipeline layer composes them.

---

## Write flow

```
1. Write document to DB (status: "pending")
2. Publish "document.created" event (Kafka in original design; now RabbitMQ)

[Pipeline consumer]
3. Load document from DB
4. Extract text
5. Chunk text → list of (chunk_index, content, heading, section_path, ...)
6. Build SearchChunkRecord per chunk via SearchChunkRecord.from_parts()
   - allowed_group_ids from source_group_ids (same as existing Elasticsearch path)
   - contentChecksum set automatically
   - indexedAt set automatically
7. provider.index_batch(records) → taskId
8. Poll task_status(taskId) until "succeeded" or timeout
9. Update doc status → "indexed"

[Translation consumer — async, after step 9]
10. Translate content fields (LibreTranslate)
11. provider.patch_translations(chunk_id, {content_en: ..., title_en: ...}) per chunk
    - Partial update: does not touch content, contentChecksum, allowed_group_ids
12. Mark translation version → "available"

[Intelligence consumer — best-effort, parallel]
13. Generate summary, tags, entities
14. Partial update on affected chunk fields
```

Original-language chunks are searchable immediately after step 9. Translated
fields arrive asynchronously without blocking search availability.

---

## Meilisearch task polling

Every mutating Meilisearch call (`add_documents`, `delete_documents_by_filter`,
`update_documents`, `swap_indexes`) returns a task ID. The task completes
asynchronously. The pipeline must poll until the task succeeds before marking
a document as indexed.

Polling strategy:
- Check status after 200 ms, then after 500 ms, then every 1 s
- Timeout after 30 s → treat as a failed indexing attempt (retry the whole chunk batch)
- Do not use `wait_for_task` in production paths — it blocks the event loop

The provider exposes `task_status(task_id)` so the caller controls polling.

---

## Failed indexing jobs

The provider itself does not retry. The pipeline layer owns retry logic:
- Up to 3 attempts with exponential backoff (2 s, 8 s, 32 s)
- After 3 failures: write to DLQ (`search_index_failures` DB table or Kafka DLQ topic)
- Record: `documant_id`, `chunk_index`, `failed_at`, `error_type`, `attempts`
- Admin `/admin/readiness` probe includes a Meilisearch health check
- DLQ entries are retried manually or via a background admin action

---

## Stale chunk detection (reindex of a single document)

When a document's content changes and must be reindexed:

```
1. Fetch existing chunk records for document_id via filtered search:
   filter: document_id = "<id>", limit: 10 000
   → {chunk_id → contentChecksum}

2. Compute new chunks from updated content

3. For each new chunk:
   - If chunk_id exists AND contentChecksum matches → skip (unchanged)
   - If chunk_id exists AND contentChecksum differs → upsert (changed content)
   - If chunk_id is new → upsert (document grew)

4. Delete chunk_ids that exist in the old set but not the new set
   (document shrank — those chunk records are now orphaned)
```

This minimises write amplification for minor edits (e.g., a metadata update
that changes only the first few chunks).

---

## Document deletion

When a document is deleted from the DB:

```
provider.remove_by_document_id(document_id)
```

This issues a `delete_documents_by_filter` call on Meilisearch with
`document_id = "<id>"`, removing all chunks for that document atomically.
It mirrors the existing `QdrantSearchClient.delete_by_doc_id` pattern.

---

## Translation patching

`patch_translations` sends a partial update — only the translation fields plus
the primary key:

```python
{"id": chunk_id, "content_en": "...", "title_en": "..."}
```

Meilisearch's `update_documents` merges this with the existing record.
`content`, `contentChecksum`, `allowed_group_ids`, and `indexedAt` are not
touched. This is the correct behaviour — the original-language content and ACL
fields must not be overwritten by a translation patch.

---

## Production reindex (swap-indexes)

Never drop the live index. The safe reindex sequence is:

```
1. provider.prepare_shadow_index()
   - Creates "documents_shadow" with the same settings as "documents"
   - Safe to call even if shadow already exists (idempotent)

2. Pipeline feeds all documents to the shadow index:
   provider.index_batch(records)  [with shadow=True]

3. Validate shadow index with sample queries

4. provider.swap_indexes()
   - Calls Meilisearch swapIndexes atomically
   - "documents" becomes the former shadow; "documents_shadow" becomes the former live
   - Live queries are uninterrupted

5. Drop former live (now "documents_shadow") after N hours of stable operation:
   provider.drop_shadow_index()
```

The `feature/meilisearch-search` feature flag gates all of this. The shadow
index approach is also used when index settings change (e.g., adding a new
filterable attribute) — change settings on the shadow, reindex, swap.

---

## Dual-write (historical — migration completed)

> **Note:** This section describes the migration cutover strategy. The dual-write
> phase completed. Elasticsearch has been removed. Meilisearch is now the sole
> BM25 backend — there is no shadow-indexing against Elasticsearch.

When `FEATURE_MEILISEARCH_SHADOW_INDEX=true` and `FEATURE_MEILISEARCH_SEARCH=false`:
- The pipeline wrote to both Elasticsearch (live) and Meilisearch (shadow)
- Search queries still went to Elasticsearch
- This validated Meilisearch correctness before cutover

The provider's `index_batch` / `remove_by_document_id` are called unconditionally
in this mode. The pipeline worker checks the feature flag and calls the appropriate
clients.

---

## Acceptance criteria

- [ ] `MeilisearchSearchProvider` implements all methods listed in the interface
- [ ] `index_batch` and `remove_by_document_id` exist as first-class methods
- [ ] `patch_translations` uses `update_documents` (partial) — not `add_documents` (full replace)
- [ ] `search` calls `needs_acl_short_circuit` before querying; returns empty on True
- [ ] `search` calls `build_permission_filter` and `compose_filters` from `meili_acl`
- [ ] `prepare_shadow_index` and `swap_indexes` exist for safe reindex
- [ ] `task_status` and `health_check` exist for observability
- [ ] User-filter construction handles all `DocumentSearchFilters` fields
- [ ] Sort mapping covers all four `DocumentSearchQuery.sort` values
- [ ] `mypy src --strict` passes
