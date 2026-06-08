# Phase 09c: Optional Atlassian Hardening

## Goal

Implement optional Atlassian permission hardening only if operators require it. Evaluate
whether the current source-grant model is sufficient or whether page/project-level permission
synchronization is needed.

## Phase Placement

Branch: `developer/phase-09c-atlassian-hardening`

Status: Planned (conditional — proceed only after Decision Gates are resolved).

## Current Baseline

- `ConfluenceConnector` and `JiraConnector` are registered and ship in production.
- Both connectors validate Server/Data Center base URLs and reject Atlassian Cloud hosts
  (`atlassian.net` and subdomains).
- Imported Atlassian documents use the source-grant permission model: access to a document
  is granted to users/groups that have a grant on the ingestion source.
- Page-level or project-level Confluence/Jira permission synchronization is not implemented.
- Attachment redirect URLs are validated against the configured base URL but do not have an
  explicit host allowlist beyond that check.

## Dependencies

- Phase 02 auth and permission guards.
- Phase 04 admin ingestion source management.
- Existing `ConfluenceConnector` and `JiraConnector` in `src/services/connectors/`.

## Decision Gates

Resolve the following before any implementation in this phase:

1. **Permission sync needed?** Determine whether the source-grant model is sufficient for
   the target operators, or whether fine-grained page/space/project permission mirroring
   is required. Record the decision in `docs/review/spec-gaps.md`.
2. **Redirect host allowlist needed?** Determine whether attachment/API redirect validation
   requires an explicit host allowlist beyond the current base URL check.

If both decisions are "not required", this phase has no implementation work and can be
closed with a note in `docs/review/spec-gaps.md`.

## Scope (If Proceeding)

### Option A: Page/Project Permission Synchronization

- Add a background sync job that reads Confluence space permissions or Jira project
  permissions via the API and maps them to user/group grants in Tomorrowland.
- Scope: Confluence space-level restrictions and Jira project-level access first; page-level
  ACL sync is a later extension.
- Must not override admin-configured source-grant denials.
- Must be gated by a feature flag (`feature.atlassian_permission_sync`), default disabled.

### Option B: Redirect Host Allowlist

- Add an explicit allowlist of permitted redirect hosts for Confluence attachment downloads
  and Jira attachment URLs.
- Allowlist is configurable via environment or admin config; defaults to the connector's
  configured base URL host only.
- Reject any redirect to a host not in the allowlist.

## Implementation Notes

- Do not replace the existing connector polling implementation.
- All changes must be narrowly scoped hardening follow-ups; no connector redesign.
- Prefer unit tests with mocked Atlassian API responses over live service tests.

## Validation

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src --strict
pytest tests/unit/test_confluence_connector.py -q
pytest tests/unit/test_jira_connector.py -q
```

## Acceptance Criteria

- If permission sync is implemented, synchronized grants follow the existing source-grant
  model and are gated by a disabled-by-default feature flag.
- If the redirect allowlist is implemented, connections to unlisted hosts are rejected with
  a logged error.
- No change to connector behavior for operators who do not enable optional hardening.
- Existing connector and permission tests remain green.
