# Phase 08: Productization, UI, And Production Compose

## Goal

Turn the completed backend capability set into a usable local-first product.
Docker Compose should start infrastructure, backend services, and the browser UI
together, and a user should be able to complete the main workflows without
mocked services.

## Scope

- Production-oriented Docker runtime for API, frontend, migrations, and required
  infrastructure.
- Browser UI for the main user product.
- Real API wiring for auth, search, preview/download, Q&A, comments,
  annotations, subscriptions/notifications, related documents, and expertise.
- No-mock Compose smoke test covering the main product path.
- Production documentation for local deployment, reset, backup, and operations.

## Out Of Scope

- NiFi integration.
- Confluence Server/Data Center polling.
- Jira Server/Data Center polling.
- Old Microsoft Office binary extraction (`.doc`, `.xls`, `.ppt`).
- Kafka consumer wiring that is not required for the production UI milestone.

These optional integration items move to Phase 09.

## Phase 08a: Compose Runtime Foundation

Status: Complete. See `docs/operations/production-compose.md`.

## Phase 08b: Frontend Foundation

Status: Complete. See `docs/implementation/frontend-ui-plan.md` UI Phase 00.

## Phase 08c: Search Workspace

Plan: `docs/implementation/phase-08c-search-workspace.md`
Branch: `developer/phase-08c-search-workspace`

Auth shell wiring, `/search` route, search results and filters, saved searches.
Can start immediately in parallel with Phase 08f.

## Phase 08d: Document Detail And Q&A

Plan: `docs/implementation/phase-08d-document-detail.md`
Branch: `developer/phase-08d-document-detail`
Prerequisite: Phase 08c review gate passed.

Document route `/doc/:doc_id`, all preview mode renderers, translation version
selector, download, intelligence display, related documents, and the `/qa` route
with citations.

## Phase 08e: Collaboration And Discovery

Plan: `docs/implementation/phase-08e-collaboration-discovery.md`
Branch: `developer/phase-08e-collaboration-discovery`
Prerequisite: Phase 08c review gate passed; `insightPaneTabs.ts` contract
committed by the 08d agent.

Comments, annotations, subscriptions, notifications, history, expertise map,
command menu, and final visual polish sweep. Can run in parallel with Phase 08d.

## Phase 08f: Production Hardening

Plan: `docs/implementation/phase-08f-production-smoke.md`
Prerequisite: None — fully independent of all frontend work.

Phase 08f is split into five reviewable hardening PRs:

- 08f-1 production defaults and security guards on branch
  `developer/phase-08f-1-production-defaults`.
- 08f-2 production operations documentation on branch
  `developer/phase-08f-2-ops-docs`.
- 08f-3 no-mock Compose smoke test on branch
  `developer/phase-08f-3-compose-smoke`.
- 08f-4 reusable smoke bootstrap helper on branch
  `developer/phase-08f-4-smoke-bootstrap-helper`.
- 08f-5 production audit helper on branch
  `developer/phase-08f-5-production-audit`.

Land 08f-1 first, then 08f-2, 08f-3, 08f-4, and 08f-5 unless the later agent
verifies that environment variable names, production defaults, and smoke helper
behavior are already stable. Can start at any point after Phase 08b.

## Acceptance Criteria

- `docker compose up` starts a working local product with backend, UI, and
  required infrastructure.
- A browser user can complete the main product workflows without mocks.
- Clean Compose volumes can be migrated from scratch.
- Production docs are sufficient for a local operator to start, stop, reset,
  back up, and troubleshoot the system.
