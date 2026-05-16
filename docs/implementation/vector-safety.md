# Vector Safety Integration Plan

Feature track: `feature/vector-safety`  
Related issues: #184, #185, #186, #198, #237

## Merge order inside `feature/vector-safety`

1. **#184 / PR #197** ✅ — Dimension-based Qdrant collection isolation and vector safety.
   *Adds:* dimension property on encoder, Qdrant collection naming by dimension, dimension validation
   before upsert/search, `EMBEDDING_DIMENSION` setting.
2. **#185 / PR #198** ✅ — Regression tests preventing mock embeddings in production.
   *Adds:* tests proving production code uses `build_encoder(settings)`, deterministic/test encoder
   construction limited to factory/test paths.
3. **#186 / PR #252** ✅ — Embedding model packaging and reindex procedure (operator-facing docs).
   *Adds:* air-gapped packaging/loading, OLLAMA_MODEL vs EMBEDDING_MODEL docs, reindex guide.
4. **#237 (this issue)** — Integration plan and docs (this PR).

## Interaction between #184 and #185

- #185 tests assert the factory/encoder contract that #184 introduces (`dimension` property,
  `build_encoder(settings)`). They are the safety net proving production does not accidentally use
  test-only encoders or wrong-dimension vectors.
- Both must pass before final merge to `main`.

## Whether #186 must land before final merge to `main`

**Yes — and it already has (PR #252).** Without #186, operators have no documented path to deploy
a real embedding model or reindex after a provider/dimension change. #186 is merged into
`feature/vector-safety`; the feature branch satisfies this requirement.

## Qdrant collection naming/versioning strategy

- Collection name format: `tomorrowland_chunks_{dimension}` (e.g. `tomorrowland_chunks_768` for
  768-dim vectors; prefix constant `COLLECTION_NAME_PREFIX` in `src/services/search/qdrant.py`).
- When the embedding dimension changes, a new collection is created automatically by
  `QdrantSearchClient` on first use via `create_collection_if_not_exists()`.
- Old collections are not deleted automatically; operators must run the reindex procedure to
  populate the new collection and can remove the old one manually after verification.

## Embedding dimension source of truth

- Single source of truth: `EMBEDDING_DIMENSION` environment variable (or `.env`), read by
  `shared.config.Settings.embedding_dimension` (default: 768).
- Encoder classes expose an instance-level `dimension` property that must match the configured
  `EMBEDDING_DIMENSION`.
- `build_encoder(settings)` in `src/services/search/factory.py` is the only production entry
  point. Test code must never call `build_encoder` with production settings.

## Model-change/reindex behavior

1. Update `EMBEDDING_MODEL` (and `EMBEDDING_DIMENSION` if the new model uses a different dimension).
2. Restart the API container — `QdrantSearchClient` creates the new-dimension collection lazily.
3. Run `reindex` (documented in #186) to backfill the new collection.
4. Once verified, the old collection can be dropped.

## Expected degraded behavior if real embedding provider is unavailable

- Semantic search mode returns zero results (keyword/hybrid modes are unaffected).
- RAG/related-document features are degraded (no vector-based similarity).
- The UI shows a clear error or empty results for semantic search; keyword and hybrid search
  continue working via Elasticsearch fallback.
- Ingestion pipeline still indexes documents (text extraction, translation, keyword indexing
  succeed); vector indexing is skipped gracefully.

## Validation checklist before final `feature/vector-safety -> main` PR

- [x] #184 (PR #197) merged into `feature/vector-safety`.
- [x] #185 (PR #198) merged into `feature/vector-safety`.
- [x] #186 (PR #252) operator docs merged into `feature/vector-safety`.
- [ ] `pytest` suite passes (no regressions).
- [ ] `ruff check` and `ruff format` pass.
- [ ] `mypy src --strict` passes (pre-existing import-unsupported errors exempted).
- [ ] Manual semantic search smoke test with a real embedding provider (Ollama or API).
- [ ] Manual smoke test with embedding provider unavailable — confirm keyword/hybrid search works.
- [ ] `CHANGELOG.md` updated for the vector safety track.

## Docs checks for #186 (all satisfied by PR #252)

- [x] `OLLAMA_MODEL` vs `EMBEDDING_MODEL` distinction explained.
- [x] Air-gapped packaging and loading for embedding models documented.
- [x] Verifying embedding model availability (health check or CLI command).
- [x] Reindex procedure after model/provider/dimension change.
- [x] Warning that deterministic-test vectors must not be used in production.
- [x] Explanation of Qdrant collection isolation (how `tomorrowland_chunks_{dim}` works).
