# Phase 09: Optional Integrations And Legacy Format Support

## Goal

Add remaining optional integrations and legacy document support after the Phase 08 production
Compose + UI milestone. Phase 09 is split into three independent sub-plans; each can be
developed and reviewed on its own branch.

## Sub-Plans

| Sub-Phase | Plan | Purpose |
|---|---|---|
| 09a | `phase-09a-nifi-integration.md` | NiFi event integration and Kafka consumer wiring |
| 09b | `phase-09b-legacy-office-extraction.md` | `.doc`, `.xls`, `.ppt` binary extraction |
| 09c | `phase-09c-atlassian-hardening.md` | Optional Atlassian permission sync and redirect hardening |

## Current Atlassian Baseline

`ConfluenceConnector` and `JiraConnector` are registered source connectors. They validate
Server/Data Center base URLs, reject Atlassian Cloud hosts, poll pages/issues, normalize
content, and download attachments. Imported Atlassian documents use the same source-grant
permission model as folder-ingested documents. Page/project permission synchronization is
not implemented.

## Cross-Phase Rules

- All imported documents must be tied to an admin-configured ingestion source and governed
  by the source-grant access model.
- Integration failures must route through the existing DLQ operational path.
- Do not replace the existing Confluence/Jira polling connectors unless a change is a
  narrowly scoped hardening follow-up.
- Resolve Decision Gates in each sub-plan via `docs/review/spec-gaps.md` before coding.
