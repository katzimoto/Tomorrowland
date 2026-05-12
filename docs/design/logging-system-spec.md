# Logging System Architecture And Event Taxonomy

## Goal

Tomorrowland logging should let operators and developers diagnose production
failures without exposing document content, user secrets, credentials, or high
cardinality business data. Logs are an operational support surface, not a user
analytics stream and not a substitute for audit records.

The core support flow is:

```text
User sees Error ID
        ↓
API response has X-Request-ID
        ↓
Backend logs contain request_id and safe context
        ↓
Admin/developer correlates logs with metrics, connector operation IDs, DLQ, or audit entries
```

This document coordinates the implementation of API error logs, user-facing
error IDs, authentication events, connector operation logs, and admin/audit
activity logs.

## Goals

- Emit structured JSON logs with a stable schema across API, connector,
  ingestion, search, translation, intelligence, and admin surfaces.
- Make each HTTP failure supportable with a `request_id` shown to users as an
  Error ID and echoed in `X-Request-ID`.
- Make longer workflows, especially connector validation and sync, supportable
  with an optional `operation_id`.
- Keep logs safe for internal operators by redacting secrets and excluding raw
  content by default.
- Keep log fields low-cardinality enough for local file logs, Docker logs, and
  future log aggregation.
- Clearly separate logs from metrics, DLQ records, audit log entries, and
  user-facing error messages.

## Non-goals

- Logs are not a data warehouse, search analytics backend, or behavioral
  analytics product.
- Logs must not contain raw documents, extracted chunks, prompts, search query
  text, raw request bodies, or connector credentials.
- Logs do not replace audit log tables for compliance-relevant admin actions.
- Logs do not replace Prometheus metrics for dashboards, alerting, or SLOs.
- Logs do not replace DLQ records for retryable ingestion failures.
- The first implementation does not require a SaaS collector or distributed
  tracing stack.

## Correlation model

### `request_id`

Every inbound HTTP request must have one request identifier:

- If the client sends `X-Request-ID`, accept it only after applying a safe format
  and length boundary.
- If absent or unsafe, generate a server-side UUID.
- Store the active request ID in request context so downstream service code can
  include it automatically.
- Echo the value in the `X-Request-ID` response header.
- For user-visible 5xx and major request failures, display the request ID as the
  Error ID.

The request ID must be present on all request-scoped log records, including
`http_request_completed`, `http_request_failed`, auth events, permission denials,
and admin action failures.

### `operation_id`

Longer workflows may span many log records inside one HTTP request or background
operation. These workflows should create an `operation_id`:

- Connector validation.
- Connector sync.
- Per-source ingestion workflows.
- DLQ retry workflows.
- Future background worker tasks.

`operation_id` is optional outside those workflows. When a workflow starts from
an HTTP route, logs should include both `request_id` and `operation_id`.

### Safe identifiers

Identifiers may be logged when they are stable and useful, but they must be
explicitly allowed. Prefer coarse and internal identifiers over names or paths:

- Safe: UUIDs for source, document, user, group, DLQ item, audit record, when
  needed for operator debugging.
- Safer for high-volume logs: counts, connector type, route template, HTTP
  method, status class, outcome.
- Avoid by default: human-readable source names, file names, absolute paths,
  document titles, group names, search text, and raw exception messages.

## JSON log record schema

All application logs should be rendered as one JSON object per line.

### Required base fields

| Field | Type | Requirement | Notes |
| --- | --- | --- | --- |
| `timestamp` | string | Always | RFC 3339 UTC timestamp. |
| `level` | string | Always | `debug`, `info`, `warning`, `error`, or `critical`. |
| `logger` | string | Always | Python logger name. |
| `message` | string | Always | Short safe event summary. |
| `component` | string | Always | `api`, `auth`, `admin`, `connector`, `pipeline`, `search`, `translation`, `intelligence`, `rag`, `metrics`, `worker`. |
| `outcome` | string | Always | `success`, `failure`, `skipped`, `denied`, `started`, `completed`, `retry`, or `dlq`. |
| `request_id` | string | HTTP context | Required when handling a request. |

### Recommended base fields

| Field | Type | Notes |
| --- | --- | --- |
| `event` | string | Event taxonomy value such as `http_request_completed`. |
| `environment` | string | Runtime environment when already available from settings. |
| `version` | string | Application version when already available from settings. |
| `commit` | string | Build commit when already available from settings. |

### Conditional HTTP fields

| Field | Type | Notes |
| --- | --- | --- |
| `route` | string | Route template, not raw path. Example: `/documents/{doc_id}`. |
| `method` | string | HTTP method. |
| `status_code` | number | Final response code. |
| `duration_ms` | number | Request duration in milliseconds. |

### Conditional error fields

| Field | Type | Notes |
| --- | --- | --- |
| `error_type` | string | Exception class name only. |
| `error_id` | string | Alias for user-facing request ID when displayed to users. Usually same as `request_id`. |
| `handled` | boolean | Whether the exception was converted to a controlled response. |

Do not log raw exception messages unless the caller has sanitized them first.
For connector and dependency failures, log a safe operator summary and the
exception class name.

### Conditional operation fields

| Field | Type | Notes |
| --- | --- | --- |
| `operation_id` | string | Workflow correlation ID. |
| `source_type` | string | Connector type such as `folder`, `nifi`, `confluence`, `jira`, or `smb`. |
| `source_id` | string | Internal UUID only when needed. |
| `dlq_item_id` | string | Internal DLQ UUID only when needed. |
| `document_id` | string | Internal document UUID only when needed; avoid in high-volume success logs. |

### Conditional admin fields

| Field | Type | Notes |
| --- | --- | --- |
| `action` | string | Stable admin action name. |
| `resource_type` | string | `source`, `user`, `group`, `permission`, `config`, `dlq`, etc. |
| `resource_id` | string | Internal UUID or key only when safe and useful. |
| `actor_user_id` | string | Internal user UUID when required for debugging; audit log remains the compliance source. |

### Conditional count fields

| Field | Type | Notes |
| --- | --- | --- |
| `discovered` | number | Items found by a connector or scan. |
| `indexed` | number | Items indexed successfully. |
| `skipped` | number | Items skipped intentionally. |
| `failed` | number | Items failed. |
| `retried` | number | Items retried. |

## Event taxonomy

Event names should be stable strings in the `event` field. Add new events only
when the field set, operational action, or alerting meaning is materially
different from an existing event.

| Event | Component | Level | Outcome | Required context |
| --- | --- | --- | --- | --- |
| `http_request_completed` | `api` | `info` | `success` or `failure` | `request_id`, `route`, `method`, `status_code`, `duration_ms` |
| `http_request_failed` | `api` | `error` | `failure` | `request_id`, `route`, `method`, `status_code`, `duration_ms`, `error_type` |
| `auth_login_succeeded` | `auth` | `info` | `success` | `request_id`, `provider` when safe |
| `auth_login_failed` | `auth` | `warning` | `failure` | `request_id`, `provider` when safe, failure reason category |
| `auth_signup_succeeded` | `auth` | `info` | `success` | `request_id` |
| `auth_signup_failed` | `auth` | `warning` | `failure` | `request_id`, failure reason category |
| `connector_validation_completed` | `connector` | `info` or `warning` | `success` or `failure` | `operation_id`, `source_type`, optional `source_id` |
| `connector_sync_started` | `connector` | `info` | `started` | `operation_id`, `source_type`, optional `source_id` |
| `connector_item_failed` | `connector` | `warning` | `failure` | `operation_id`, `source_type`, optional `document_id` or safe item identifier |
| `connector_item_skipped` | `connector` | `info` | `skipped` | `operation_id`, `source_type`, skip reason category |
| `connector_sync_completed` | `connector` | `info` or `warning` | `success` or `failure` | `operation_id`, `source_type`, counts |
| `dlq_item_created` | `pipeline` | `warning` | `dlq` | `request_id` or `operation_id`, `dlq_item_id`, reason category |
| `permission_denied` | `auth` | `warning` | `denied` | `request_id`, `resource_type`, action category |
| `admin_action_completed` | `admin` | `info` | `success` | `request_id`, `action`, `resource_type`, optional `resource_id` |
| `admin_action_failed` | `admin` | `warning` or `error` | `failure` | `request_id`, `action`, `resource_type`, `error_type` when applicable |

### Reason categories

Use stable reason categories instead of raw messages. Examples:

- `invalid_credentials`
- `missing_bearer_token`
- `expired_token`
- `invalid_token_claims`
- `permission_missing_group`
- `connector_validation_error`
- `connector_unavailable`
- `item_too_large`
- `unsupported_mime_type`
- `duplicate_document`
- `extract_failed`
- `translation_failed`
- `index_failed`
- `dependency_unavailable`
- `unexpected_error`

## Safe field registry

Allowed fields must remain explicit and reviewed. Prefer adding a new stable
field to overloading `message` with semi-structured data.

| Field family | Allowed examples | Disallowed examples |
| --- | --- | --- |
| Correlation | `request_id`, `operation_id`, `error_id` | Session tokens, JWTs, browser cookies |
| HTTP | `route`, `method`, `status_code`, `duration_ms` | Raw path with IDs or query strings, request body |
| Runtime | `component`, `logger`, `level`, `event`, `outcome` | Arbitrary user-provided labels |
| Error | `error_type`, `reason`, `handled` | Raw exception message unless sanitized |
| Source | `source_type`, safe `source_id` | Connector credentials, source display names, absolute paths by default |
| Document | Optional internal `document_id`, `mime_family` | Title, file contents, extracted text, chunks, prompts |
| Search | `mode`, `backend`, count summaries | Raw query text, result titles, snippets |
| Admin | `action`, `resource_type`, optional `resource_id` | Full config values, changed secrets, raw SQL values |
| Counts | `indexed`, `skipped`, `failed`, `discovered`, `retried` | Per-item content summaries |

## Redaction and safety rules

Logs must not contain:

- JWTs or session tokens.
- Passwords.
- Connector credentials.
- Raw request bodies.
- Raw document text.
- Extracted chunks.
- User search query text.
- Unsafe exception messages.
- SQL values.
- File contents.
- Unnecessary absolute source paths.

Additional rules:

- Prefer allowlists over denylist-only filtering.
- Redact known credential patterns before emitting dependency or connector
  errors.
- Never log `Authorization`, `Cookie`, or connector config values.
- Do not log prompt text or model responses when RAG or intelligence calls fail.
- Do not log Elasticsearch or Qdrant payloads if they may include document text.
- Treat traceback logging as development-only unless the traceback has passed the
  same redaction rules and excludes local paths that reveal sensitive source
  structure.
- Keep user-facing messages intentionally generic; put support correlation in
  the Error ID, not in detailed response text.

## User-facing error ID flow

When an unhandled server error or controlled 5xx occurs:

1. Middleware ensures the request has a `request_id`.
2. The response includes `X-Request-ID: <request_id>`.
3. The frontend displays a concise failure message that includes `Error ID:
   <request_id>`.
4. Backend logs for that request include the same `request_id` and safe fields
   such as route, method, status code, duration, component, event, outcome, and
   error type.
5. Operators search logs by `request_id` and then correlate to metrics,
   connector operation logs, DLQ entries, or audit log entries as needed.

Do not expose stack traces, SQL messages, dependency URLs with credentials, or
raw connector errors to the user.

## Admin/operator debugging workflow

### HTTP request failure

1. User reports the Error ID shown in the UI.
2. Operator searches logs for `request_id=<Error ID>`.
3. Operator checks `http_request_failed` for route, method, status code,
   duration, and `error_type`.
4. Operator checks related component logs with the same `request_id`.
5. Operator checks Prometheus metrics for route-level error rate or dependency
   health at the same time.

### Connector validation or sync failure

1. Admin sees a failed source validation or sync result.
2. UI or API response includes `request_id`; sync logs include `operation_id`.
3. Operator searches by `operation_id` for connector lifecycle events.
4. `connector_sync_completed` provides summary counts.
5. `connector_item_failed` or `dlq_item_created` points to safe reason categories
   and optional DLQ item IDs.
6. Operator uses DLQ or source status UI for retry/remediation.

### Admin action failure

1. Operator searches by `request_id` from the failed admin request.
2. Logs show `admin_action_failed` with safe action/resource fields.
3. Audit log records remain the authoritative timeline for who changed what.
4. Metrics show aggregate admin action outcome trends.

## Relationship to other observability data

### Logs

Logs answer: what happened in a specific request or operation?

They are event-oriented, correlated by `request_id` and `operation_id`, and
contain safe context for diagnosis.

### Metrics

Metrics answer: how often, how slow, and how healthy?

They use low-cardinality labels and power dashboards and alerts. Metrics should
not include identifiers, names, query text, document titles, or free-form error
messages.

### DLQ records

DLQ records answer: which ingestion items need retry or operator action?

DLQ records may store the minimum details required for retry and remediation.
Logs should link to DLQ records through safe IDs and reason categories instead
of duplicating full DLQ payloads.

### Audit log entries

Audit log entries answer: who performed an admin-relevant action, against which
resource, and when?

Audit records are durable product data. Logs may duplicate safe operational
summaries for support, but the database audit log remains the source of truth for
admin activity and compliance review.

### User-facing messages

User-facing messages answer: what should the user do now?

They must be concise, localized where appropriate, and safe. They should include
an Error ID for support correlation, not raw backend details.

## Validation and test expectations

Implementation PRs should include targeted tests for safety and correlation:

- JSON formatter tests verify required fields and valid JSON output.
- Request middleware tests verify `X-Request-ID` propagation and generated IDs.
- 500 handling tests verify user responses include a support-safe request ID.
- Logging leakage tests assert logs do not include JWTs, passwords, connector
  config values, raw request bodies, document text, chunks, search queries, SQL
  values, or raw unsafe exception messages.
- Auth event tests verify success/failure categories without logging submitted
  secrets.
- Connector tests verify `operation_id` propagation and summary counts without
  logging file contents or unnecessary absolute paths.
- Admin/audit alignment tests verify admin action logs and audit rows use the
  same action/resource taxonomy where applicable.
- Documentation checks should keep this taxonomy synchronized with shared schema
  code when the implementation lands.

## Implementation dependency map

### Logging core

- #178 logging system architecture and event taxonomy.
- #163 shared JSON formatter/schema foundation.
- #165 logging regression tests and leakage guards.

### API and user error correlation

- #164 API request and 500 error logs.
- #166 user-facing error messages with request IDs.

### Auth events

- #167 sign-in 401/session-expired bug.
- #174 local sign-up.
- #179 safe structured auth event logs.

### Connector operation logs

- #170 connector validation UX.
- #173 item-level connector failure isolation.
- #180 structured connector validation and sync operation logs.
- #171 connector sync/failure status UI.

### Admin and audit logs

- #172 connector edit/disable flows.
- #175 user/group membership UI.
- #176 source/group permission UI.
- #177 nested groups.
- #181 admin activity/audit structured log alignment.

## Rollout guidance

1. Land this design as the shared contract.
2. Implement a shared JSON formatter and schema helpers.
3. Add request middleware logs and 500 error correlation.
4. Add user-facing Error ID display in frontend/server responses.
5. Add leakage regression tests before expanding event coverage.
6. Add auth event logs.
7. Add connector validation/sync operation logs.
8. Align admin action logs with database audit records.

Each step should remain useful independently and must preserve the redaction
rules in this document.
