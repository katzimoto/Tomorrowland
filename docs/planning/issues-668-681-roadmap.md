# Issues #668–#681 Roadmap — Evidence Packs, Ingestion Quality, Admin UX

**Branch:** `feature/planning-668-681`
**Author:** researcher
**Date:** 2026-06-11

## Already Complete

| Issue | Title | Status | Merge Commit |
|-------|-------|--------|-------------|
| #668 | Parser router | Merged to main | `ed18a3b` |
| #671 | Fixture corpus | Open | — |

## Remaining Issues: Dependency Graph

```
#669 (layout blocks) ──→ #670 (parser strategy UI)
     │                          
     │ (parallel track)         
     ▼                          
#672 (ingestion status page)     #670 data available for #672
     │
     ▼
#673 (timeline + safe retry) ←── needs #672 page
     │
     ├──→ #674 (source health dashboard) ←── uses /admin/sources/{id}/qa API
     │         │
     │         ▼
     │    #675 (surface health in search)
     │
     ▼
#676 (evidence pack schema + API) ◄── FOUNDATION for Wave 4–6
     │
     ├──→ #677 (save citations into packs from UI)
     │         │
     │         ▼
     │    #678 (pack detail UI + export)
     │         │
     │         ▼
     │    #679 (audit + permission tests)
     │
     ├──→ #680 (cited findings UI)
     │
     └──→ #681 (Hermes creates evidence packs) ←── BLOCKED by #612
```

### Flat Dependency Table

| Issue | Depends On | Blocks | Unblocked? |
|-------|-----------|--------|------------|
| #669 | — (independent) | #670 | ✅ Yes |
| #670 | #669 (for `layout_blocks_available` flag introduced by #669) | #672 (soft — data source) | ✅ Yes |
| #672 | #529 (backend exists), #661 (parent release issue, open), #670 (soft — related parallel track) | #673 | ✅ Yes |
| #673 | #672 (page to extend) | — | ✅ Yes |
| #674 | #608 #611 #663 (QA checks), #672 (related) | #675 | ✅ Yes |
| #675 | #674 (health data) | — | ✅ Yes |
| #676 | — (greenfield schema) | #677, #678, #679, #680, #681 | ✅ Yes |
| #677 | #676 (API) | #678 | ✅ Yes |
| #678 | #676, #677 | #679 | ✅ Yes |
| #679 | #676, #677, #678 | — | ✅ Yes |
| #680 | #676 (API) | #681 | ✅ Yes |
| #681 | #612 ❌, #676, #680 | — | ⛔ BLOCKED |

## Merge Order Recommendation

Issues are grouped into **feature branches** that can be developed and merged independently.

### Wave 1 — Parser Ecosystem (Parallel Track)
**Branch:** `feature/parser-ecosystem`
1. #669 — Persist layout blocks and page-region metadata
2. #670 — Show parser strategy in source/document UI

**Rationale:** #669 is pure backend (new `document_layout_blocks` table, schema, API). Note: the `document_blocks_available` table name only exists in `docs/design/parser-router.md` — it is design-only and has no migration or model yet. #670 is full-stack but depends on #669's `layout_blocks_available` flag (a new boolean field #669 introduces on the source/document response). These can run in parallel with Wave 2.

### Wave 2 — Ingestion Admin & Source Health
**Branch:** `feature/ingestion-admin`
3. #672 — Build ingestion status frontend page
4. #673 — Per-document processing timeline + safe retry
5. #674 — Source Health dashboard
6. #675 — Surface source health in evidence/search

**Rationale:** #672 uses existing backend endpoints (`GET /admin/ingestion/status`, `GET /admin/ingestion/status/{document_id}`) — already implemented in `src/services/api/routers/admin/ingestion_status.py`. #673 extends #672's page with timeline + retry actions. #674 uses existing `GET /admin/sources/{source_id}/qa` endpoint (`src/services/api/routers/admin/source_qa.py`). #675 depends on #674's health data.

### Wave 3 — Evidence Packs Backend
**Branch:** `feature/evidence-packs`
7. #676 — Evidence pack schema and API

**Rationale:** This is the foundation for all evidence pack work. Must land before any frontend evidence pack features. Greenfield — no existing `evidence_packs` table exists (confirmed by codebase search).

### Wave 4 — Evidence Packs Frontend
**Branch:** `feature/evidence-packs-ui`
8. #677 — Save citations/passages into packs from UI
9. #678 — Evidence pack detail UI + Markdown/JSON export

**Rationale:** #677 adds "Save to evidence pack" actions to existing citation cards and Evidence Inspector (`frontend/src/features/chat/EvidencePanel.tsx`). #678 builds the pack detail page with export.

### Wave 5 — Evidence Packs Quality & Security
**Branch:** `feature/evidence-packs-security`
10. #679 — Audit and permission tests for evidence packs

**Rationale:** Security hardening after all evidence pack features are in place. Tests cross-user access, permission revocation, export safety, audit trail completeness.

### Wave 6 — Advanced Evidence Features
**Branch:** `feature/evidence-packs-advanced`
11. #680 — Cited findings UI for advisory runs
12. #681 — Hermes advisory runs create evidence packs

**Rationale:** #680 provides the review UI for Hermes advisory outputs. #681 depends on #612 (approval gates) which is **still open and deferred** — must remain blocked.

## Feature Branch Strategy

```
main
 ├── feature/parser-ecosystem    (#669, #670)
 ├── feature/ingestion-admin     (#672, #673, #674, #675)
 ├── feature/evidence-packs      (#676)
 ├── feature/evidence-packs-ui   (#677, #678)
 ├── feature/evidence-packs-security (#679)
 └── feature/evidence-packs-advanced (#680, #681*)
```

Each feature branch targets `main`. PRs are opened per feature branch. #681 stays blocked until #612 lands.

## Crew Assignments & Complexity

| # | Issue | Assignee | Complexity | Est. Effort | Notes |
|---|-------|----------|------------|-------------|-------|
| #669 | Persist layout blocks | **backend-coder** | **L** | 3–5 days | New table `document_layout_blocks`, schema, API, tests. No existing layout block model. |
| #670 | Parser strategy UI | **frontend-coder** | **M** | 2–3 days | Extends `AdminSourceDetailPage.tsx` + `AdminIngestionPage.tsx`. Backend needs new fields on document/source responses. |
| #672 | Ingestion status page | **frontend-coder** | **S** | 1–2 days | Backend already exists (`ingestion_status.py`). Page already exists (`AdminIngestionPage.tsx`) — this completes/enhances it. |
| #673 | Timeline + safe retry | **backend-coder** | **L** | 3–4 days | New retry/reprocess endpoints, audit logging, duplicate prevention. Frontend timeline component. |
| #674 | Source health dashboard | **frontend-coder** | **M** | 2–3 days | Uses existing `GET /admin/sources/{id}/qa` API. New dashboard page + summary cards. |
| #675 | Health in search/evidence | **frontend-coder** | **M** | 2–3 days | Extends `EvidencePanel.tsx` and search results. Depends on #674 health data. |
| #676 | Evidence pack schema + API | **backend-coder** | **XL** | 5–7 days | Greenfield: new tables, CRUD API, permission checks, audit. Foundation for #677–#681. |
| #677 | Save citations to packs | **frontend-coder** | **M** | 2–3 days | UI actions on citation cards + Evidence Inspector. Uses #676 API. |
| #678 | Pack detail UI + export | **frontend-coder** | **M** | 2–3 days | New detail page, Markdown/JSON export endpoints on backend. |
| #679 | Audit + permission tests | **backend-coder** | **M** | 2–3 days | Security test suite. Cross-user, revocation, export safety. |
| #680 | Cited findings UI | **frontend-coder** | **L** | 3–4 days | New review UI for advisory runs. Depends on #676 API. |
| #681 | Hermes creates packs | **backend-coder** | **L** | 3–4 days | **BLOCKED by #612.** Agent write tools, approval flow integration. |

### Complexity Key
- **S** (Small): < 2 days, single component, existing patterns
- **M** (Medium): 2–3 days, full-stack or multi-component
- **L** (Large): 3–5 days, new models/APIs, significant testing
- **XL** (Extra-Large): 5+ days, greenfield foundation for multiple issues

## Risk Assessment

### High Risk
1. **#676 (Evidence pack schema)** — This is the foundation for 5 downstream issues (#677–#681). Schema changes after the fact are expensive. Must get the data model right: `evidence_packs` + `evidence_pack_items` tables, permission model, audit trail.
2. **#681 blocked by #612** — Issue #612 (approval gates) is labeled `status:deferred` and still open. #681 cannot proceed until #612 is implemented. This is a hard dependency.

### Medium Risk
3. **#669 (Layout blocks)** — New table with geometric data (bbox). Must handle missing layout gracefully for existing documents. Chunks need to reference layout block IDs.
4. **#673 (Safe retry)** — Retry/reprocessing actions are destructive if misused. Must have audit logging, admin-only enforcement, and duplicate/storm prevention.
5. **#679 (Security tests)** — Must cover all permission edge cases: cross-user access, revoked documents, export filtering. Any gap is a data leak.

### Low Risk
6. **#672 (Ingestion status page)** — Backend already exists. Frontend page already exists (`AdminIngestionPage.tsx`). This is primarily completion/enhancement.
7. **#674 (Source health dashboard)** — Uses existing QA API (`source_qa.py`). Primarily a frontend task.
8. **#670 (Parser strategy UI)** — Extends existing admin pages. Backend changes are additive (new fields on existing responses).

## Key Source File References

### Backend
- `src/services/api/routers/admin/ingestion_status.py` — Existing ingestion status API (#529)
- `src/services/api/routers/admin/sources.py` — Source CRUD + health fields
- `src/services/api/routers/admin/source_qa.py` — Source QA checks API
- `src/services/api/routers/admin/dlq.py` — Dead letter queue + requeue endpoint
- `src/services/api/routers/admin/ingestion.py` — Sync-now endpoint
- `src/services/api/routers/admin/parsers.py` — Parser admin endpoints
- `src/services/extraction/router.py` — ParserRouter with confidence scoring
- `src/services/documents/models.py` — Document model (no layout blocks yet)
- `src/services/api/schemas.py` — Shared Pydantic schemas

### Frontend
- `frontend/src/features/admin/AdminIngestionPage.tsx` — Existing ingestion status page
- `frontend/src/features/admin/AdminSourceDetailPage.tsx` — Source detail with document list
- `frontend/src/features/admin/AdminSourcesPage.tsx` — Source list
- `frontend/src/features/chat/EvidencePanel.tsx` — Evidence inspector (save-to-pack entry point)

### No Existing Evidence Pack Code
- Zero files match `evidence_pack` in the codebase
- Zero files match `EvidenceInspector` component
- Evidence pack schema, API, and UI are all greenfield

## Blocked Issues

| Issue | Blocked By | Reason |
|-------|-----------|--------|
| #681 | #612 (approval gates) | #612 is open + `status:deferred`. #681 requires approval-gate foundation before Hermes can create evidence packs. |

## Recommended Immediate Actions

1. **Start Wave 1 + Wave 2 in parallel** — #669 (backend) and #672 (frontend) can begin immediately since they're independent
2. **Prioritize #676** — Once Wave 2 starts, begin #676 immediately since 5 issues depend on it
3. **Monitor #612** — Track approval gates progress to unblock #681
4. **Schema review for #676** — Schedule a design review before implementing evidence pack tables. Owner: **backend-coder** (to present schema draft; reviewer: researcher + frontend-coder)
5. **Track #612 to unblock #681** — #612 (approval gates) is `status:deferred` and still open. Until it lands, #681 cannot be assigned. Add a recurring check on #612 status to the weekly planning cadence.

## Related Documents

- **Shared memory:** `docs/memory/current-state.md` — canonical active project state; update this file as waves complete.
- **Release queue:** `AGENTS.md` (root) — references this roadmap for crew assignment and PR ordering. Keep in sync when waves are added or reprioritized.
