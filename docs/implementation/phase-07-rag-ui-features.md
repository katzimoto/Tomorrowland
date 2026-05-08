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
