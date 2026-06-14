# RAG hierarchy-aware context packing

Use this note when working on hierarchy expansion, coarse-to-fine retrieval, context packing traces, and #715 rollout.

## Current state

Implemented and merged through #715:

- PR #785 — hierarchy-aware context packing from layout blocks.
- PR #786 — coarse-to-fine section routing for RAG retrieval.
- #715 is closed as completed.
- #787 tracks controlled rollout and comparison of the dark flags.

Both behavior-changing flags ship disabled by default:

```text
feature_document_chat_hierarchy_expansion=false
feature_document_chat_coarse_to_fine_routing=false
```

Do not enable either by default without eval comparison and failed-case inspection.

## Main files

- `src/services/rag/context_packer.py` — `expand_chunks()` adds parent/sibling layout context.
- `src/services/rag/layout_hierarchy.py` — section map and layout-block neighborhood helpers.
- `src/services/rag/trace_models.py` — `ContextPackingTrace` and `RetrievalTrace.context_packing`.
- `src/services/rag/service.py` — feature-flag wiring, RAG answer/stream integration, and `_fine_retrieve()`.
- `src/services/documents/layout_block_repository.py` — layout-block lookup.
- `src/services/search/qdrant.py` — Qdrant payload read/write support for layout metadata.
- `src/shared/config.py` — runtime feature flags.

## Behavior

### Hierarchy expansion

`expand_chunks()` runs after retrieval/reranking/final-context selection and before `_assemble_context()`.

When enabled, it tries to resolve each retrieved chunk to layout blocks using:

1. `layout_block_id` when present;
2. fallback `(page_number, section_heading)` matching.

It can prepend:

- parent section headings;
- nearby sibling blocks before the anchor;
- nearby sibling blocks after the anchor.

The original chunk text remains in the context. The packer does not remove original chunks.

### Coarse-to-fine routing

When enabled, RAG first uses stage-one flat retrieval to identify up to `MAX_COARSE_PAIRS=5` unique `(document_id, section_heading)` pairs. It then runs a scoped Qdrant vector search restricted to those sections and merges the fine results with BM25/metadata/translated candidates using weighted RRF.

If fine retrieval returns no results, stage-one results are preserved.

## Safety invariants

Preserve these invariants in every follow-up:

- same-document-only expansion;
- no cross-document context insertion;
- no permission or ACL semantic changes;
- documents without layout metadata use flat fallback;
- traces must not contain raw unauthorized text, prompts, secrets, credentials, or internal paths;
- original chunks must remain available for citation grounding;
- default-off rollout until Quality Lab or equivalent eval artifacts show safe benefit.

## Trace fields

`RetrievalTrace.context_packing` is a `ContextPackingTrace` with:

- `expansion_applied`
- `expanded_chunk_ids`
- `parent_blocks_added`
- `sibling_blocks_added`
- `budget_words`
- `dropped_for_budget`
- `sections_matched`
- `sections_not_found`

These are safe diagnostic fields. Do not add raw expansion text to the trace.

## Tests to run

Use focused tests first, then broader RAG/search tests:

```bash
pytest tests/unit/test_rag_context_packer.py -q
pytest tests/unit/test_rag_layout_hierarchy.py -q
pytest tests/unit/test_rag_coarse_to_fine.py -q
pytest tests/unit/test_search_qdrant.py -q -k layout
pytest tests/unit/test_rag_trace.py -q
```

If test names drift, discover with:

```bash
rg --files tests | rg "rag|qdrant|layout|context"
rg "ContextPackingTrace|feature_document_chat_hierarchy|coarse_to_fine|layout_block_id" tests src
```

## Rollout sequence

Recommended sequence:

1. Baseline eval: both flags off.
2. Enable hierarchy expansion only.
3. Enable coarse-to-fine routing only.
4. Enable both flags together.
5. Compare recall@k, MRR, citation accuracy, no-answer correctness, leakage count, retrieval-degraded rate, per-stage latency, and context-packing trace coverage.
6. Inspect table-heavy, section-heavy, multi-block, translated-lane, no-layout fallback, and permission-boundary cases.
7. Record the decision in #787.

## Related issues

- #714 — Quality Lab; preferred surface for comparing retrieval configurations.
- #717 — Permission Simulator; should explain retrieval visibility without leaking inaccessible text.
- #787 — Controlled rollout experiment for #715 flags.
- #726/#727/#728 — translation quality and metadata work; relevant because translated lanes interact with RAG/evidence trust.
