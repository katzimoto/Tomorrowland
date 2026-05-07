# Phase 08: Integrations And Hardening

## Goal

Complete external integrations, observability, and hardening work.

## Scope

- NiFi integration.
- Confluence Server/Data Center polling.
- Jira Server/Data Center polling.
- Old Microsoft Office binary format extraction (`.doc`, `.xls`, `.ppt`).
- Observability stack.
- Security sanitization.
- Performance tuning.
- Final documentation pass.

## Implementation Notes

- Old Office binary formats (`.doc`, `.xls`, `.ppt`) are deferred to this phase
  because they require extra system dependencies (`antiword` for `.doc`,
  `xlrd` or `pywin32` COM for `.xls`/`.ppt`) and are increasingly rare in
  modern enterprise environments. The extraction registry will gain new
  extractors: `DocExtractor`, `XlsExtractor`, `PptExtractor`.
- These extractors should follow the same `Extractor` protocol as Phase 03a
  and return `""` on failure without raising.

## Decision Gates

- Resolve Atlassian permissions and URL validation gaps.

## Validation

- Mocked Atlassian sync tests.
- NiFi event tests.
- Metrics and logging tests.
- HTML sanitization tests.
- Load and performance smoke tests.

## Acceptance Criteria

- External integrations are deterministic under test.
- Logs and metrics support production debugging.
- Security checks cover HTML, auth, secrets, and dependency surfaces.
