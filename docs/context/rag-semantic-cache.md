# Semantic RAG Cache

> **Feature flag**: `RAG_SEMANTIC_CACHE_ENABLED` (default `false`)
> **Introduced**: v0.6.x

## Overview

The semantic cache intercepts incoming chat questions before the full RAG
pipeline runs.  If a semantically similar question was answered recently, the
cached answer is returned immediately — eliminating retrieval, reranking, and
LLM generation latency entirely.

**Expected savings**: 30–50% reduction in LLM API/token costs for deployments
with repeated or similar queries (common in enterprise document Q&A).

## How it works

```
User question
  │
  ├─ 1. Embed question via TextEncoder
  ├─ 2. Search `rag_cache` Qdrant collection (cosine similarity)
  ├─ 3a. HIT (score ≥ 0.90)
  │       → Check TTL (default 24 h)
  │       → Check embedding model tag matches
  │       → Return cached AnswerResponse
  │
  └─ 3b. MISS
          → Run full retrieval → rerank → generate pipeline
          → Store question + answer in `rag_cache` collection
          → Return fresh AnswerResponse
```

Only the non-streaming `RagService.answer()` path benefits from the cache.
The streaming `answer_stream()` path is not cached (streaming responses are
inherently real-time and serialising them defeats the purpose).

## Configuration

All settings are in the `.env` file / `Settings` class:

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_SEMANTIC_CACHE_ENABLED` | `false` | Master on/off switch |
| `RAG_SEMANTIC_CACHE_SIMILARITY_THRESHOLD` | `0.90` | Cosine-similarity threshold (0.0–1.0). Higher = stricter matching, fewer hits. 0.95 recommended for compliance/high-precision domains |
| `RAG_SEMANTIC_CACHE_TTL_SECONDS` | `86400` | Cache entry lifetime in seconds (24 h). Entries older than this are silently dropped on read |
| `RAG_SEMANTIC_CACHE_COLLECTION` | `rag_cache` | Qdrant collection name for cache entries |

### Recommended thresholds by use case

| Use case | Threshold | Rationale |
|----------|-----------|-----------|
| Legal / compliance | 0.95 | Minimise risk of serving "close-but-wrong" answers |
| Technical documentation | 0.90 | Balance hit rate with precision |
| General enterprise Q&A | 0.85 | Higher hit rate for FAQ-style queries |
| Internal dev/staging | 0.80 | Maximise cost savings during development |

## Architecture

### Collection schema

The `rag_cache` Qdrant collection stores one point per cached query-answer pair:

| Field | Type | Purpose |
|-------|------|---------|
| `id` | uint64 | SHA-256 hash of question text (stable across restarts) |
| `vector` | float[] | Embedding of the original question |
| `payload.question` | string | Original question text |
| `payload.answer` | string | Generated answer |
| `payload.model` | string | LLM model used for generation |
| `payload.citations_json` | string | JSON-serialised citation list |
| `payload.trace_json` | string | JSON-serialised retrieval trace |
| `payload.embedding_model_tag` | string | `{model_name}:{dimension}` — used to invalidate on model changes |
| `payload.cached_at_ts` | float | Unix timestamp for TTL enforcement |

### Why Qdrant-native (not GPTCache or LangChain)

We evaluated existing semantic cache libraries:

- **GPTCache** (zilliztech): Deprecated/stagnant — upstream no longer adds support
  for new models or API shapes.  Not recommended for production.
- **LangChain Semantic Cache**: Actively maintained but adds a framework dependency
  that Tomorrowland does not otherwise use.  The Qdrant-native approach achieves
  the same result with zero additional dependencies.
- **Qdrant-native (our approach)**: Uses the Qdrant client already in the stack.
  Full control over TTL, similarity threshold, model-versioning, and eviction
  policy.  No new dependencies.

### Design decisions

| Decision | Rationale |
|----------|-----------|
| **Response-level caching** | Caching the full `AnswerResponse` (answer + citations + trace) gives the highest latency savings. Retrieval-level caching would still require LLM generation |
| **TTL-based invalidation** | Simplest mechanism that handles the primary failure mode (stale answers). Event-driven eviction (purge on document update) is a future enhancement |
| **Model-version tagging** | Embedding vectors from different models are not comparable. The `embedding_model_tag` ensures a model upgrade silently invalidates all cached entries |
| **SHA-256 point IDs** | Python's `hash()` is randomised per process. SHA-256 digests are stable across restarts, preventing duplicate cache entries |
| **Error responses not cached** | When LLM generation fails and falls back to "I encountered an issue…", that text is never stored in the cache |
| **Degraded-only** | Cache failures (Qdrant unreachable, embedding error) silently fall through to the normal pipeline. The cache is purely an optimisation |

## Operations

### Enabling the cache

```bash
# .env
RAG_SEMANTIC_CACHE_ENABLED=true
```

The cache collection is auto-created on first use.  No manual Qdrant setup is
required.

### Monitoring

Cache hits are tracked via the existing `rag_requests_total` Prometheus counter
with label `cache_hit`:

```promql
# Cache hit rate
rate(rag_requests_total{label="cache_hit"}[5m])
/
rate(rag_requests_total[5m])
```

### Clearing the cache

Two scenarios require clearing the cache:

1. **Embedding model upgrade**: The `embedding_model_tag` check automatically
   invalidates old entries.  No manual action needed.

2. **Emergency purge** (e.g., a hallucinated answer was cached): Delete the
   Qdrant collection:

   ```bash
   curl -X DELETE "http://qdrant:6333/collections/rag_cache"
   ```

   The collection will be recreated on the next chat request.

3. **Document re-indexing**: The cache may serve answers based on old document
   state.  Decrease TTL before a re-index, or purge the collection after.

### Scaling

- Each cache entry is one Qdrant point with one 4096-dim vector and ~2 KB of
  JSON payload.
- At 1000 entries/day with 24 h TTL: ~24,000 points, ~50 MB.
- No additional Redis or external cache store is needed.

## Testing

The cache is disabled by default in all environments.  Unit tests do not depend
on the cache — the `SemanticCache` parameter on `RagService` defaults to `None`.

Integration tests will be added when the feature graduates from opt-in to
default-enabled.

## Future enhancements

- **Event-driven eviction**: Purge cache entries when a scoped document is
  re-indexed.  Requires a document-update event bus.
- **Per-scope isolation**: Cache entries could be scoped to `group_ids` to
  prevent cross-tenant cache hits.
- **Cache warming**: Pre-populate the cache with common questions during
  deployment.
- **Analytics**: Track cache hit rate, average TTL of served entries, and
  false-positive rate (cached answer ≠ fresh answer).
