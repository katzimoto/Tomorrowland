# Phase 04: Admin And Operations

## Goal

Expose operational control surfaces for administrators.

## Scope

- Admin APIs for users, groups, permissions, ingestion sources, config, DLQ, and
  activity audit.
- System config update behavior.
- DLQ retry interface.

## Validation

- Admin-only endpoint tests.
- Config update/read tests.
- DLQ retry tests.

## Acceptance Criteria

- Admin users can configure the running system without restart where specified.
- Non-admin users cannot access admin endpoints.
- DLQ retry behavior is auditable.
