# Phase 08f: Production Hardening Overview

## Goal

Split production hardening into multiple small, reviewable planning PRs so each
agent can validate one operational concern without blocking frontend feature
work.

Phase 08f remains independent of Phase 08c, 08d, and 08e. It can start after
Phase 08b because the production Compose runtime and frontend container already
exist.

## Sub-Phases

| Sub-phase | Plan | Branch | Purpose |
| --- | --- | --- | --- |
| 08f-1 | `phase-08f-1-production-defaults.md` | `developer/phase-08f-1-production-defaults` | Production defaults, CORS hardening, and security guard audit |
| 08f-2 | `phase-08f-2-ops-docs.md` | `developer/phase-08f-2-ops-docs` | Annotated environment template and production operations documentation |
| 08f-3 | `phase-08f-3-compose-smoke.md` | `developer/phase-08f-3-compose-smoke` | No-mock Compose smoke test automation |

## Recommended Dependency Order

1. Land Phase 08f-1 first so configuration names and secure defaults are stable.
2. Land Phase 08f-2 second so documentation reflects the final production
   configuration surface.
3. Land Phase 08f-3 last so the smoke script can rely on stable environment
   names, documented reset behavior, and hardened defaults.

Phase 08f-2 may begin before 08f-1 merges if the agent keeps environment names
in sync with 08f-1 before review. Phase 08f-3 should wait unless the smoke-test
agent explicitly verifies the latest defaults and docs before implementation.

## Overall Acceptance Criteria

- `docker compose up` starts the API, frontend, migration job, and all required
  infrastructure services without manual code changes.
- Production defaults avoid wildcard CORS, debug/reload modes, real tracked
  secrets, and unsafe download-path behavior.
- Clean-volume migration from scratch succeeds.
- Production operations docs are sufficient for a local operator to start,
  stop, reset, back up, and troubleshoot the system.
- The no-mock smoke test completes authentication, source setup, ingestion,
  search, preview, download, and frontend reachability.
- Accepted audit exceptions, if any, are documented with justification.

## Shared Do Not Start Criteria

Do not start any implementation sub-phase if the repository has known broken
Compose healthchecks that would cause validation to hang indefinitely. Fix the
healthcheck first or document a narrowly scoped skip in the sub-phase PR.

Do not commit real secrets to address audit findings. Replace them with
placeholders and rotate any secret that was exposed.

Do not edit `spec.md` or `spec-v4.pdf` for this work; implementation guidance
belongs in the phase plans and operations docs.

## Optional Future Split

If Phase 08f-3 reveals that test fixture creation requires a reusable admin or
bootstrap helper, split that helper into an optional Phase 08f-4 planning PR
instead of expanding the smoke-test PR beyond reviewable size.
