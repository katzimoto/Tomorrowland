# Tomorrowland Current State

Canonical shared memory for active project state. Keep this file compact and factual.
<!-- Compaction cutoff: 2026-06-14. Older detailed entries intentionally compacted here; use git history for the prior long-form state log. -->

## 2026-06-14 — Current product baseline

Status: **post-foundation / pre-rollout**.

Tomorrowland is now best understood as an air-gapped, permission-aware document intelligence workspace with:

- high-fidelity document preview for mail, Office, PDF/image/text, and structured XLSX grids;
- parser/layout-aware document understanding with Docling/layout metadata foundations;
- hybrid retrieval with Meilisearch/BM25 + Qdrant/vector, weighted RRF, optional reranker, metadata/translated lanes, and safe degraded-backend traces;
- Evidence Inspector, citation feedback, source health visibility, and operator diagnostics;
- durable Evidence Packs with backend API, UI save flows, detail pages, and Markdown/JSON exports;
- hierarchy-aware RAG context packing and coarse-to-fine section routing implemented but disabled by default;
- RAG threat model and offline regression coverage for prompt-injection/ACL/metadata/translation leakage risks.

Open implementation PR count observed 2026-06-14: **0**.

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

## Active next work

### #714 Quality Lab — priority:next, status:ready

Recommended next major implementation.

Purpose: turn offline/nightly eval artifacts into an admin-facing dashboard for retrieval, parser, citation, permission, no-answer, degradation, and latency regressions.

Why now: #715 introduced dark retrieval/context-packing knobs. Quality Lab should compare flat retrieval vs hierarchy expansion vs coarse-to-fine vs combined mode before any default-on decision.

### #717 Permission Simulator — priority:next, status:ready

Recommended parallel/high-priority trust work.

Purpose: let admins simulate user/group/source/document/query access and explain allow/deny reasons without leaking inaccessible text.

Why now: Evidence Packs, exports, derived translations, and future Hermes workflows all rely on explainable permission safety.

### #787 Controlled #715 rollout experiment

Purpose: evaluate hierarchy expansion and coarse-to-fine routing under controlled metrics before enabling either by default.

Suggested dependency: #714 skeleton or equivalent stored eval artifacts.

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
