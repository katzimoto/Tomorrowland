# Documentation Guide

This folder contains all project documentation. Read in this order.

## 1. Start Here

| File | Purpose | When to read |
|------|---------|-------------|
| `logical-spec.md` | Product behavior, domain model, non-functional requirements | First session, before any coding |
| `implementation/README.md` | Phase index — what has been built and what comes next | Every new phase |
| `review/spec-gaps.md` | Architecture decisions and blockers | Before starting a phase |

## 2. Implementation Plans

Located in `implementation/`. Each phase gets one file; multi-feature phases get an overview
plus per-feature sub-plans.

| Phase | File | Status |
|-------|------|--------|
| 00 | `phase-00-repo-bootstrap.md` | Done |
| 01 | `phase-01-foundation.md` | Done |
| 02 | `phase-02-auth-permissions.md` | Done |
| 03 | `phase-03-core-search-mvp.md` | Done |
| 03a | `phase-03a-extraction-persistence.md` | Done |
| 03b | `phase-03b-translation-chunking.md` | Done |
| 03c | `phase-03c-search-infrastructure.md` | Done |
| 03d | `phase-03d-worker-pipeline.md` | Done |
| 03e | `phase-03e-search-apis.md` | Done |
| 04 | `phase-04-admin-operations.md` | Done |
| 05 | `phase-05-preview-enrichment.md` | Done |
| 05c | `phase-05c-translation-versions.md` | In progress |
| 06 | `phase-06-intelligence-layer.md` | Done |
| 07 | `phase-07-rag-ui-features.md` | Done |
| 07a | `phase-07a-document-comments.md` | Done |
| 08 | `phase-08-integrations-hardening.md` | Done |
| 08b | `phase-08b-frontend-ui.md` | In progress |
| 08c | `phase-08c-search-workspace.md` | Done |
| 08d | `phase-08d-document-detail.md` | Done |
| 08e | `phase-08e-collaboration-discovery.md` | Done |
| 08f | `phase-08f-production-smoke.md` | Done |
| 08f-1 | `phase-08f-1-production-defaults.md` | Done |
| 08f-2 | `phase-08f-2-ops-docs.md` | Done |
| 08f-3 | `phase-08f-3-compose-smoke.md` | Done |
| 08f-4 | `phase-08f-4-smoke-bootstrap-helper.md` | Done |
| 08f-5 | `phase-08f-5-production-audit.md` | Done |
| 09 | `phase-09-optional-integrations.md` | Planned (index) |
| 09a | `phase-09a-nifi-integration.md` | Planned |
| 09b | `phase-09b-legacy-office-extraction.md` | Planned |
| 09c | `phase-09c-atlassian-hardening.md` | Planned (conditional) |
| 10 | `phase-10-observability.md` | Planned (index) |
| 10a | `phase-10a-metrics-foundation.md` | Done |
| 10b | `phase-10b-domain-metrics.md` | Planned |
| 10c | `phase-10c-admin-readiness.md` | Planned |
| 10d | `phase-10d-monitoring-compose.md` | Planned |
| 10e | `phase-10e-structured-logs.md` | Planned |
| 10f | `phase-10f-worker-observability.md` | Deferred |

## 3. Design Documents

Located in `design/`. UI/UX specs, metric catalogs, and non-implementation design work.
Each design document pairs with one or more implementation plans.

| File | Purpose | Paired Plan |
|------|---------|-------------|
| `user-ui-spec.md` | Full UI specification (routes, shell, interactions) | `phase-08b-frontend-ui.md` |
| `translation-versions-spec.md` | Translation versioning UX and API contracts | `phase-05c-translation-versions.md` |
| `document-comments-spec.md` | Shared document comments UX and API contracts | `phase-07a-document-comments.md` |
| `metrics-monitoring-spec.md` | Metric catalog, dashboards, alerts, structured log schema | `phase-10a` through `phase-10f` |
| `logo-options.md` | Logo candidates and recommendation | — |
| `assets/*.svg` | Logo SVG files | — |

## 4. Operations

Located in `operations/`. Production operations and infrastructure guides.

| File | Purpose |
|------|---------|
| `production-compose.md` | Compose service layout, first-run setup, reset, backup, troubleshooting |

## 5. Review And Decisions

Located in `review/`. Architecture decision log and spec gap analysis.

| File | Purpose |
|------|---------|
| `spec-gaps.md` | Resolved and open blockers per phase |

---

**Rule:** `spec.md` and `spec-v4.pdf` in the repo root are canonical client specs.
Do not modify them. All interpretation, decisions, and gap-filling go in this folder.
