# Documentation

Start here when you are not sure which Tomorrowland document to read. The root
README is the landing page; this index routes by audience.

## Operators

- [Air-gapped deployment](operations/air-gapped-deployment.md) — offline install
  using the platform archive, split image parts, and optional model bundle.
- [Air-gapped upgrade](operations/air-gapped-upgrade.md) — data-safe upgrade path
  that preserves `.env` and persistent volumes.
- [Production Compose](operations/production-compose.md) — connected Compose
  operation, service layout, backups, troubleshooting, and connector notes.
- [Release notes](operations/release-notes-rc.md) — release-candidate operator
  notes and known limitations.

## Developers

- [Local development](development/local-dev.md) — repository setup and local
  runtime orientation.
- [Testing](development/testing.md) — targeted backend and frontend checks.
- [Architecture overview](architecture/overview.md) — concise system map and
  major runtime components.
- [Logging system design](design/logging-system-spec.md) — structured JSON log
  schema, safe event taxonomy, request/operation correlation, and redaction rules.
- [Implementation plan index](implementation/README.md) — historical phase plans;
  use GitHub Issues as the current source of truth when an issue exists.

## Agents

- [Agent instructions](agents/README.md) — practical issue-first workflow for
  Codex, Claude Code, and human handoffs.
- [Token efficiency](agents/token-efficiency.md) — context-loading rules.
- [Issue context template](agents/issue-context-template.md) — compact issue
  format with allowed paths and acceptance criteria.

## Canonical requirements

`spec.md` and `spec-v4.pdf` in the repository root are canonical client specs.
Do not edit them unless the user explicitly asks.
