# AI Surfaces — Operator Reference

This document is the operator-facing reference for Tomorrowland's AI-friendly
document surfaces: what they are, how they are configured, how permissions
are enforced, how to run them air-gapped, and how to swap the embedding model.

It is the companion to `docs/operations/air-gapped-deployment.md` and
`docs/operations/pipeline-workers.md`, focused specifically on the surfaces
that expose model-derived content (search, summaries, entities, tags, RAG,
related documents, expertise).

Source-of-truth for runtime settings is `src/shared/config.py`
(class `Settings`, Pydantic Settings auto-loaded from `.env`). Where this
document references a flag, the env var is the upper-snake-case of the field
name.

---

## AI Surfaces Overview

Tomorrowland exposes the following AI-derived surfaces. Each one runs only when
its feature flag is enabled and its backing service is reachable.

| Surface              | Backing service(s)               | Feature flag                  | Status            |
|----------------------|----------------------------------|-------------------------------|-------------------|
| Hybrid search        | Qdrant + Meilisearch             | always on                     | Available         |
| Document summary     | Ollama (generation model)        | `feature_summarization`       | Available         |
| Entity extraction    | Ollama (generation model)        | `feature_entity_extraction`   | Available         |
| Auto-tags            | Ollama (generation model)        | `feature_auto_tagging`        | Available         |
| Key points           | Ollama / rule-based              | (new flag, in-progress B1)    | In progress (B1)  |
| Related documents    | Qdrant + payload signals         | `feature_related_docs`        | Available         |
| Expertise map        | Activity signals + Qdrant        | `feature_expertise_map`       | Available         |
| Q&A / RAG            | Qdrant + Ollama (generation)     | `feature_rag_qa`              | Available         |
| Intelligence projection (`GET /documents/{id}/intelligence`) | aggregates above | (depends on B1)               | Planned (B2)      |
| Vault export (`/vault/export`) | aggregates above             | (new flag)                    | Planned (E1, #399)|

Surfaces marked **In progress** or **Planned** are tracked in
`Issue #400 — AI-friendly document surfaces`. Do not assume those endpoints
exist in the running RC. Confirm against `CHANGELOG.md` and the live API.

---

## Admin runtime configuration (Admin → Configuration)

Feature flags, the default LLM model/prompts, and search tuning ship with
environment defaults (`.env` → `Settings`), but admins can override most of them
at runtime **without a restart** from **Admin → Configuration** (`/admin/config`).

- The page lists every registered key from `SYSTEM_CONFIG_DEFAULTS`
  (`src/shared/feature_flags.py`), grouped into Feature Flags, LLM Model &
  Prompts, Search & Retrieval, and Other.
- Each key shows whether it is a **Default** (env value, no override stored) or
  **Overridden** (an admin value is persisted in `system_config`).
- Saving a value upserts it into `system_config`; the in-process config cache
  (30 s TTL) is invalidated so the change applies within seconds. **Reset to
  defaults** restores every key to its registered default.
- Resolution order at request time: a stored `system_config` value wins;
  otherwise the env default on `Settings` applies. Keys never written keep using
  the env default (`load default value if needed`).

The two hierarchy-aware RAG flags ship dark but are now runtime-toggleable here
for controlled rollout (still default `false`):

| Config key                                    | Env var                                          | Default |
|-----------------------------------------------|--------------------------------------------------|---------|
| `feature.document_chat_hierarchy_expansion`   | `FEATURE_DOCUMENT_CHAT_HIERARCHY_EXPANSION`      | `false` |
| `feature.document_chat_coarse_to_fine_routing`| `FEATURE_DOCUMENT_CHAT_COARSE_TO_FINE_ROUTING`   | `false` |

**LLM model selection.** Per-task model/provider routing (chat, utility,
reranking, embedding, …) lives in **Admin → Model Providers**: register a
provider, discover/declare model descriptors, set per-task defaults, then
**Reload** to apply without a restart. The `llm.model` config key is a simple
default-name fallback for deployments that do not use the provider registry.
Startup/infrastructure-only flags (Meilisearch index topology, extraction
binaries such as OCR/Docling, preview rendering) remain env-only because they
are read at service/worker boot, not per request.

---

## RAG Configuration

RAG (`POST /qa`) retrieves chunks from Qdrant, assembles a bounded context,
and asks Ollama for an answer. Configuration today is split between
`shared/config.py` and constants inside `src/services/rag/service.py`. Some
keys are being lifted to config in slice **A1** of #400.

| Setting                 | Env var                  | Default              | Status            | Purpose |
|-------------------------|--------------------------|----------------------|-------------------|---------|
| `feature_rag_qa`        | `FEATURE_RAG_QA`         | `true`               | Available         | Master toggle for the `/qa` endpoint. |
| `rag_max_chunks`        | `RAG_MAX_CHUNKS`         | (planned, default 5) | In progress (A1)  | Hard cap on retrieved chunks (`top_k`). Today fixed in code (default `top_k=5` in `RagService.answer`). |
| `rag_max_tokens_context`| `RAG_MAX_TOKENS_CONTEXT` | (planned)            | In progress (A1)  | Cap on assembled context. Today enforced as a word cap (`_MAX_CONTEXT_WORDS = 2_000` in `rag/service.py`); A1 lifts this to a configurable token bound. |
| `rag_score_threshold`   | `RAG_SCORE_THRESHOLD`    | (planned)            | In progress (A1)  | Minimum vector-similarity score for a chunk to be included. Today no floor is applied; A1 adds the gate. |

Until A1 merges, only `FEATURE_RAG_QA` is operator-tunable; the other RAG
limits live in code. Treat A1-flagged keys as **not present** in `.env` for
the current RC. After A1 lands, document the merged keys here and update the
`.env.example` and `.env.airgap.example` templates in the same PR.

**Required dependencies for RAG:**

- Qdrant reachable at `QDRANT_URL`.
- Ollama reachable at `OLLAMA_URL` with `OLLAMA_MODEL` loaded.
- An embedding model reachable through `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL`.
- At least one document indexed in the active Qdrant collection.

If any of those dependencies is missing, `/qa` returns a "no relevant
information found" answer with zero citations rather than 500-ing.

---

## Document Intelligence Lifecycle

`IntelligenceWorker` (`src/services/intelligence/worker.py`) runs best-effort
LLM tasks after a document is indexed. The pipeline currently runs:

1. `summarize` — Ollama summary, stored on the document. Cap: `MAX_SUMMARIZE_CHARS = 8000`.
2. `extract_entities` — Ollama JSON output, parsed into person /
   organization / location rows linked to the document. Cap:
   `MAX_ENTITY_CHARS = 6000`.
3. `auto_tag` — Ollama tag list, written back to the document. Cap:
   `MAX_TAG_CHARS = 4000`.
4. `extract_key_points` — planned; B1 adds a rule-based extractor first with
   an optional LLM layer, plus a new `document_key_points` table.

Tasks run in the order above. A failure on one task is logged and stops
further tasks for that document, but does **not** fail ingestion: the
document is still searchable. See `docs/operations/pipeline-workers.md` for
the Ollama-unavailable behaviour.

**Feature flags** (all default `true`):

| Setting                       | Env var                          | Effect when `false`                                  |
|-------------------------------|----------------------------------|------------------------------------------------------|
| `feature_summarization`       | `FEATURE_SUMMARIZATION`          | Skip summary task.                                   |
| `feature_entity_extraction`   | `FEATURE_ENTITY_EXTRACTION`      | Skip entity extraction.                              |
| `feature_auto_tagging`        | `FEATURE_AUTO_TAGGING`           | Skip auto-tag task.                                  |
| (key-points flag, in-progress)| (planned)                        | Skip key-points (B1).                                |

Intelligence is **not** retroactively backfilled when a flag flips from
`false` to `true`. Re-running enrichment for already-indexed documents
requires a re-ingest or a future enrichment job.

`auto_enrich_threshold` (default `5`) is the minimum word count below which a
document is skipped for enrichment.

---

## Related Documents & Expertise

`RelatedService` (`src/services/related/service.py`) powers two surfaces:

- **Related documents** — embeds the source document, queries Qdrant filtered
  by the caller's group memberships, dedupes, and returns metadata.
- **Expertise map** — aggregates view / comment / annotation / subscription
  signals into per-user expertise scores.
  Weights: `view=3.0, comment=2.0, annotation=2.0, subscription=1.0`.

| Setting                   | Env var                       | Default | Purpose                                |
|---------------------------|-------------------------------|---------|----------------------------------------|
| `feature_related_docs`    | `FEATURE_RELATED_DOCS`        | `true`  | Toggle for related-documents surface.  |
| `feature_expertise_map`   | `FEATURE_EXPERTISE_MAP`       | `true`  | Toggle for expertise surface.          |
| `feature_subscriptions`   | `FEATURE_SUBSCRIPTIONS`       | `true`  | Subscription signal feeds expertise.   |
| `feature_annotations`     | `FEATURE_ANNOTATIONS`         | `true`  | Annotation signal feeds expertise.     |

Permission expectations:

- Both surfaces call `QdrantSearchClient.search(group_ids=...)`, which adds a
  group filter to every Qdrant query.
- Admins receive an `allow_all` bypass only when the calling route opts in.
- Related-documents currently re-extracts the source document from disk to
  build its query vector. Slice **C1** of #400 replaces that with a payload
  cache (`document_payloads.payload_text`) and adds a tag/entity overlap
  signal — until then, related-documents has a hard dependency on the
  original file being present at the recorded `document.path`.
- Slice **C2** adds per-signal explanations to expertise results; until it
  lands, the response carries aggregate counts but not per-document evidence.

---

## Permissions Model

Tomorrowland's AI surfaces share the same authorization primitives as the
rest of the API. The relevant code lives in
`src/services/permissions/enforcer.py`.

| Primitive                          | Behaviour                                                            |
|------------------------------------|----------------------------------------------------------------------|
| `require_admin(user)`              | 403 unless `user.is_admin`. Used for admin-only routes.              |
| `get_allowed_groups(user)`         | Returns the caller's group UUIDs; passed to Qdrant / search.         |
| `assert_source_access(source, …)`  | 403 unless the user has a grant on the source. Admin bypasses.       |
| `assert_doc_access(document, …)`   | 403 unless the document's source is accessible to the user.          |

**Group filtering.** Vector and lexical search both apply a group filter
derived from the JWT (`user.groups`). A user who is not in a group with a
grant on the document's source cannot retrieve that document via search,
related docs, RAG, or expertise.

**Admin bypass.** `is_admin=True` bypasses source-grant checks at the
permission layer. Whether a given route exposes that bypass is controlled at
the route level (the `allow_all` flag on `QdrantSearchClient.search` and
`RagService.answer`). Treat admin bypass as a deliberate operator capability,
not a debugging shortcut — it makes cross-group content reachable.

**Audit posture.** Slice **D1** (issue #142) is producing a read-only
permission matrix of every document-derived surface. D2 will apply any fixes
the audit surfaces. Until D1/D2 land, assume:

- Any route that does not call `assert_doc_access` or pass `group_ids` into
  Qdrant is a candidate finding.
- Cross-group leakage tests are not yet exhaustive.

If you discover a surface that returns a document the caller could not
otherwise reach via `/documents/{id}`, file it against #142.

---

## Air-Gapped / Offline Setup

The AI surfaces work fully offline as long as the local model bundle is loaded
and the dependent services are reachable inside the Compose network.

Use `docs/operations/air-gapped-deployment.md` as the primary reference for
the install / load-images / start flow. The notes below cover only what is
specific to the AI surfaces.

### Required services (air-gapped)

| Service           | Compose host       | Used by                              |
|-------------------|--------------------|--------------------------------------|
| `qdrant`          | `qdrant:6333`      | search, RAG, related docs            |
| `meilisearch`     | `meilisearch:7700` | keyword/BM25 search, typo-tolerant   |
| `ollama`          | `ollama:11434`     | summary, entities, tags, RAG, embeddings (if `EMBEDDING_PROVIDER=ollama`) |
| `libretranslate`  | `libretranslate:5000` | translation enrichment (not strictly AI but required for non-English indexing) |

### Loading models

Load the Ollama model bundle before relying on RAG / summaries / entities /
tags. The bundle ships generation and embedding models together:

```bash
bash scripts/tomorrowland-airgap.sh load-ollama \
  /path/to/tomorrowland-ollama-bundle-qwen3-4b-<version>.tar.gz
```

Then validate that both models resolved inside Ollama:

```bash
OLLAMA_URL=http://localhost:11434 OLLAMA_MODEL=qwen3:4b \
  bash scripts/validate-ollama-model.sh

curl -s http://localhost:11434/api/tags | grep -q "$EMBEDDING_MODEL" \
  && echo "embedding model present" \
  || echo "embedding model missing"
```

### Degraded behaviour without models

- **Ollama generation model missing:** summary / entities / tags / RAG return
  empty or "no answer" responses. Ingestion succeeds; full-text and vector
  search still work.
- **Embedding model missing:** Qdrant indexing is skipped gracefully on
  ingest; semantic search returns zero results; Meilisearch (BM25)
  search continues to work; RAG retrieval is effectively disabled.
- **Qdrant unreachable:** RAG returns "no relevant information"; related
  documents returns an empty list; Meilisearch (BM25) search continues.

None of these states should fail login, document upload, preview, or
download — those paths do not depend on AI services.

---

## Embedding Model Swap

Changing the embedding model is an operator-visible event because it changes
the Qdrant collection name. Each `(provider, model, dimension)` choice maps
to a separate Qdrant collection so vectors from different models never mix.

### Where the collection name comes from

`src/services/search/qdrant.py` constructs the collection name as:

```python
COLLECTION_NAME_PREFIX = "tomorrowland_chunks"
collection_name = f"{COLLECTION_NAME_PREFIX}_{dimension}"
```

So `EMBEDDING_DIMENSION=768` ⇒ `tomorrowland_chunks_768`, and switching to
`EMBEDDING_DIMENSION=1024` creates `tomorrowland_chunks_1024` on first
upsert. The old collection is preserved on disk and can be deleted manually
once you no longer want to roll back.

### Swap procedure

1. **Confirm the new model is loaded into Ollama** (or reachable through
   whatever `EMBEDDING_PROVIDER` you use). The model bundle must ship both
   the generation model and the embedding model.
2. **Update `.env`:**

   ```env
   EMBEDDING_PROVIDER=ollama
   EMBEDDING_MODEL=<new-model>
   EMBEDDING_DIMENSION=<dimension-of-new-model>
   ```

3. **Restart the stack** so the new dimension is read at startup:

   ```bash
   docker compose down
   docker compose up -d
   ```

   (Do **not** add `-v`; that would delete persistent volumes.)

4. **Reindex existing documents.** New ingests populate the new collection
   automatically. Pre-existing documents remain only in the old collection
   until you re-trigger ingestion (`POST /admin/ingestion/{source_id}/sync-now`
   per source).
5. **Verify both surfaces:**
   - Semantic search returns results.
   - `/qa` returns answers with citations.
6. **Optionally drop the old collection** once you are confident the new
   model is good.

### Test-mode embeddings

`EMBEDDING_PROVIDER=deterministic-test` exists for CI and local development
only. The flag
`embedding_provider_unsafe_allow_test_in_prod` (`EMBEDDING_PROVIDER_UNSAFE_ALLOW_TEST_IN_PROD`)
gates production use; leave it `false` in any real deployment. Deterministic
test vectors silently degrade search and RAG quality.

---

## RAG Tuning Reference

Today's RAG tuning surface is narrow; A1 expands it. Use this table when
diagnosing answer quality or relevance complaints.

| Knob                     | Today                                          | After A1                                   | When to change |
|--------------------------|------------------------------------------------|--------------------------------------------|----------------|
| Number of chunks (`top_k`) | Fixed at 5 (`RagService.answer` default).    | `rag_max_chunks`                            | Bump up for long documents or sparse hits; down for noisy answers. |
| Context budget           | Hard cap of 2 000 words (`_MAX_CONTEXT_WORDS`). | `rag_max_tokens_context` (token-bounded). | Lower if the generation model is truncating; raise only if the model context window allows. |
| Score floor              | None; every retrieved chunk is included.       | `rag_score_threshold`                       | Raise to suppress weak matches that drag the answer off-topic. |
| Chunking                 | Current chunker is window-based.               | Sentence-boundary chunker (A5).            | Re-chunk after A5 ships; expect better citations. |
| Reranking                | None; pure cosine order.                       | `NoOpReranker` (A3 default) or a pluggable reranker. | Plug in once a reranker is approved. |
| Hybrid retrieval         | Vector-only via Qdrant.                        | RRF fusion of vector + BM25 / Meilisearch (A2). | Helpful when lexical recall is poor (acronyms, codes). |

Diagnostic checklist when RAG quality regresses:

1. Confirm the embedding model and generation model are both loaded.
2. Confirm the active Qdrant collection name matches `EMBEDDING_DIMENSION`.
3. Confirm the user has group access to the documents they expect to see.
4. Check `tomorrowland_job_queue_depth` and DLQ depth — uningested docs
   never appear in RAG.
5. Compare the failing question against `/search?q=…`: if lexical search
   finds the right doc but RAG does not, the issue is vector recall, not
   permissions.

---

## Search Backend Roles

Tomorrowland uses up to three search backends. Each plays a distinct role
and they are not interchangeable.

| Backend         | Role                              | Required?                  | Notes                                                       |
|-----------------|-----------------------------------|----------------------------|-------------------------------------------------------------|
| **Qdrant**      | Vector / semantic search          | Yes for semantic + RAG     | Collection per embedding dimension. Soft-failure on ingest. |
| **Meilisearch** | Keyword / BM25 search             | Yes — primary BM25 index    | Gated by `feature_meilisearch_search`. Canonical BM25 backend. |

Default merge behaviour (hybrid `/search`) is RRF fusion via
`search/hybrid.py::merge_results()`. The same fusion will be wired into
`/qa` in slice A2.

---

## Staged Work — Issue #400

This is the parallel-execution view of #400 so operators know which surfaces
to expect to change over the next round of merges. **Do not assume any
non-Group-0 item is in the running RC.**

### Group 0 — in progress

| Slice | Branch                       | Owner area               | Operator-visible change                                       |
|-------|------------------------------|--------------------------|---------------------------------------------------------------|
| A1    | `feat/rag-config-wiring`     | `shared/config.py`, RAG  | New env keys `RAG_MAX_CHUNKS`, `RAG_MAX_TOKENS_CONTEXT`, `RAG_SCORE_THRESHOLD`. |
| B1    | `feat/key-points`            | intelligence worker      | New `document_key_points` table + migration; new feature flag. |
| C1    | `feat/related-multisignal`   | related service          | Related docs no longer requires the file on disk; tag/entity overlap added. |
| C2    | `feat/expertise-evidence`    | related service          | Expertise responses carry per-signal explanations.            |
| D1    | `feat/acl-audit`             | docs only                | Permission matrix + D2 fix checklist (no runtime change yet). |
| F1    | `feat/operator-docs`         | docs only                | This document.                                                |

### Group 1+ — planned

| Group | Slice | Branch                       | Operator-visible change                                                                     |
|-------|-------|------------------------------|---------------------------------------------------------------------------------------------|
| 1     | A2    | `feat/rag-hybrid-retrieval`  | RAG fuses Qdrant vector + Meilisearch BM25 hybrid retrieval.                            |
| 1     | A5    | `feat/rag-chunking`          | Sentence-boundary chunker — reindex required for full benefit.                              |
| 1     | A6    | `feat/rag-eval-harness`      | Hit@k / MRR eval; CI signal only.                                                           |
| 1     | B2    | `feat/intelligence-projection` | `GET /documents/{id}/intelligence` aggregates summary / key_points / entities / tags.    |
| 1     | D2    | `feat/acl-hardening`         | Applies D1 audit fixes; cross-group leakage tests.                                          |
| 1     | E1    | `feat/vault-export`          | `services/vault/` package; group-scoped Markdown zip export (#399).                         |
| 2     | A3    | `feat/rag-reranker`          | Pluggable reranker (`NoOpReranker` default).                                                |
| 2     | E2    | `feat/vault-topics`          | Topic index + `[[wikilink]]` links in vault export.                                         |
| 3     | A4    | `feat/rag-prompt-quality`    | Citation dedup + word-bounded assembly tightening.                                          |

When any of these merges, update the matching row in **RAG Configuration**,
**Document Intelligence Lifecycle**, or **Permissions Model** above, plus
`CHANGELOG.md`. Do not move an item out of "planned" here until the PR is
merged to `main`.

---

## Researcher API — Audit Logging and Usage Limits (#561)

The permissioned researcher API (`/api/agent/v1/*`) and the Hermes MCP
adapter (`/mcp`) emit structured audit events and enforce per-user rate
limits.  Both behaviours are active by default and require no changes for
standard deployments.

### Audit events

Every successful call to the six researcher endpoints emits an `INFO`-level
structured log line.  Example:

```
agent_audit route=search_documents user=<uuid> correlation_id=<uuid> \
  query_length=12 result_count=5 latency_ms=42.3 status=ok
```

**What is logged**: route name, user id (UUID), correlation id, query or
question *length* (character count, not the raw text), result count, end-to-end
latency in milliseconds, and status (`ok` or `degraded`).

**What is never logged**: raw query text, raw question text, document content,
passage text, citation text, answer text, Authorization headers, JWTs, or
API keys.

Log lines appear under the logger `services.api.routers.agent`.  Route
MCP calls through REST; because every MCP tool forwards to a REST endpoint,
audit events are emitted on the REST side automatically — there is no
separate MCP-side audit log, and there are no duplicate events.

### Usage limits

| Setting                                     | Env var                                        | Default | Purpose                                         |
|---------------------------------------------|------------------------------------------------|---------|-------------------------------------------------|
| `agent_rate_limit_enabled`                  | `AGENT_RATE_LIMIT_ENABLED`                     | `true`  | Master toggle. Set `false` in dev/test only.    |
| `agent_rate_limit_window_seconds`           | `AGENT_RATE_LIMIT_WINDOW_SECONDS`              | `60`    | Sliding-window width in seconds.                |
| `agent_rate_limit_calls_per_window`         | `AGENT_RATE_LIMIT_CALLS_PER_WINDOW`            | `100`   | Max calls per user per window (non-ask_corpus). |
| `agent_rate_limit_ask_corpus_calls_per_window` | `AGENT_RATE_LIMIT_ASK_CORPUS_CALLS_PER_WINDOW` | `20` | Max `ask_corpus` calls per user per window.     |

**Counters are independent**: `ask_corpus` has its own bucket per user;
the general counter covers the other five endpoints.

**MCP**: because MCP tools forward to REST, they count against the same
per-user REST-side limits.  There is no separate MCP-side limit.

**Fail-closed**: if any limit value is invalid (≤ 0), the server refuses to
start.  An over-limit request receives `HTTP 429 Rate limit exceeded` with a
safe message and no internal detail.

**Over-limit troubleshooting**:
- Confirm `AGENT_RATE_LIMIT_CALLS_PER_WINDOW` / `AGENT_RATE_LIMIT_ASK_CORPUS_CALLS_PER_WINDOW` are set appropriately for your workload.
- Limits are in-memory per process; they reset on restart and do not
  synchronise across multiple API replicas.
- Normal user-facing search and RAG endpoints (`/search`, `/qa`, chat) are
  **not** affected by these limits.

---

## See Also

- `docs/operations/air-gapped-deployment.md` — install, load, validate.
- `docs/operations/air-gapped-upgrade.md` — upgrade flow and volume safety.
- `docs/operations/pipeline-workers.md` — ingestion, DLQ, degraded modes.
- `docs/operations/production-compose.md` — Compose service layout.
- `src/shared/config.py` — authoritative settings list.
- `src/services/rag/service.py` — RAG retrieval / assembly / generation.
- `src/services/intelligence/worker.py` — summary / entities / tags / key points.
- `src/services/related/service.py` — related docs / expertise.
- `src/services/search/qdrant.py` — Qdrant client, collection naming, group filter.
- `src/services/permissions/enforcer.py` — `require_admin`, `assert_doc_access`, `get_allowed_groups`.
