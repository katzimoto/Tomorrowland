# Rollout Evaluation Report: #715 Hierarchy Expansion & Coarse-to-Fine Routing

Issue: #787
Date: 2026-06-15
Status: Complete — results recorded, decision documented.

## Configurations evaluated

| # | Name | `hierarchy_expansion` | `coarse_to_fine_routing` |
|---|------|-----------------------|--------------------------|
| 1 | baseline | false | false |
| 2 | hierarchy | true | false |
| 3 | coarse2fine | false | true |
| 4 | combined | true | true |

## Evaluation harness

The existing `tests/eval/` offline retrieval evaluation harness was used. It
runs 31 parameterised eval cases across 11 categories: simple_factual,
citation_required, no_answer, hebrew_english_translation, permission_boundary,
multi_document, follow_up, table_heavy, layout_aware, preview_anchor,
translation_anchor, malicious, metadata_poisoning, translation_leak,
revoked_access.

5 dedicated hierarchy-expansion cases (he-001 through he-005) carry the
`expansion` tag and are counted in the `expansion_coverage` metric.

Two new scripts were created:
- `scripts/run-rollout-eval.sh` — orchestrates all 4 eval runs
- `scripts/compare-eval-runs.py` — compares JSON result files across configs

## Results

### Aggregate metrics (identical across all 4 configurations)

| Metric | Value |
|--------|-------|
| Total cases | 31 |
| Passed | 30 (96.77%) |
| Unauthorized leakage | 0 |
| Expansion eligible | 5 |
| Expansion applied | 0 |

### Per-case failures

Only `th-003` failed across all configurations:
- **th-003**: XLSX sheet-anchor case — `expected_sheet_name='Summary'` not found
  in citations. This is a corpus-dependent failure (no spreadsheet with a
  "Summary" sheet exists in this dev corpus). Not a regression.

### Why expansion_applied = 0

Analysis of the corpus state revealed:

1. **No `layout_blocks` table** — The database schema has not been migrated to
   include this table, which is a prerequisite for hierarchy expansion.
2. **Chunks in Qdrant lack layout metadata** — The `tomorrowland_chunks_384`
   collection stores chunks without `section_heading`, `layout_block_id`, or
   `page_number` payload fields. These were indexed before Docling/layout-aware
   extraction was introduced.
3. **`resolve_chunk_layout_block_ids()` has not been run** — No backfill or
   reindex has populated the layout-referencing payload fields.

Because the corpus has no layout-derived data, both `expand_chunks()` and
`_fine_retrieve()` fall through to their disabled/no-op paths, producing results
identical to baseline. The trace version remains `2` (no `context_packing`
trace v3 data).

### What was verified

- ✅ Both feature flags gate correctly — no errors or exceptions when enabled
- ✅ No regression in pass/fail metrics — identical results across all configs
- ✅ Zero unauthorized leakage — permission boundaries intact
- ✅ All 31 eval cases complete without errors in all configs
- ✅ The eval harness correctly captures `expansion_applied` and
  `expansion_eligible` per case
- ✅ The comparison infrastructure (`run-rollout-eval.sh` + `compare-eval-runs.py`)
  works end-to-end

## Rollout decision

**Keep both flags default-off (`False`).**

Rationale:

1. No corpus with layout blocks exists in this deployment to evaluate against.
   Enabling the flags would change code paths without any measurable impact.
2. #714 (Quality Lab) admin dashboard is the prerequisite for storing,
   comparing, and trending eval runs across configurations. It was merged
   [today](https://github.com/katzimoto/Tomorrowland/commit/7a5a709)
   but needs a populated corpus and schema migration to be useful.
3. A proper evaluation requires:
   - A Postgres migration creating the `layout_blocks` table
   - Docling-enabled document extraction producing layout blocks
   - `resolve_chunk_layout_block_ids()` backfill on existing chunks
   - Reindex of documents to populate `section_heading` and `layout_block_id`
     in Qdrant payloads
4. Until these prerequisites are met, the feature flags should remain
   admin-configurable but default-off. The existing defaults (`False`) stay.

## Recommended follow-up (post-corpus)

1. Apply the layout-blocks migration to the target deployment.
2. Index at least 20-30 documents with Docling (layout-aware) extraction.
3. Run `resolve_chunk_layout_block_ids()` to backfill Qdrant payloads.
4. Rerun all 4 eval configurations via `scripts/run-rollout-eval.sh`.
5. Compare metrics via `scripts/compare-eval-runs.py`.
6. Inspect `expansion_coverage`, `recall@k`, `citation_accuracy` deltas.
7. Decide: promote either flag to default-on or keep admin-configurable.

## Files created

- `scripts/run-rollout-eval.sh` — Orchestrates 4-config rollout eval
- `scripts/compare-eval-runs.py` — Compares JSON result files
- `eval-results/results-baseline.json` — Baseline eval results
- `eval-results/results-hierarchy.json` — Hierarchy-expansion eval results
- `eval-results/results-coarse2fine.json` — Coarse-to-fine eval results
- `eval-results/results-combined.json` — Combined eval results
