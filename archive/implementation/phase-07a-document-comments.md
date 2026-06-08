# Document Comments Implementation Plan

## Goal

Implement shared document-level comments that are visible to every user with
document access, editable/deletable by the creator, and editable/deletable by
admins.

Design source: `docs/design/document-comments-spec.md`.

## Phase Placement

Recommended branch: `developer/phase-07a-document-comments`

Implement after the core Phase 07 permission and user-facing collaboration
foundation is available. This should be a separate PR from annotations unless
the Reviewer approves combining them.

Frontend implementation belongs in `developer/ui-04-comments-annotations`, as
described in `docs/implementation/phase-08b-frontend-ui.md`.

## Dependencies

- Phase 02 auth and admin guards.
- Phase 03e document preview and permission checks.
- Phase 04 audit logging.
- Phase 07 feature flag plumbing for collaboration surfaces.

## Backend Scope

### Feature Flag

Add `feature.document_comments`, default `true` for development and enabled
deployments.

When disabled:

- Comment endpoints return 404 or a feature-disabled response consistent with
  existing feature-gated endpoints.
- The frontend hides the `Comments` tab or shows a disabled state.

### Data Model

Add a `document_comments` table:

```sql
CREATE TABLE document_comments (
    id UUID PRIMARY KEY,
    documant_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    author_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    body TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    edited_at TIMESTAMP WITH TIME ZONE NULL,
    edited_by_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
    deleted_at TIMESTAMP WITH TIME ZONE NULL,
    deleted_by_id UUID NULL REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX ix_document_comments_doc_id_created_at
    ON document_comments (documant_id, created_at DESC);
CREATE INDEX ix_document_comments_author_id
    ON document_comments (author_id);
```

Behavior:

- Use soft delete for user-visible deletion.
- Normal list endpoints exclude deleted comments.
- Admin audit views may include deletion metadata.
- Store long bodies in `TEXT`. Do not add a short product character limit.
- Enforce only a configurable abuse/safety byte limit at the API boundary.

### Service Layer

Add a document comments service/repository:

- `list_comments(documant_id, current_user, sort)`
- `create_comment(documant_id, body, current_user)`
- `update_comment(comment_id, body, current_user)`
- `delete_comment(comment_id, current_user)`
- `can_edit_comment(comment, current_user)`
- `can_delete_comment(comment, current_user)`

Every method must:

- Check document access through the existing permission enforcer.
- Avoid revealing whether inaccessible documents or comments exist.
- Compute `can_edit` and `can_delete` server-side.
- Emit audit entries for admin edits/deletes.

### API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/documents/{documant_id}/comments` | Document access | List visible comments |
| POST | `/documents/{documant_id}/comments` | Document access | Create shared comment |
| PATCH | `/documents/{documant_id}/comments/{comment_id}` | Creator or admin | Edit comment |
| DELETE | `/documents/{documant_id}/comments/{comment_id}` | Creator or admin | Soft-delete comment |

Request/response contracts are defined in
`docs/design/document-comments-spec.md`.

### API Behavior

List:

- Sort by newest first by default.
- Support `sort=newest|oldest`.
- Return `total_count` for visible non-deleted comments only.
- Return `can_comment` based on document access and feature flag.

Create:

- Trim only leading/trailing whitespace for emptiness checks.
- Preserve internal whitespace, line breaks, and emoji.
- Reject empty bodies.
- Return the created comment with permissions.

Update:

- Creator or admin only.
- Preserve body formatting.
- Set `edited_at` and `edited_by_id`.
- Admin edits someone else's comment should be auditable.

Delete:

- Creator or admin only.
- Set `deleted_at` and `deleted_by_id`.
- Return 204 or a normalized deleted response.
- Admin deletes someone else's comment should be auditable.

## Frontend Scope

Implement in UI Phase 04:

- Add `Comments` tab to document insight pane.
- Add composer with multiline text, long comment support, and emoji support.
- Add comment thread with newest/oldest sort.
- Add collapse/expand for long comments.
- Add creator/admin edit/delete actions.
- Preserve drafts across tab changes and failed requests.
- Add empty, loading, error, permission, and read-only states.

## Validation

### Unit Tests

- Comment permission helpers:
  - creator can edit/delete own comment.
  - admin can edit/delete any comment.
  - other users cannot edit/delete.
- Body validation preserves line breaks and emoji.
- Soft delete hides comments from normal lists.
- `can_edit` and `can_delete` are computed correctly.

### Migration Tests

- `document_comments` table and indexes are created.
- FK to `documents` cascades on hard delete.
- Long body text can be persisted.
- Deleted comments remain stored with deletion metadata.

### API Tests

- User with document access can list and create comments.
- User without document access gets the same safe response style as preview
  access failures.
- Creator can edit/delete.
- Admin can edit/delete another user's comment.
- Non-creator cannot edit/delete another user's comment.
- Deleted comments do not appear in the normal list.
- Admin edit/delete produces audit entries.

### UI Tests

- Create text-only, emoji-only, and long comments.
- Expand/collapse long comments.
- Edit own comment and preserve failed draft.
- Delete own comment with confirmation.
- Admin affordances render for other-user comments.
- Keyboard-only create/edit/delete flow works.

## Acceptance Criteria

- Comments are visible to all users with document access.
- Comments are hidden from users without document access.
- No private document comments exist in this feature.
- Creators and admins can edit/delete according to policy.
- Admin edits/deletes are audit logged.
- Long comments and emoji are supported.
- UI keeps document preview context while reading or writing comments.
- Tests cover permissions, deletion, errors, and accessibility.

Stop after opening the PR for Reviewer-agent review.
