# Search Context

Use this map for Meilisearch (BM25/keyword), Qdrant (vector/semantic), hybrid search, ranking, query behavior, and search-related tests.

## Main files

- `src/services/search/` — Meilisearch provider, Qdrant client, hybrid merge, search orchestration.
- `src/services/documents/` — document metadata that search may depend on.
- `src/services/api/routers/search.py` — search routes if API behavior changes.
- `src/services/api/main.py` — search backend initialization (Meilisearch client creation).
- Search-related tests under `tests/unit/` and `tests/integration/`.

## Common tests

```bash
pytest tests/unit/test_*search*.py -q
pytest tests/integration/test_*search*.py -q
```

If exact test names are unknown, use `rg --files tests | rg search` before opening files.

## Patterns to preserve

- Keep Meilisearch/Qdrant boundaries explicit.
- Avoid changing ranking semantics unless the mission says so.
- Preserve permission filtering before returning protected document results.
- Mock or stub external services in unit tests.
- Use integration fixtures for real persistence/search boundary checks.

## Do not touch unless required

- extraction handlers
- frontend UI files
- migrations unless search schema/index metadata changes require them
- `spec.md`
- `spec-v4.pdf`

## Discovery commands

```bash
rg "<query-or-symbol>" src/services/search src/services/api tests
rg --files src/services/search tests | rg search
```

## Uniform filter enforcement (#759)

Added 2026-06-13. All `/search` filters apply equally to both Meilisearch
(BM25) and Qdrant (vector) results.

### How it works

1. **`_map_filters(raw)`** in `search.py` converts the frontend `filters` dict
   into `DocumentSearchFilters`.  It now also maps `date_to` → `created_before`
   (previously left client-side).

2. **Meilisearch**: `_build_user_filter` in `meili_provider.py` translates
   every `DocumentSearchFilters` field into a Meilisearch filter expression,
   including the new `created_before` → `metadata.created_at <= "..."`.

3. **Qdrant payload push**: `_qdrant_extra_conditions(filters)` returns a list
   of `FieldCondition` objects for payload fields stored at index time.
   Currently only `language` → `source_language` is pushed.  These are passed
   to `QdrantSearchClient.search(extra_conditions=...)` so Qdrant can pre-filter
   vector candidates before returning them.

4. **Post-retrieval predicate**: `_matches_filters(doc, filters)` is applied to
   every entry in the merged result list after `DocumentRow` enrichment and
   before pagination.  It checks all supported filters against the authoritative
   `DocumentRow` fields (`source`, `mime_type`, `source_language`,
   `metadata["tags"]`, `metadata["file_extension"]`, `created_at`).  This is
   the definitive enforcement point — no out-of-filter Qdrant candidate can
   survive to the response.

### Adding a new filter

1. Add the field to `DocumentSearchFilters` in `meili_types.py`.
2. Map it in `_map_filters` (search router).
3. Add the Meilisearch expression to `_build_user_filter` (meili_provider).
4. If the field exists in the Qdrant payload, add a `FieldCondition` in
   `_qdrant_extra_conditions`.
5. Add the check to `_matches_filters`.
6. Add tests to `tests/unit/test_search_filter_predicate.py`.

### Tests

```bash
pytest tests/unit/test_search_filter_predicate.py -q
pytest tests/unit/test_search_qdrant.py -q -k extra_conditions
```

---

## Document versioning

Added in `feature/document-versioning` (#201 / #203 / #205).

### Default behavior — latest-only filter

Both Meilisearch and Qdrant queries must include an `is_latest = true` filter
by default. Remove it only when the caller sends `include_older_versions: true`.

```python
# Meilisearch filter
"is_latest = true"

# Qdrant
{"must": [{"key": "is_latest", "match": {"value": True}}]}
```

### `include_older_versions` flag

The `/search` request accepts `include_older_versions: bool = False`.
When `True`, omit the `is_latest` filter from both Meilisearch and Qdrant queries.
All result objects must include `version_number`, `is_latest`,
`has_newer_version`, and `latest_document_id` so the UI can label results.

### Version payload fields (Meilisearch and Qdrant)

```json
{
  "version_family_id":  "<uuid>",
  "version_number":     1,
  "is_latest":          true,
  "has_newer_version":  false,
  "latest_document_id": null
}
```

### Stale chunk / vector isolation

Old version chunks are stored under the old `document_id`; new version chunks
under the new `document_id`. The `is_latest = false` filter excludes old chunks
at query time — no deletion required for search correctness.

**Reindex caution**: version metadata columns (`is_latest`, `version_number`,
`version_family_id`) must be populated in the database before a full reindex.
If a reindex runs against a partially migrated state, older versions may
re-appear as `is_latest = true`.

### Permission ordering

Permission filters are applied before the version filter.
Older versions of inaccessible documents must not appear even when
`include_older_versions = true`.

### Discovery commands

```bash
rg "is_latest\|include_older_versions\|version_family" src/services/search src/services/api tests
pytest tests/unit/test_*search*.py tests/integration/test_*search*.py -q -k version
```

## Retrieval trace v2 — backend attribution and rerank deltas (#751)

Added 2026-06-13. Extends the RAG retrieval trace with decision-level diagnostic fields.

### New models in `src/services/rag/trace_models.py`

| Model | Fields | Purpose |
|---|---|---|
| `BackendAttributionTrace` | `backend`, `score`, `rank` | Per-backend score/rank before fusion |
| `RerankerDeltaTrace` | `input_rank`, `input_score`, `reranker_score`, `output_rank`, `dropped` | Cross-encoder rerank movement |
| `DegradedBackendInfo` | `backend`, `error_category` | Safe failure info — category string only |

### New fields on `RetrievalCandidateTrace`

- `backends: list[BackendAttributionTrace]` — which backends (`vector`/`bm25`/`metadata`/`translated`) contributed, with per-backend score and 1-based rank
- `fused_rank: int | None` — rank in the merged list after reciprocal-rank fusion
- `fused_score: float | None` — combined score after fusion
- `reranker_delta: RerankerDeltaTrace | None` — rerank movement; `None` when reranking was not applied
- `final_context_rank: int | None` — 1-based position in the LLM prompt context

### New fields on `RetrievalTrace`

- `trace_version: int = 2` — consumers can use this to detect v2 fields
- `degraded_backends: list[DegradedBackendInfo]` — one entry per failed backend
- `scope_filtered_count: int` — candidates removed by BM25 post-scope filtering
- `dedup_count: int` — candidates removed as cross-backend duplicates
- `score_threshold_filtered_count: int` — candidates removed below the score threshold
- `reranker_dropped_count: int` — candidates dropped by reranker min-score or top-n cutoff

### Backward compatibility

All new fields are optional with defaults. Existing v1 consumers of `stages`, `candidates`, `reranker_enabled`, `retrieval_degraded`, `total_latency_ms` are unaffected.

### Reranker score embedding

`CrossEncoderEndpointReranker` and `CrossEncoderReranker` in `src/services/rag/reranker.py` now embed `_reranker_score` (the raw cross-encoder or LLM score) into each returned chunk dict so `reranker_delta.reranker_score` can be populated.

### Return type change in `_retrieve_chunks`

Returns a 4-tuple: `(chunks, stages, retrieval_degraded, extras: _RetrievalExtras)`. The `extras` TypedDict carries `degraded_backends`, `scope_filtered_count`, `dedup_count`.

### Tests

```bash
pytest tests/unit/test_rag_trace.py -q
pytest tests/unit/test_rag_reranker.py -q
```

---

## `retrieval_degraded` flag (#698)

Added 2026-06-12. Surfaces when either Qdrant or Meilisearch is unavailable during a search request.

### Where it lives

| Layer | Location | Field |
|---|---|---|
| RAG service | `src/services/rag/service.py` — `_retrieve_chunks` return type | 3rd tuple element `retrieval_degraded: bool` |
| Trace model | `src/services/rag/trace_models.py` — `RetrievalTrace` | `retrieval_degraded: bool = False` |
| Search API | `src/services/api/schemas.py` — `SearchResponse` | `retrieval_degraded: bool = False` |
| Search router | `src/services/api/routers/search.py` | `retrieval_degraded` tracked from `_run_meilisearch`/`_run_qdrant` return values |
| Frontend types | `frontend/src/api/search.ts` — `SearchResponse`; `frontend/src/api/chat.ts` — `RetrievalTrace` | optional fields |
| Search UI | `frontend/src/features/search/SearchPage.tsx` | warning chip when `retrieval_degraded` |
| Chat UI | `frontend/src/features/chat/EvidencePanel.tsx` | warning chip in admin retrieval trace tab |

### Semantics

- `retrieval_degraded = True` when any backend (Qdrant or Meilisearch) throws an exception during the search futures.
- The encoder failing to produce a query vector (BM25-only fallback) also sets `retrieval_degraded = True` in the search router.
- Results are still returned from whichever backend remained healthy — the flag is visibility only, not a blocking error.
- The RAG `_retrieve_chunks` method tracks degradation independently; the search router has its own tracking via function return values.

### Tests

```bash
pytest tests/unit/test_rag_trace.py -q -k degraded
npx vitest run src/features/search/
```

---

## RAG embedding failure degradation (#760)

Added 2026-06-13. `_retrieve_chunks` degrades gracefully when `encoder.encode()` fails.

### Problem

Previously, `_retrieve_chunks` called `encoder.encode(question)` before launching any backend
futures. An embedding failure (provider down, model missing, timeout) exited the whole retrieval
path — no BM25 or metadata results were returned.

### New behavior

1. `encoder.encode()` is wrapped in try/except at the top of `_retrieve_chunks`, after
   `degraded_backends` is initialized.
2. If encoding fails: `retrieval_degraded = True`, a `DegradedBackendInfo(backend="query_embedding",
   error_category=<safe category>)` entry is added, and `_embedding_failed = True`.
3. The Qdrant/vector future is **skipped** when `_embedding_failed` (no submission to the pool).
4. BM25, metadata, and translated-text futures run normally — they do not need the query vector.
5. Reranking still runs on surviving lexical candidates if a reranker is configured.
6. Raw exception text is never stored; only the safe category string (`timeout`,
   `connection_error`, `unexpected_error`) appears in `DegradedBackendInfo.error_category`.

### DegradedBackendInfo backend values

| Value | Meaning |
|---|---|
| `vector` | Qdrant future failed (vector DB unreachable) |
| `bm25` | Meilisearch BM25 future failed |
| `metadata` | Meilisearch metadata-search future failed |
| `translated` | Meilisearch translated-text future failed |
| `query_embedding` | `encoder.encode()` raised before any backend was called |

### Tests

```bash
pytest tests/unit/test_rag_trace.py -q -k embedding_failure
```
