# Top-1 Document Intelligence Roadmap Research — 2026-06-10

## Purpose

This note captures the product/research direction created from the UI/UX benchmark and Tomorrowland current-state review. It should be treated as the durable reference for future planning, Codex/Claude/opencode missions, release planning, and backlog triage.

## Core positioning

Tomorrowland should not compete as a generic chat app or a direct Onyx clone. The credible top-1 position is:

> The best air-gapped, permission-safe, multilingual document intelligence system for source-faithful search, chat, evidence, QA, and review.

This means optimizing for:

1. Document understanding quality for messy enterprise files.
2. Citation trust UX: exact preview, page/section, original/translated text, retrieval trace, parser path, source health.
3. Air-gapped operator experience.
4. Permission safety and auditability.
5. Offline evals for document QA, citation accuracy, no-answer correctness, and permission boundaries.
6. Proactive but controlled review workflows through Hermes.

## Current-state assumptions used

- Canonical runtime: NiFi → Kafka/Redpanda → NiFiKafkaDrain → RabbitMQ → parse/translate/embed/index → Meilisearch/Qdrant.
- Meilisearch is the primary BM25 index; Elasticsearch was removed.
- Qdrant + Meilisearch hybrid retrieval exists.
- Retrieval trace foundation exists.
- Side-by-side evidence panel exists.
- Exact-location citation grounding has started.
- Admin ingestion status backend exists; frontend was deferred.
- Source QA deterministic checks exist for empty chunks, missing payloads, missing metadata/title, OCR needs, and index lag.
- Model provider registry and OpenAI-compatible provider foundation exist.
- Hermes planning exists, but Hermes must not own ACL, audit, approvals, persistence, or business rules.

## Top-level release trackers

- #659 — `release(v0.3): Trust and Retrieval Quality`
- #660 — `release(v0.4): Document Understanding and Parser Routing`
- #661 — `release(v0.5): Operator Cockpit and Source Health`
- #662 — `release(v0.6): Evidence Packs and Review Workflow`
- #663 — `release(v0.7): Controlled Hermes Automation`

## v0.3 — Trust and Retrieval Quality

Goal: make the ask/search loop measurably trustworthy and debuggable.

Child issues:

- #650 — BGE reranker for hybrid search relevance.
- #664 — Evidence Inspector v1 for citations.
- #665 — Retrieval trace admin/developer UI.
- #666 — Citation feedback as a quality signal.
- #667 — Offline retrieval and citation quality harness.

Execution order:

1. Merge/review #658.
2. Implement #650 reranker.
3. Implement #665 retrieval trace UI.
4. Implement #664 Evidence Inspector v1.
5. Implement #666 citation feedback.
6. Implement #667 offline eval harness.

Exit criteria:

- Reranker enabled behind config/feature flag and visible in retrieval trace.
- Evidence Inspector shows citation, source, retrieval, parser/translation metadata where available.
- Admin/developer retrieval trace UI exists.
- Citation feedback is stored and usable by evals.
- Offline eval runner can compare at least two retrieval configurations.

## v0.4 — Document Understanding and Parser Routing

Goal: understand messy enterprise documents better than generic RAG systems.

Child issues:

- #649 — Docling integration for advanced document processing.
- #668 — Parser router and parser strategy policies.
- #669 — Layout blocks and page-region metadata.
- #670 — Parser strategy and extraction quality in source/document UI.
- #671 — Parser/layout fixture corpus expansion.

Execution order:

1. Implement #668 parser routing foundation.
2. Implement/adjust #649 Docling as one parser backend.
3. Implement #669 layout block/page-region metadata.
4. Implement #670 parser strategy/admin visibility.
5. Implement #671 parser/layout fixture eval expansion.

Design principle:

Docling should be a backend behind parser routing, not a blind global replacement.

Suggested parser strategies:

- Fast native text parser.
- Docling/layout-aware parser.
- OCR/scanned-document parser.
- Table-heavy parser.
- Office document parser.
- Email/archive parser.
- Manual-review/failure path.

## v0.5 — Operator Cockpit and Source Health

Goal: make Tomorrowland easy to operate in air-gapped/self-hosted environments.

Child issues:

- #672 — Ingestion status frontend page.
- #673 — Per-document processing timeline and safe retry actions.
- #674 — Source Health dashboard from deterministic QA checks.
- #675 — Source health in evidence and search confidence.

Execution order:

1. Implement #672 ingestion status frontend.
2. Implement #674 Source Health dashboard.
3. Implement #673 processing timeline + safe retry actions.
4. Implement #675 source health in evidence/search confidence.

Processing timeline target:

```text
uploaded → detected → parsed → OCR → translated → chunked → embedded → Meilisearch indexed → Qdrant indexed → QA checked
```

Source health should expose:

- total/indexed/pending/failed documents
- empty chunks
- missing content payloads
- missing metadata/title
- OCR eligible / OCR maybe needed
- index lag count
- latest check time
- issue list and severity
- recommended actions

## v0.6 — Evidence Packs and Review Workflow

Goal: turn answers/search results into durable, auditable evidence artifacts.

Child issues:

- #676 — Evidence pack schema and API.
- #677 — Save citations/passages into evidence packs from UI.
- #678 — Evidence pack detail UI and Markdown/JSON export.
- #679 — Audit and permission tests for evidence packs.
- #681 — Advisory Hermes runs create evidence packs after approval gates.

Execution order:

1. Implement #676 evidence pack schema/API.
2. Implement #679 security/audit tests alongside backend work.
3. Implement #677 save-to-pack UI.
4. Implement #678 detail UI and export.
5. Defer #681 until #612 and #663 prerequisites are ready.

Evidence pack concept:

```text
Evidence Pack
- title
- question/task
- answer or finding summary
- claims
- evidence items
- original snippets
- translated snippets
- page/section/chunk references
- retrieval trace reference where safe
- source health snapshot where safe
- created by user or Hermes
- export: Markdown, JSON, later PDF
```

## v0.7 — Controlled Hermes Automation

Goal: make Tomorrowland proactive without becoming unsafe.

Child issues:

- #608 — Deterministic source QA runner.
- #610 — Scheduled document intelligence jobs.
- #611 — Hermes run inspection UI.
- #612 — Approval gates before write/destructive tools.
- #680 — Cited findings UI for digest, conflict, and compliance jobs.
- #681 — Advisory Hermes runs create evidence packs after approval gates.

Execution order:

1. Follow #603 slice dependencies for Hermes spine/tooling.
2. Implement #608 deterministic source QA runner.
3. Implement #611 run inspection UI.
4. Implement #610 scheduled advisory jobs.
5. Implement #680 cited findings review UI.
6. Implement #612 approval gates.
7. Implement #681 only after #612 and #676.

Core constraint:

Hermes can plan, inspect, and propose. Core services own permissions, audit, persistence, budgets, approvals, and execution boundaries.

## Product UX target

The main trusted workflow should become:

```text
Ask / Search
→ retrieve evidence
→ answer with citations
→ click citation
→ preview exact source
→ inspect retrieval trace
→ verify permission + translation + parser path + source health
→ save evidence pack
```

This flow is more important than adding many generic agents.

## Benchmarks and differentiation

Use external products as benchmarks, but do not copy them blindly:

- Onyx: benchmark for enterprise search, connectors, permissions, and agents.
- RAGFlow: benchmark for document parsing and visual citation grounding.
- Open WebUI: benchmark for local model/RAG controls.
- Dify: benchmark for human-in-the-loop review workflow.
- Glean: benchmark for search filters and enterprise search ergonomics.

Tomorrowland should differentiate by combining:

- Air-gapped deployment.
- Permission-safe source-grounded answers.
- Multilingual original/translated retrieval.
- Source-faithful preview and citation inspection.
- Operator-grade ingestion/source health diagnostics.
- Evidence packs as durable review artifacts.
- Controlled Hermes automation.

## Anti-goals

Do not prioritize:

- Generic chat-first UX.
- Broad SaaS connector race before the trust loop is excellent.
- Full Dify-style visual workflow canvas.
- Generic agents without document-intelligence purpose.
- Hidden retrieval/parser settings only in config files.
- Citation chips that do not support inspection.

## Immediate strongest sequence

```text
1. Merge/review #658
2. Ship #650 BGE reranker
3. Ship #668 parser router
4. Ship #649 Docling behind parser router
5. Ship #665 retrieval trace UI
6. Ship #664 Evidence Inspector
7. Ship #672/#674 operator/source health views
8. Ship #676/#677 evidence packs
9. Then let Hermes automate QA/review on top
```
