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

## Phases

| Phase | Plan | Purpose |
| --- | --- | --- |
| 00 | `phase-00-repo-bootstrap.md` | Docs, repo hygiene, GitHub Actions |
| 01 | `phase-01-foundation.md` | Service skeleton, config, DB, schemas |
| 02 | `phase-02-auth-permissions.md` | Auth, JWT, groups, permission guards |
| 03 | `phase-03-core-search-mvp.md` | Ingestion, indexing, search, preview (overview) |
| 03a | `phase-03a-extraction-persistence.md` | Document persistence and text extraction |
| 03b | `phase-03b-translation-chunking.md` | Translation and chunking |
| 03c | `phase-03c-search-infrastructure.md` | Elasticsearch + Qdrant with mock embeddings |
| 03d | `phase-03d-worker-pipeline.md` | Fast worker pipeline and admin ingestion |
| 03e | `phase-03e-search-apis.md` | Search, preview, and download APIs |
| 04 | `phase-04-admin-operations.md` | Admin APIs, DLQ, audit, config |
| 05 | `phase-05-preview-enrichment.md` | Preview modes and translation enrichment |
| 05c | `translation-versions-plan.md` | Versioned manual translation history |
| 06 | `phase-06-intelligence-layer.md` | Ollama intelligence worker |
| 07 | `phase-07-rag-ui-features.md` | RAG, annotations, subscriptions, UI |
| 07a | `document-comments-plan.md` | Shared document comments |
| 08 | `phase-08-integrations-hardening.md` | Phase 08 overview and sub-phase index |
| 08c | `phase-08c-search-workspace.md` | Search workspace (UI Phase 01) |
| 08d | `phase-08d-document-detail.md` | Document preview, Q&A (UI Phase 02–03) |
| 08e | `phase-08e-collaboration-discovery.md` | Comments, annotations, subscriptions, expertise (UI Phase 04–06) |
| 08f | `phase-08f-production-smoke.md` | Production hardening overview and sub-phase index |
| 08f-1 | `phase-08f-1-production-defaults.md` | Production defaults, CORS hardening, and security guard audit |
| 08f-2 | `phase-08f-2-ops-docs.md` | Annotated environment template and production operations docs |
| 08f-3 | `phase-08f-3-compose-smoke.md` | No-mock Compose smoke test automation |
| 08f-4 | `phase-08f-4-smoke-bootstrap-helper.md` | Reusable smoke fixture bootstrap helper |
| 08f-5 | `phase-08f-5-production-audit.md` | Production audit helper for static checks and optional dependency audits |
| UI | `frontend-ui-plan.md` | Frontend phases folded into Phase 08 |
| 09 | `phase-09-optional-integrations.md` | NiFi, Atlassian, legacy Office formats |

## Review Gate

At the end of each phase, the Developer agent stops after validation. The
Reviewer agent audits correctness, coverage, docs, security, and style before
the next phase begins.
