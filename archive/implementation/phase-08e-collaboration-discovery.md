# Phase 08e: Collaboration And Discovery

## Prerequisites

1. Phase 08c review gate passed (authenticated shell and `/search` route
   exist).
2. `frontend/src/features/documents/insightPaneTabs.ts` committed by the 08d
   agent. The agreed tab type is:
   ```typescript
   export type InsightPaneTab =
     | "summary" | "qa" | "related"      // owned by 08d
     | "comments" | "annotations" | "subscriptions"; // owned by this phase
   ```
   Once 08d commits this file, this phase can begin without waiting for 08d to
   complete the rest of its scope.

This phase can run in parallel with Phase 08d once the two prerequisites above
are met.

## Branch

`developer/phase-08e-collaboration-discovery`

## Stack

React 19 + TypeScript + Vite + TanStack Router + TanStack Query + React Hook
Form + Zod + CSS modules. See `docs/implementation/phase-08b-frontend-ui.md` Chosen
Stack section for constraints. Do not introduce additional frameworks.

## API Availability

All endpoints required by this phase are available from the backend. No mock
adapters are needed. See `docs/implementation/phase-08b-frontend-ui.md` API
Availability Map for the full table.

Endpoints used in this phase:
- `GET /documents/{documant_id}/comments`
- `POST /documents/{documant_id}/comments`
- `PATCH /documents/{documant_id}/comments/{comment_id}`
- `DELETE /documents/{documant_id}/comments/{comment_id}`
- `GET /documents/{documant_id}/annotations`
- `POST /documents/{documant_id}/annotations`
- `PUT /annotations/{annotation_id}`
- `DELETE /annotations/{annotation_id}`
- `GET /subscriptions`
- `POST /subscriptions`
- `PUT /subscriptions/{id}`
- `DELETE /subscriptions/{id}`
- `GET /notifications`
- `PUT /notifications/{id}/read`
- `GET /me/activity`
- `GET /expertise`

## Auth UX Contract

Follow the Auth UX Contract in `docs/implementation/phase-08b-frontend-ui.md`
precisely. `403` responses render a permission state without leaking source
names, hidden counts, or document titles.

## Scope — UI Phase 04: Document Comments And Annotations

These components populate the `comments` and `annotations` tabs in
`InsightPane.tsx` (owned by 08d). Render them as the tab body when
`InsightPane` is present; they also work as standalone panel components.

### Comments (`src/features/comments/`)

- `CommentList.tsx` — fetches `GET /documents/{documant_id}/comments` via TanStack
  Query. Renders `CommentItem` list with `CommentComposer` at the bottom.
  Handles loading (skeleton), empty ("No comments yet"), error, and
  feature-disabled states.
- `CommentComposer.tsx` — multiline textarea supporting long text, line breaks,
  and emoji. Submit creates via `POST /documents/{documant_id}/comments`. Draft is
  preserved in component state.
- `CommentItem.tsx` — displays author, timestamp, body text. Collapses long
  comments with expand toggle. Shows edit/delete actions for the comment
  creator and for admins. Read-only for other users.
- `CommentEditForm.tsx` — inline edit form replacing the comment body on edit.
  Submits via `PATCH /documents/{documant_id}/comments/{comment_id}`.
- Tests: `CommentList.test.tsx`, `CommentComposer.test.tsx`,
  `CommentItem.test.tsx`.

Create `src/api/comments.ts`:
- `listComments(docId, params?)` — pagination, sort.
- `createComment(docId, body)`.
- `updateComment(docId, commentId, body)`.
- `deleteComment(docId, commentId)`.

### Annotations (`src/features/annotations/`)

- `AnnotationList.tsx` — fetches `GET /documents/{documant_id}/annotations`. Lists
  `AnnotationItem` components. Handles loading, empty, and error states.
- `AnnotationEditor.tsx` — create/edit form with body field and private/shared
  toggle via React Hook Form + Zod. Submits `POST` or `PUT`.
- `AnnotationItem.tsx` — displays body, position label (from `position` JSON),
  `PrivacyLabel`, and edit/delete actions (creator and admin only).
- `PrivacyLabel.tsx` — badge showing "Private note" or "Shared with readers".
- Tests: `AnnotationList.test.tsx`, `AnnotationEditor.test.tsx`,
  `AnnotationItem.test.tsx`.

Create `src/api/annotations.ts`:
- `listAnnotations(docId)`.
- `createAnnotation(docId, payload)`.
- `updateAnnotation(annotationId, payload)`.
- `deleteAnnotation(annotationId)`.

## Scope — UI Phase 05: Subscriptions, Notifications, And History

Replace `PlaceholderPage` stubs in `src/app/routes.tsx` for `/subscriptions`,
`/notifications`, and `/history`.

### Subscriptions (`src/features/subscriptions/`)

- `SubscriptionsPage.tsx` — lists subscriptions from `GET /subscriptions`.
  Create/edit/delete flows inline or via dialog. Shows saved searches alongside
  subscriptions with a visual distinction.
- `SubscriptionForm.tsx` — React Hook Form + Zod form with query, threshold,
  and enabled toggle fields. Submits `POST /subscriptions` or
  `PUT /subscriptions/{id}`.
- `SavedSearchToSubscription.tsx` — flow to convert a saved search (from
  `SavedSearches.ts` in the `search` feature) into a subscription. Pre-fills
  `SubscriptionForm` with the saved query.
- Tests: `SubscriptionsPage.test.tsx`, `SubscriptionForm.test.tsx`.

Create `src/api/subscriptions.ts`:
- `listSubscriptions()`.
- `createSubscription(payload)`.
- `updateSubscription(id, payload)`.
- `deleteSubscription(id)`.

### Notifications (`src/features/notifications/`)

- `NotificationsPage.tsx` — fetches `GET /notifications`. Lists
  `NotificationItem` components. Groups unread at the top.
- `NotificationItem.tsx` — unread/read state, notification body, action link
  to the related document. Marks read via `PUT /notifications/{id}/read` on
  click.
- Wire unread notification count into `AppLayout.tsx`: replace the hardcoded
  `unreadCount={0}` prop passed to `NavRail` with a live count from a
  background TanStack Query fetch of `GET /notifications` (count of unread
  items). Poll interval: 60 seconds is acceptable for MVP.
- Tests: `NotificationsPage.test.tsx`, `NotificationItem.test.tsx`.

Create `src/api/notifications.ts`:
- `listNotifications()`.
- `markNotificationRead(id)`.

### History (`src/features/history/`)

- `HistoryPage.tsx` — recent activity from `GET /me/activity` merged with
  recent searches from `SavedSearches.ts` browser storage. Sections: recently
  viewed documents, recent searches.
- `HistoryRow.tsx` — row component for each history entry type with icon,
  label, timestamp, and action link.
- Include a brief privacy help note: "Activity visible only to you and admins."
- Tests: `HistoryPage.test.tsx`.

Create `src/api/history.ts`:
- `getActivity(params?)` — `GET /me/activity`.

## Scope — UI Phase 06: Expertise Map And Power-User Polish

### Expertise Map (`src/features/expertise/`)

Add `/expertise` route to `src/app/routes.tsx` (this route does not exist yet;
this phase adds it and the NavRail link).

- `ExpertisePage.tsx` — topic input and results list. Uses `GET /expertise?topic=<query>`.
- `ExpertiseResultList.tsx` — list of `ExpertiseResult` items.
- `ExpertiseResult.tsx` — user identifier, evidence list (accessed documents,
  comments, shared annotations, subscriptions). Neutral language: "evidence,
  not ranking." Does not look like a leaderboard or ranking table.
- Tests: `ExpertisePage.test.tsx`, `ExpertiseResult.test.tsx`.

Create `src/api/expertise.ts`:
- `queryExpertise(topic)` — `GET /expertise?topic=<topic>`.

### Command Menu

- `src/components/feedback/CommandMenu.tsx` — modal triggered by
  `Cmd+K`/`Ctrl+K`. Lists navigation shortcuts: go to Search, Q&A,
  Subscriptions, History, Expertise. Filters by typed query.
- Does not replace visible navigation.
- Test: `CommandMenu.test.tsx`.

### Final Visual Polish Pass

- Screenshot regression sweep for all major routes at all four viewports.
  Compare against Phase 08d baseline screenshots if available.
- Accessibility regression sweep: run axe checks on every route introduced in
  this phase plus the routes from 08b.
- Fix any clipping, overlap, or focus-visibility issues surfaced by the sweep.

## Do Not Start Criteria

Do not begin this phase if:

- Required backend endpoints are ambiguous and no disabled-state plan exists.
- Phase 08c has unresolved Reviewer blockers.
- The route would require revealing inaccessible document metadata.
- The feature depends on a backend phase that has not defined a stable response
  contract.

## New Files

```
frontend/src/features/comments/
  CommentList.tsx + .test.tsx
  CommentComposer.tsx + .test.tsx
  CommentItem.tsx + .test.tsx
  CommentEditForm.tsx
frontend/src/features/annotations/
  AnnotationList.tsx + .test.tsx
  AnnotationEditor.tsx + .test.tsx
  AnnotationItem.tsx + .test.tsx
  PrivacyLabel.tsx
frontend/src/features/subscriptions/
  SubscriptionsPage.tsx + .module.css + .test.tsx
  SubscriptionForm.tsx + .test.tsx
  SavedSearchToSubscription.tsx
frontend/src/features/notifications/
  NotificationsPage.tsx + .module.css + .test.tsx
  NotificationItem.tsx + .test.tsx
frontend/src/features/history/
  HistoryPage.tsx + .module.css + .test.tsx
  HistoryRow.tsx + .test.tsx
frontend/src/features/expertise/
  ExpertisePage.tsx + .module.css + .test.tsx
  ExpertiseResultList.tsx
  ExpertiseResult.tsx + .test.tsx
frontend/src/components/feedback/CommandMenu.tsx + .test.tsx
frontend/src/api/comments.ts
frontend/src/api/annotations.ts
frontend/src/api/subscriptions.ts
frontend/src/api/notifications.ts
frontend/src/api/history.ts
frontend/src/api/expertise.ts
frontend/tests/e2e/comments.spec.ts
frontend/tests/e2e/subscriptions.spec.ts
frontend/tests/e2e/notifications.spec.ts
frontend/tests/e2e/expertise.spec.ts
```

## Modified Files

```
frontend/src/app/routes.tsx       — replace subscriptionsRoute, notificationsRoute, historyRoute components;
                                    add expertiseRoute
frontend/src/app/AppLayout.tsx    — wire live unread notification count into NavRail unreadCount prop
```

## Validation

```bash
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

Playwright workflows required:

- Create a comment on a document; edit own comment; delete own comment.
- Admin affordances render on another user's comment.
- Keyboard-only: create, edit, delete a comment.
- Create a private annotation; create a shared annotation; edit; delete.
- Private annotation shows "Private note" label; shared shows "Shared with
  readers".
- Shared annotation is not shown to a user without document access.
- Create a subscription; read a notification; open document from notification.
- Unread count in shell decrements after marking notification read.
- History page shows recently viewed documents.
- Expertise search returns evidence rows (neutral language, not a leaderboard).
- Command menu opens with `Cmd+K`, filters by typed query, and navigates.
- Full screenshot regression sweep at all four viewports: 320×720, 768×1024,
  1024×768, 1440×900.
- Accessibility sweep for all routes introduced in this phase.

## Review Artifacts

Each PR must include (see `docs/implementation/phase-08b-frontend-ui.md` Review
Artifacts Per UI PR for the full checklist):

- Screenshots or Playwright trace links at all four viewports.
- Keyboard navigation notes.
- Accessibility check results (this phase's sweep covers all major routes).
- Viewport validation notes.
- Visual regression results versus Phase 08d baseline.
- API contract notes.
- Auth/session behavior notes.

## Acceptance Criteria

- Comments are visible to all users with document access; hidden from users
  without access.
- Comment creators and admins can edit/delete; other users cannot.
- Long comments do not take over the insight pane.
- Private annotations are clearly labelled.
- Shared annotations do not appear for users without document access.
- Comment and annotation actions are keyboard accessible.
- Saved searches and subscriptions are visually distinct.
- Notification unread count is visible in the shell after landing.
- History states explain privacy without cluttering the page.
- Expertise map does not look like a leaderboard.
- Command menu does not replace visible navigation.
- All major routes pass responsive screenshot checks.

Stop for Reviewer-agent review.
