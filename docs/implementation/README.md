# Implementation Plan Index

Implementation is split into reviewable phases. Each phase should be developed
on its own branch and reviewed before the next phase starts.

## Rules

- One phase equals one PR unless explicitly split into smaller PRs.
- Do not push directly to `main`.
- Preserve `spec.md` and `spec-v4.pdf` as source references.
- Use `agents.md` for Developer and Reviewer agent responsibilities.
- Use `skill.md` for TDD, linting, documentation, and coverage expectations.
- Resolve phase blockers in `docs/review/spec-gaps.md` before coding the phase.

## What to work on next

See `AGENTS.md ## Mission queue` for the prioritized list of available missions with branch
names and parallel-safety flags. Do not start a phase from this table without checking the
queue first.

## Phases

| Phase | Plan | Purpose | Status |
| --- | --- | --- | --- |
| 00 | `phase-00-repo-bootstrap.md` | Docs, repo hygiene, GitHub Actions | Done ✅ |
| 01 | `phase-01-foundation.md` | Service skeleton, config, DB, schemas | Done ✅ |
| 02 | `phase-02-auth-permissions.md` | Auth, JWT, groups, permission guards | Done ✅ |
| 03 | `phase-03-core-search-mvp.md` | Ingestion, indexing, search, preview (overview) | Done ✅ |
| 03a | `phase-03a-extraction-persistence.md` | Document persistence and text extraction | Done ✅ |
| 03b | `phase-03b-translation-chunking.md` | Translation and chunking | Done ✅ |
| 03c | `phase-03c-search-infrastructure.md` | Elasticsearch + Qdrant with mock embeddings | Done ✅ |
| 03d | `phase-03d-worker-pipeline.md` | Fast worker pipeline and admin ingestion | Done ✅ |
| 03e | `phase-03e-search-apis.md` | Search, preview, and download APIs | Done ✅ |
| 04 | `phase-04-admin-operations.md` | Admin APIs, DLQ, audit, config | Done ✅ |
| 05 | `phase-05-preview-enrichment.md` | Preview modes and translation enrichment | Done ✅ |
| 05c | `phase-05c-translation-versions.md` | Versioned manual translation history | Done ✅ |
| 06 | `phase-06-intelligence-layer.md` | Ollama intelligence worker | Done ✅ |
| 07 | `phase-07-rag-ui-features.md` | RAG, annotations, subscriptions, UI | Done ✅ |
| 07a | `phase-07a-document-comments.md` | Shared document comments | Done ✅ |
| 08 | `phase-08-integrations-hardening.md` | Phase 08 overview and sub-phase index | Done ✅ |
| 08b | `phase-08b-frontend-ui.md` | Frontend phases (design system through expertise map) | In progress 🔄 |
| 08c | `phase-08c-search-workspace.md` | Search workspace (UI Phase 01) | In progress 🔄 |
| 08d | `phase-08d-document-detail.md` | Document preview, Q&A (UI Phase 02–03) | In progress 🔄 |
| 08e | `phase-08e-collaboration-discovery.md` | Comments, annotations, subscriptions, expertise (UI Phase 04–06) | In progress 🔄 |
| 08f | `phase-08f-production-smoke.md` | Production hardening overview and sub-phase index | Done ✅ |
| 08f-1 | `phase-08f-1-production-defaults.md` | Production defaults, CORS hardening, and security guard audit | Done ✅ |
| 08f-2 | `phase-08f-2-ops-docs.md` | Annotated environment template and production operations docs | Done ✅ |
| 08f-3 | `phase-08f-3-compose-smoke.md` | No-mock Compose smoke test automation | Done ✅ |
| 08f-4 | `phase-08f-4-smoke-bootstrap-helper.md` | Reusable smoke fixture bootstrap helper | Done ✅ |
| 08f-5 | `phase-08f-5-production-audit.md` | Production audit helper for static checks and optional dependency audits | Done ✅ |
| 09 | `phase-09-optional-integrations.md` | Phase 09 overview and sub-phase index | Planned |
| 09a | `phase-09a-nifi-integration.md` | NiFi event integration and Kafka consumer wiring | **Next** (parallel-safe) |
| 09b | `phase-09b-legacy-office-extraction.md` | `.doc`, `.xls`, `.ppt` binary extraction | **Next** (parallel-safe) |
| 09c | `phase-09c-atlassian-hardening.md` | Optional Atlassian permission sync and redirect hardening | Conditional |
| 10 | `phase-10-observability.md` | Phase 10 overview and sub-phase index | Planned |
| 10a | `phase-10a-metrics-foundation.md` | Prometheus `/metrics`, HTTP middleware, request-ID | Done ✅ |
| 10b | `phase-10b-domain-metrics.md` | Instrument auth, pipeline, search, RAG, collaboration | Done ✅ |
| 10c | `phase-10c-admin-readiness.md` | Admin readiness endpoint with dependency probes | **Next** |
| 10d | `phase-10d-monitoring-compose.md` | Optional Prometheus + Grafana Compose profile | **Next** |
| 10e | `phase-10e-structured-logs.md` | JSON structured logs and OpenTelemetry hooks | **Next** |
| 10f | `phase-10f-worker-observability.md` | Worker heartbeats and consumer lag | Deferred |

## Review Gate

At the end of each phase, the Developer agent stops after validation. The
Reviewer agent audits correctness, coverage, docs, security, and style before
the next phase begins.
