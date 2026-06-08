# Phase 01: Foundation

## Goal

Create the system foundation that later services will share.

## Scope

- Docker Compose skeleton.
- Shared config package.
- Base service directory layout.
- Alembic migration setup.
- Postgres schema foundation.
- `system_config` seed migration.
- Shared Kafka schema definitions.
- Structured logging and correlation ID helpers.
- Health endpoint conventions.

## Implementation Notes

- Docker Compose in this phase is infrastructure-only. It validates the
  foundational service dependencies and does not yet require API or worker
  application containers.

## Decision Gates

- Document identity uses UUID primary keys; source-specific stable identifiers
  are stored as `external_id`.
- Document access inherits from `source_permissions`; documents do not carry a
  single `group_id`.
- NiFi and ingestion both publish normalized `documents.raw` events.
- The foundation migration creates the canonical `documents` table.

## Validation

- Docker Compose configuration validates.
- Migrations run locally.
- Unit tests cover config, feature flag defaults, schemas, and logging helpers.

## Acceptance Criteria

- Later phases can add services without changing foundational conventions.
- Runtime config has documented defaults and `.env.example` parity.
- Foundation PR contains no feature implementation beyond the shared base.
