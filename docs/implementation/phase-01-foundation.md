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

## Decision Gates

- Resolve document persistence, document identity, `group_id`, and NiFi event
  ownership gaps before coding.

## Validation

- Docker Compose configuration validates.
- Migrations run locally.
- Unit tests cover config, feature flag defaults, schemas, and logging helpers.

## Acceptance Criteria

- Later phases can add services without changing foundational conventions.
- Runtime config has documented defaults and `.env.example` parity.
- Foundation PR contains no feature implementation beyond the shared base.
