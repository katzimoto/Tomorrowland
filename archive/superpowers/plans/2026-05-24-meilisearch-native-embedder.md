# Meilisearch Native Embedder — Eliminate Qdrant + Embed Worker

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current three-component vector pipeline (embed-worker → ollama-embed → Qdrant) with Meilisearch's built-in Ollama embedder. Meilisearch v1.9 can call `ollama-embed` directly during document indexing and serve hybrid (BM25 + vector) results in a single query — removing ~600 lines of bespoke embedding infrastructure and four Docker containers.

**Architecture before:**
```
index_worker  → Meilisearch (BM25 only)
embed_worker  → ollama-embed → Qdrant (vectors)
search.py     → Meilisearch result + Qdrant result → Python merge → response
```

**Architecture after:**
```
index_worker  → Meilisearch (BM25 + vectors — embedder calls ollama-embed internally)
search.py     → Meilisearch hybrid result → response
```

**Key facts:**
- Meilisearch v1.9 (already running) supports the `ollama` embedder source via `PUT /indexes/{uid}/settings/embedders`.
- Meilisearch calls `POST /api/embed` on `ollama-embed:11434` during indexing — no code change needed in the embed path.
- Hybrid queries send `hybrid: { embedder: "default", semanticRatio: 0.5 }` — Meilisearch vectorises the query itself; no Python encoder needed at search time.
- The `ollama-embed` container stays; it is just called by Meilisearch instead of by the Python embed worker.
- A new feature flag `FEATURE_MEILISEARCH_HYBRID` gates the hybrid path so existing deployments are not broken.

**Tech stack:** Python 3.13, FastAPI, Meilisearch v1.9, meilisearch-python SDK, Docker Compose, `uv run pytest`, `ruff`, `mypy --strict`.

**Feature branch:** `feature/meili-native-embedder` → `main` (final PR only). All sub-issue PRs target this branch.

---

## File map

### New files
| File | Purpose |
|---|---|
| `tests/unit/test_meili_embedder_settings.py` | Unit-test embedder config generation |
| `tests/unit/test_meili_hybrid_search.py` | Unit-test hybrid query builder |

### Modified files
| File | Change |
|---|---|
| `src/services/search/meili_settings.py` | Add `embedders` key to `INDEX_SETTINGS`; add `"vector"` ranking rule |
| `src/services/search/meili_provider.py` | Add `hybrid` param to `search()` and `search_rag()` when flag is on |
| `src/services/api/routers/search.py` | Remove Qdrant branch and Python merge when `FEATURE_MEILISEARCH_HYBRID` is on |
| `src/shared/config.py` | Add `feature_meilisearch_hybrid: bool`, `meili_semantic_ratio: float`, `meili_embedder_name: str` |
| `docker-compose.yml` | Gate embed-worker, vector-worker, qdrant on `FEATURE_MEILISEARCH_HYBRID=false`; add `MEILI_MASTER_KEY` embedder env |
| `.env.example` | Document new flags and `FEATURE_MEILISEARCH_HYBRID=true` |
| `CHANGELOG.md` | Feature entry |

### Deleted / deprecated (sub-issue E)
| File | Action |
|---|---|
| `src/services/pipeline/embed_worker.py` | Delete (Meilisearch owns embedding) |
| `src/services/pipeline/vector_worker.py` | Delete (Qdrant writes gone) |
| `src/services/search/qdrant.py` | Delete |
| `src/services/search/encoder.py` | Delete (only needed for Qdrant and standalone encode) |
| `src/services/search/factory.py` | Delete |

> **Note:** `src/services/chunking/splitter.py` stays — `index_worker.py` still uses it to split text before pushing to Meilisearch.

---

## Sub-issue A — Embedder config + index settings

### Context

Meilisearch embedder config is set via `PATCH /indexes/{uid}/settings` with an `embedders` key.  
`apply_index_settings()` in `meili_settings.py` is called on every startup — adding the embedder config there is the right place.

Embedder config for Ollama:
```json
{
  "embedders": {
    "default": {
      "source": "ollama",
      "url": "http://ollama-embed:11434/api/embed",
      "model": "nomic-embed-text",
      "dimensions": 768,
      "documentTemplate": "{{doc.title}} {{doc.content}}"
    }
  }
}
```

`documentTemplate` controls what text Meilisearch sends to Ollama. Use `title` + `content` — the same fields the index worker already populates.

### Tasks

- [ ] **Add config fields to `src/shared/config.py`**

```python
feature_meilisearch_hybrid: bool = False
meili_embedder_name: str = "default"
meili_semantic_ratio: float = 0.5
```

- [ ] **Add embedder settings to `src/services/search/meili_settings.py`**

Below `_RANKING_RULES`, add a helper:
```python
def _embedder_settings(
    embedder_url: str,
    model: str,
    dimensions: int,
    embedder_name: str,
) -> dict[str, Any]:
    """Return the embedders block for Meilisearch index settings."""
    return {
        embedder_name: {
            "source": "ollama",
            "url": embedder_url,
            "model": model,
            "dimensions": dimensions,
            "documentTemplate": "{{doc.title}} {{doc.content}}",
        }
    }
```

Update `apply_index_settings()` signature to accept optional embedder params:
```python
def apply_index_settings(
    client: Any,
    *,
    shadow: bool = False,
    embedding_url: str | None = None,
    embedding_model: str = "nomic-embed-text",
    embedding_dimension: int = 768,
    embedder_name: str = "default",
    hybrid: bool = False,
) -> None:
```

When `hybrid=True`, merge `{"embedders": _embedder_settings(...)}` into `INDEX_SETTINGS` before applying.  
Also append `"vector"` to `_RANKING_RULES` when `hybrid=True`.

- [ ] **Update callers of `apply_index_settings`** — pass `hybrid=settings.feature_meilisearch_hybrid` wherever the function is called (search provider init, backfill script, rollout script).

- [ ] **Write `tests/unit/test_meili_embedder_settings.py`**

Test that:
1. `hybrid=False` produces no `embedders` key and no `"vector"` ranking rule.
2. `hybrid=True` produces correct `embedders` block and `"vector"` is appended to ranking rules.

- [ ] **Commit** `feat(search): add Meilisearch embedder config behind FEATURE_MEILISEARCH_HYBRID`

---

## Sub-issue B — Hybrid search query

### Context

When `FEATURE_MEILISEARCH_HYBRID=true`, Meilisearch search requests need:
```json
{
  "q": "...",
  "hybrid": {
    "embedder": "default",
    "semanticRatio": 0.5
  }
}
```
Meilisearch vectorises the query and merges BM25 + vector scores internally. No Python encoder call at query time.

The `meilisearch-python` SDK exposes this via `index.search(q, {"hybrid": {...}})`.

### Tasks

- [ ] **Update `MeilisearchSearchProvider.search()` in `meili_provider.py`**

Add `hybrid_embedder: str | None = None` and `semantic_ratio: float = 0.5` parameters.  
When `hybrid_embedder` is set, add `"hybrid": {"embedder": hybrid_embedder, "semanticRatio": semantic_ratio}` to the search params dict.

- [ ] **Update `MeilisearchSearchProvider.search_rag()` the same way.**

- [ ] **Update callers in `search.py` and `rag/service.py`** to pass `hybrid_embedder=settings.meili_embedder_name` when `settings.feature_meilisearch_hybrid` is on.

- [ ] **Write `tests/unit/test_meili_hybrid_search.py`**

Mock the SDK client. Assert that:
1. When `hybrid_embedder` is None the `"hybrid"` key is absent.
2. When `hybrid_embedder="default"` and `semantic_ratio=0.7` the payload contains `{"hybrid": {"embedder": "default", "semanticRatio": 0.7}}`.

- [ ] **Commit** `feat(search): add hybrid query param to Meilisearch provider`

---

## Sub-issue C — Simplify search route

### Context

`src/services/api/routers/search.py` currently:
1. Calls Meilisearch for BM25 results.
2. Calls Qdrant for vector results.
3. Merges both lists in Python with `merge_results()`.

When `FEATURE_MEILISEARCH_HYBRID=true`, step 1 already returns hybrid results — steps 2 and 3 are redundant.

### Tasks

- [ ] **Gate the Qdrant branch in `search.py`**

Wrap the `vector_results` block in:
```python
if not settings.feature_meilisearch_hybrid:
    # Qdrant vector search (legacy path)
    vector_results = ...
```

When the flag is on, set `vector_results = []` immediately and skip the merge — use `bm25_results` directly as `merged`.

- [ ] **Gate the `build_encoder` import** so it is not imported when the hybrid path is active (avoid loading `encoder.py` / `factory.py` at startup when they will be deleted later).

Use a lazy import inside the `if not settings.feature_meilisearch_hybrid` block.

- [ ] **Manual smoke test** (Docker not required — unit test acceptable):

Assert that with `feature_meilisearch_hybrid=True`, the route does not instantiate `QdrantSearchClient` or call `build_encoder`.

- [ ] **Commit** `feat(search): skip Qdrant branch when FEATURE_MEILISEARCH_HYBRID is on`

---

## Sub-issue D — Docker Compose + env

### Tasks

- [ ] **Add `FEATURE_MEILISEARCH_HYBRID` to `.env.example`**

```
# Optional: enable Meilisearch hybrid (BM25 + vector) search.
# When true, Meilisearch calls ollama-embed directly during indexing.
# Eliminates embed-worker, vector-worker, and qdrant containers.
FEATURE_MEILISEARCH_HYBRID=false
```

- [ ] **Gate embed-worker, vector-worker, qdrant in `docker-compose.yml`**

Add profile `legacy-vector` to each:
```yaml
embed-worker:
  profiles: ["legacy-vector"]
  ...
vector-worker:
  profiles: ["legacy-vector"]
  ...
qdrant:
  profiles: ["legacy-vector"]
  ...
```

When `FEATURE_MEILISEARCH_HYBRID=true`, operators simply omit `--profile legacy-vector` and those three services are not started.

- [ ] **Expose `EMBEDDING_URL`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION` to the `meilisearch` service** in `docker-compose.yml` environment block so the Python API startup can pass them through to `apply_index_settings`.

- [ ] **Commit** `feat(infra): gate embed-worker/vector-worker/qdrant behind legacy-vector profile`

---

## Sub-issue E — Delete legacy embedding code (after E2E verification)

> **Prerequisite:** Sub-issues A–D are merged and `FEATURE_MEILISEARCH_HYBRID=true` has been verified end-to-end on a running stack.

### Files to delete
- `src/services/pipeline/embed_worker.py`
- `src/services/pipeline/vector_worker.py`
- `src/services/search/qdrant.py`
- `src/services/search/encoder.py`
- `src/services/search/factory.py`
- `src/services/search/meili_rollout.py` (Qdrant-specific backfill)
- Any `tests/` files exclusively testing deleted modules

### Tasks

- [ ] Delete the files above.
- [ ] Remove `qdrant-client` and any Qdrant-only deps from `pyproject.toml`.
- [ ] Remove `qdrant_url` and all embedding encoder settings from `src/shared/config.py`.
- [ ] Remove `qdrant` volume from `docker-compose.yml` volumes block.
- [ ] Run full test suite: `uv run pytest --tb=short -q` — must pass with no Qdrant/encoder references.
- [ ] **Commit** `feat(cleanup): remove Qdrant, embed-worker, and Python embedding encoder`

---

## Sub-issue F — Backfill + CHANGELOG

### Context

Existing indexed documents have no vectors in Meilisearch. After enabling the embedder, Meilisearch will embed new documents automatically. Existing documents need a one-time re-index.

### Tasks

- [ ] **Write `scripts/meili-reindex.py`**

Fetches all documents from Meilisearch in pages and re-POSTs them without `_vectors`. Meilisearch will call `ollama-embed` for each. Progress logged to stdout.

```python
# Pseudocode
client = meilisearch.Client(MEILI_URL, MEILI_MASTER_KEY)
index = client.index("documents")
offset = 0
while True:
    page = index.get_documents({"offset": offset, "limit": 500})
    if not page.results:
        break
    # Re-add triggers re-embedding
    index.add_documents(page.results)
    offset += len(page.results)
    print(f"Re-indexed {offset} documents")
```

- [ ] **Update `CHANGELOG.md`**

```md
## [Unreleased]
### Changed
- Vector search now served by Meilisearch's native Ollama embedder
  (`FEATURE_MEILISEARCH_HYBRID=true`). The separate embed-worker,
  vector-worker, and Qdrant container are no longer needed and are
  removed when the flag is enabled.
- `EMBEDDING_*` env vars now configure the Meilisearch embedder
  rather than a Python OllamaEmbeddingEncoder.
```

- [ ] **Commit** `feat(search): add meili-reindex script and changelog entry`

---

## Acceptance criteria

- [ ] `FEATURE_MEILISEARCH_HYBRID=true` brings up the stack without embed-worker, vector-worker, or qdrant containers.
- [ ] Keyword search returns results (BM25 unchanged).
- [ ] Semantic / hybrid search returns relevant results for a test query.
- [ ] RAG Q&A works end-to-end.
- [ ] `FEATURE_MEILISEARCH_HYBRID=false` (default) keeps the legacy stack fully operational — no regression.
- [ ] Full test suite passes with `uv run pytest --tb=short -q`.
- [ ] `ruff check src` and `mypy --strict src` pass clean.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Meilisearch embedder config is applied at every startup — re-applying to an index that already has vectors is safe (idempotent), but changing `documentTemplate` invalidates existing vectors | Pin `documentTemplate` to `"{{doc.title}} {{doc.content}}"` and never change it without a full reindex |
| `ollama-embed` must be healthy before Meilisearch indexes any document | `depends_on: ollama-embed: condition: service_healthy` already in compose for embed-worker; extend to meilisearch service |
| Hybrid `semanticRatio=0.5` may degrade BM25 precision for exact-match queries | Make ratio configurable via `MEILI_SEMANTIC_RATIO`; default 0.5; operators can tune down to 0.2 for more BM25 weight |
| Meilisearch `ollama` source uses `/api/embed` — confirmed available in Ollama v0.3.4+ | Our `ollama-embed.Dockerfile` pulls `ollama/ollama:latest` which is well past 0.3.4 |
