# Documentation Guide

This folder contains all project documentation. Read in this order.

## 1. Start Here

| File | Purpose | When to read |
|------|---------|-------------|
| `logical-spec.md` | Product behavior, domain model, non-functional requirements | First session, before any coding |
| `implementation/README.md` | Phase index — what has been built and what comes next | Every new phase |
| `review/spec-gaps.md` | Architecture decisions and blockers | Before starting a phase |

## 2. Implementation Plans

Located in `implementation/`. Each phase gets one file.

| Phase | File | Status |
|-------|------|--------|
| 00 | `phase-00-repo-bootstrap.md` | Done |
| 01 | `phase-01-foundation.md` | Done |
| 02 | `phase-02-auth-permissions.md` | Done |
| 03a | `phase-03a-extraction-persistence.md` | Done |
| 03b | `phase-03b-translation-chunking.md` | Done |
| 03c | `phase-03c-search-infrastructure.md` | Done |
| 03d | `phase-03d-worker-pipeline.md` | Done |
| 03e | `phase-03e-search-apis.md` | Done |
| 04 | `phase-04-admin-operations.md` | Done |
| 05a/b | `phase-05-preview-enrichment.md` | Done |
| 06 | `phase-06-intelligence-layer.md` | Next |
| 07 | `phase-07-rag-ui-features.md` | Planned |
| 08 | `phase-08-integrations-hardening.md` | Planned |
| UI | `frontend-ui-plan.md` | Planned |
| 10 | `phase-10-observability.md` | Planned |

## 3. Design Documents

Located in `design/`. UI/UX specs, logo assets, and non-implementation design work.

| File | Purpose |
|------|---------|
| `user-ui-spec.md` | Full UI specification |
| `metrics-monitoring-spec.md` | Metrics, monitoring, readiness, dashboard, and alert design |
| `logo-options.md` | Logo candidates and recommendation |
| `assets/*.svg` | Logo SVG files |

## 4. Review & Decisions

Located in `review/`. Architecture decision log and spec gap analysis.

| File | Purpose |
|------|---------|
| `spec-gaps.md` | Resolved and open blockers per phase |

---

**Rule:** `spec.md` and `spec-v4.pdf` in the repo root are canonical client specs.
Do not modify them. All interpretation, decisions, and gap-filling go in this folder.
