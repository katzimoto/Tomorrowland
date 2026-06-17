# Tomorrowland Current State

Canonical shared memory for active project state. Keep this file compact and factual.
<!-- Compaction cutoff: 2026-06-14. Older detailed entries intentionally compacted here; use git history for the prior long-form state log. -->

## 2026-06-14 — Current product baseline

Status: **v0.6 released**.

Tomorrowland is now best understood as an air-gapped, permission-aware document intelligence workspace with:

- high-fidelity document preview for mail, Office, PDF/image/text, and structured XLSX grids;
- parser/layout-aware document understanding with Docling/layout metadata foundations;
- hybrid retrieval with Meilisearch/BM25 + Qdrant/vector, weighted RRF, optional reranker, metadata/translated lanes, and safe degraded-backend traces;
- Evidence Inspector, citation feedback, source health visibility, and operator diagnostics;
- durable Evidence Packs with backend API, UI save flows, detail pages, and Markdown/JSON exports;
- hierarchy-aware RAG context packing and coarse-to-fine section routing implemented but disabled by default;
- RAG threat model and offline regression coverage for prompt-injection/ACL/metadata/translation leakage risks.

Latest release: **v0.6** (2026-06-15).
Open implementation PR count observed 2026-06-15: **0**.

---

## Completed release trackers / major epics

### v0.6 Evidence Packs and Review Workflow (#662) — done

Status: **Closed complete**.

Completed children:

- #676 / PR #780 — `evidence_packs` + `evidence_pack_items` schema, API, owner-scoped service layer, audit rows, JSON/Markdown export, and permission/audit integration tests.
- #679 — security/audit tests reconciled and closed.
- #677 / PR #781 — UI save flows from chat citation cards, Evidence Inspector, and search result rows. Shared `SaveToEvidencePackDialog`; supports create-new/add-existing; blocks duplicate passage saves; surfaces 403/404 clearly.
- #678 / PR #783 — Evidence Packs nav/list/detail UI, editable metadata, grouped items, original/translated excerpts, source-document links, item removal, and Markdown/JSON exports.

#681 remains open under #663/v0.7 because agent-created evidence packs depend on Hermes approval gates and advisory-run flows.

### #715 hierarchy-aware RAG context packing — done, ships dark

Status: **Closed complete**.

Merged work:

- PR #785 — hierarchy derivation + context packer core + trace rollout + precise layout-block linkage.
- PR #786 — optional coarse-to-fine section routing.

Runtime flags remain default-off:

```text
feature_document_chat_hierarchy_expansion=false
feature_document_chat_coarse_to_fine_routing=false
```

Important invariants:

- same-document-only expansion;
- no eviction of original chunks by the packer;
- flat fallback for documents without layout blocks or unresolved layout anchors;
- permission boundaries unchanged;
- traces store identifiers/counts/budgets only, not raw unauthorized text.

Follow-up tracker:

- #787 — controlled rollout experiment for hierarchy expansion and coarse-to-fine routing.

### High-fidelity preview (#539) — done

Status: **Closed complete**.

Delivered manifest/artifact-based preview pipeline:

- EML/MSG rendered as sanitized email manifests;
- DOCX/PPTX rendered through LibreOffice-to-PDF in preview-worker;
- XLSX rendered as per-sheet structured grids;
- PDF/image/text ready-immediate manifests;
- admin renderer diagnostics and rerender;
- orphan sweep helper.

Known follow-ups:

- #740 RTF-only MSG body HTML conversion — implemented via PR #782.
- #748 cross-sheet XLSX search counting — still open.

---

## 2026-06-15 — Admin Configuration UI + runtime-toggleable chat flags

Branch `claude/admin-ui-flags-llm-config-fr5eqd`.

- New **Admin → Configuration** page (`/admin/config`, `AdminConfigPage.tsx`)
  exposes the existing `/admin/config` registry: feature flags as toggles, LLM
  model/prompts as text, search/alerts tuning as numbers. Per-key save + reset.
  `adminApi.listConfig/updateConfig/resetConfig` added; route + hub card wired.
- `/admin/config` backend is now **defaults-aware**: `GET` merges
  `SYSTEM_CONFIG_DEFAULTS` with stored rows (adds `is_default`); `PUT` **upserts**
  (seeds default-only keys, still 404s for unknown keys); `reset` upserts. Values
  are JSON-decoded so the API returns typed bool/str/number (fixes prior `'true'`
  / `'"qwen3:4b"'` raw-text quirk noted in `config_cache.py`). No migration needed.
- Two previously settings-only dark RAG flags are now runtime-toggleable via the
  config registry (still default false): `feature.document_chat_hierarchy_expansion`,
  `feature.document_chat_coarse_to_fine_routing`. Added to `SYSTEM_CONFIG_DEFAULTS`
  + `ENV_FEATURE_TO_CONFIG_KEY`; new `resolve_feature_flag()` helper in `_helpers.py`
  resolves DB-override-then-env; wired at the 3 `RagService` build sites in
  `chat.py` (x2) and `agent.py`.
- **LLM generation model config** was already fully UI-driven via Admin → Model
  Providers (providers/descriptors/per-task defaults/discover/test/**reload**).
- **Model overrides (2nd slice — resolver-based).** Validation found embedding,
  search-path reranker, translation-QE, and translation-HQ-bundle were env-only.
  Design decision (after review): **endpoint-backed models go through the existing
  model-provider registry / `TaskDefaultResolver`, not a parallel system_config
  path.** `build_encoder`/`build_reranker` now take an optional `resolver=` and
  honor the `embedding`/`reranking` task defaults (activating the previously-dead
  `embedding` task type); fall back to env when no default. Wired at every
  encoder/reranker call site (search/chat/agent/documents/alerts pass
  `request.app.state.task_default_resolver`; workers build one via
  `task_defaults.build_task_resolver(engine, settings)`). Resolver is in-memory
  (no per-request DB); reload via existing `/admin/model-providers/reload` (API)
  or worker restart. Embedding change ⇒ re-embed (query+index must match);
  optional `parameters.dimension` on the task default sets vector size.
  **Local model bundles** (QE + HQ-translation CTranslate2/OPUS) are file paths,
  not endpoints, so they don't fit the registry → kept on `system_config`
  `model.translation_qe_model_path` / `model.translation_high_bundle_path`
  (empty sentinel = use env), read by enrich/slow workers via
  `shared/runtime_config.apply_model_config_overrides`. Config-page list marks
  stored==default as Default (sentinels show Default); "Translation Model Bundles"
  group on the config page. Tests: `test_search_factory.py` (resolver paths),
  `test_runtime_config.py`. Startup/infra flags (Meilisearch topology, OCR/Docling
  extraction, preview render) remain env-only by design.
- Tests: `tests/integration/test_admin.py` (default-only upsert),
  `tests/unit/test_feature_flag_resolution.py`, `AdminConfigPage.test.tsx`. Verified:
  ruff, mkdocs --strict, backend config/chat/agent suites, frontend admin tests (100), tsc, eslint.

## Active next work

### #714 Quality Lab — priority:next, status:ready

Recommended next major implementation.

Purpose: turn offline/nightly eval artifacts into an admin-facing dashboard for retrieval, parser, citation, permission, no-answer, degradation, and latency regressions.

Why now: #715 introduced dark retrieval/context-packing knobs. Quality Lab should compare flat retrieval vs hierarchy expansion vs coarse-to-fine vs combined mode before any default-on decision.

### #717 Permission Simulator — priority:next, status:ready

Recommended parallel/high-priority trust work.

Purpose: let admins simulate user/group/source/document/query access and explain allow/deny reasons without leaking inaccessible text.

Why now: Evidence Packs, exports, derived translations, and future Hermes workflows all rely on explainable permission safety.

### #787 Controlled #715 rollout experiment — DONE

Status: **Done — evaluation complete, both flags remain default-off**.

Results: `docs/agents/rollout-eval-787.md`. All 4 configurations (baseline,
hierarchy-only, coarse-to-fine-only, combined) produced identical metrics
(30/31 pass, 0 leakage). Hierarchy expansion never activated because the dev
corpus has no `layout_blocks` data — features require Docling-enabled indexing.

Decision: Keep both flags default-off until a layout-aware corpus exists for
controlled comparison. Full evaluation infrastructure (runner scripts,
comparison tool, result artifacts) committed under `scripts/` and
`eval-results/`.

### #726 Translation quality roadmap

Open release roadmap for air-gapped translation quality. Current state from the issue: fast/high lanes exist, but both effectively use LibreTranslate/Argos and full-text translation. The next safe slice is #727 translation metadata before provider or algorithm changes.

---

## Strategic ordering

Recommended order from 2026-06-14:

1. #714 Quality Lab.
2. #717 Permission Simulator.
3. #787 controlled #715 rollout experiment.
4. #727 translation provider/lane/purpose/validation metadata.
5. #728 segment-aware translation pipeline.
6. #663 Hermes automation only after quality/permission observability is stronger.

Do **not** jump directly to broad Hermes/write automation unless the owner explicitly pivots. The current risk is not missing features; it is safe rollout, measurement, and permission explainability.

---

## Watch / residual risks

- `docs/context/search.md` should document #715 hierarchy expansion + coarse-to-fine routing in addition to existing RRF/filter/trace/degradation notes.
- #715 flags are dark. Do not enable by default without comparison metrics and failed-case inspection.
- `DocumentChatCitation` historically lacked some item metadata (`chunk_id`, `translated_from` in some flows); Evidence Pack save uses available anchors, especially `citation_id`.
- NiFi/Kafka ingestion drain was previously identified as implemented but not wired into a running process. If NiFi ingestion matters, design a real worker/lifespan path before claiming release readiness.
- Air-gapped external LLM/LiteLLM passthrough exists in config/compose state from earlier work; first-boot smoke testing is still recommended for release packaging.
