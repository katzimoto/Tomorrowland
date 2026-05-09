# Phase 07: RAG And UI Features

## Goal

Implement user-facing intelligence workflows.

## Scope

- `/qa` endpoint and RAG service.
- Citation response model.
- Q&A UI.
- Document comment APIs and UI.
- Annotation APIs and UI.
- Subscriptions and notifications.
- Alert matching (deferred from Phase 06 — requires subscriptions table).
- Related documents.
- Expertise map.

Detailed document comment plan:

- `docs/implementation/document-comments-plan.md`

## Validation

- RAG retrieval permission tests.
- Feature flag enabled/disabled tests.
- UI workflow tests for Q&A, comments, annotations, subscriptions, and
  notifications.

## Decision Gates

- **Annotation retention:** delete cascade says annotations are marked
  `doc_deleted: true`, but the annotation schema does not include that column.
  - **Resolved for Phase 07:** annotations table includes `doc_id` (FK to
    documents with `ON DELETE CASCADE`). When a document is soft-deleted
    (`status = 'deleted'`), annotations remain in place for audit purposes.
    Hard delete cascades through FK. No `doc_deleted` column needed.
- **Preview positions:** annotation `position` is preview-mode dependent.
  - **Resolved for Phase 07:** position is a JSON object with shape determined
    by preview mode. Phase 05a defines preview modes: `text` (char offset),
    `html` (XPath + offset), `pdf` (page + bbox). Annotation UI uses the
    same preview mode as the document's MIME type.

## Acceptance Criteria

- Q&A answers cite accessible source chunks only.
- Feature-flagged routes and UI surfaces hide or disable correctly.
- Document comments are visible only to users with document access.
- Comment creators and admins can edit/delete according to policy.
- Annotation and notification workflows persist and render expected state.

## Phase 07d Backend Slice

Subscriptions and notifications are implemented as a backend-only slice:

- `alert_subscriptions` stores user-owned topic rules with a query, threshold,
  enabled state, timestamps, and last notification time.
- `alert_notifications` stores per-user document matches and cascades with
  subscription, user, and document deletion.
- `GET|POST /subscriptions`, `PUT|DELETE /subscriptions/{id}` manage only the
  authenticated user's subscriptions.
- `GET /notifications` returns unread notifications by default, and
  `PUT /notifications/{id}/read` marks a user's own notification read.
- `AlertMatcher` compares document text and subscription queries with the
  project `MockEncoder`, filters candidates through source permissions, and
  de-duplicates subscription/document notifications.
- Alert matching runs best-effort during folder ingestion when
  `alerts.check_on_ingest` is enabled.
- `POST /admin/alerts/{doc_id}/trigger` lets admins match one indexed document
  on demand.

## Phase 07e Backend Slice

Related documents and the expertise map are implemented as a backend-only slice:

- `GET /documents/{doc_id}/related` returns permission-filtered related
  documents for a source document.
- Related documents use existing Qdrant chunk vectors and the authenticated
  user's group IDs, exclude the source document, deduplicate by `doc_id`, and
  respect `system_config.search.related_docs_limit`.
- `GET /expertise?topic=<query>` returns neutral user evidence for a topic.
- Expertise scoring uses weighted, transparent signals from views, comments,
  shared annotations, and enabled subscriptions on topic-matching accessible
  documents.
- Expertise evidence includes only accessible document metadata and aggregate
  counts. Private annotation text and comment text are never returned.
- `feature.related_docs` and `feature.expertise_map` are enforced from both
  runtime settings and `system_config`.
