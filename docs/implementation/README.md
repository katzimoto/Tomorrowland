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
| 03 | `phase-03-core-search-mvp.md` | Ingestion, indexing, search, preview |
| 04 | `phase-04-admin-operations.md` | Admin APIs, DLQ, audit, config |
| 05 | `phase-05-preview-enrichment.md` | Preview modes and translation enrichment |
| 06 | `phase-06-intelligence-layer.md` | Ollama intelligence worker |
| 07 | `phase-07-rag-ui-features.md` | RAG, annotations, subscriptions, UI |
| 08 | `phase-08-integrations-hardening.md` | NiFi, Atlassian, observability, hardening |

## Review Gate

At the end of each phase, the Developer agent stops after validation. The
Reviewer agent audits correctness, coverage, docs, security, and style before
the next phase begins.
