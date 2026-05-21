# Tomorrowland Decisions

Shared record for durable architecture, product, and agent workflow decisions.

## 2026-05-21 — Virtualization uses react-window v2 with List + ARIA tables

Status: Active
Source: issue #450, PR #464

Decision:
- Use `react-window@2` for text/table virtualization. v2 API: `List` (not `FixedSizeList`), `rowCount`/`rowHeight`/`rowComponent` props, `rowProps={{}}` required.
- Virtualized TablePreview uses ARIA role-based table (`role="table"`, `role="rowgroup"`, etc.) instead of native `<table>` elements, because react-window renders flat `div` children.
- Always pass `rowProps={{}}` to `List` — v2 crashes with `Object.values(null)` if rowProps is undefined.

Impact:
- Non-virtualized TablePreview path (<1K rows) keeps native `<table>` for semantics.
- Virtualization threshold: 10K lines for TextPreview, 1K rows for TablePreview.
- Test setup must mock `ResizeObserver` globally (jsdom compat).

Next action:
- Consider browser-based virtualization verification (#451).

## 2026-05-21 — TextPreview is API-driven via docId prop

Status: Active
Source: issue #441, PR #455

Decision:
- `TextPreview` accepts an optional `docId` prop. When provided, it fetches full text from `GET /documents/{document_id}/text` in 10K chunks instead of using the `preview.snippet` field.
- The `text` prop is kept as an optional static fallback for backward compat and tests.
- `PreviewPane` passes `docId={preview.document_id}` for all text-based MIME dispatches.

Impact:
- New text-based renderers should follow the same `docId`-driven fetch pattern.
- Do not pass `text={preview.snippet}` to `TextPreview` from `PreviewPane` — that bypasses the full-text API.

Next action:
- When #443 adds a fidelity mode switcher, thread `translationVersionId` and `showOriginal` through PreviewPane → TextPreview.

## 2026-05-21 — Document viewer branching strategy

Status: Active
Source: docs/design/document-viewer-implementation-guardrails.md, issue #441

Decision:
- #440 targets `main` directly (security fix).
- #441–#451 target `feature/document-viewer` integration branch.
- #446 (Office conversion) should use a sub-branch `feature/document-viewer/office-conversion`.
- Git does not allow a branch named `feature/document-viewer/X` while `feature/document-viewer` also exists — use flat names like `feat/442-pdfjs-viewer` instead.

Impact:
- All document-viewer PRs must target `feature/document-viewer`, not `main`.
- Sub-branch naming: prefer `feat/<issue>-<short-name>` over path-style names.

Next action:
- Keep enforcing until the feature branch merges to `main`.

## 2026-05-21 — Document Chat: TanStack Query v5 message seeding pattern

Status: Active
Source: issue #473, `feature/document-chat`; ChatWindow.tsx

Decision:
- TanStack Query v5 removed `onSuccess`/`onError`/`onSettled` from `useQuery` options. Use `useEffect` instead.
- Chat message state is seeded once from the query result using a ref guard (`seededForSession = useRef<string | null>(null)`). The ref stores the last session ID for which messages were seeded.
- After seeding, messages are managed entirely in local React state to allow optimistic updates without query invalidation.
- Session change resets both input and the ref guard via a separate `useEffect` on `session.id`.
- `staleTime: 5 * 60_000` on the chat-session query prevents background refetch from overwriting locally-appended messages during an active chat.

Impact:
- Any future query-driven local state that allows offline mutations must follow this seed-once pattern.
- Never use `queryClient.setQueryData` to append optimistic chat messages — that would break the seed-once guard.

Next action:
- Phase C streaming changes should preserve the seed-once guard.

## 2026-05-21 — Document Chat: backend DELETE returns 200 JSON (not 204)

Status: Active
Source: issue #473, `src/services/api/routers/chat.py`

Decision:
- `DELETE /chat/sessions/{id}` returns `{"ok": true}` with HTTP 200, not 204 No Content.
- `deleteChatSession()` in `api/chat.ts` is typed as `Promise<{ ok: boolean }>`, not `Promise<void>`.
- This differs from the standard REST convention used by other delete endpoints in the codebase.

Impact:
- If the backend is ever normalized to 204, update `deleteChatSession` return type and callers.

## 2026-05-21 — Document Chat: dual-gate feature flag in tests

Status: Active
Source: issue #473, `tests/integration/test_chat_api.py`, `src/shared/feature_flags.py`

Decision:
- Every `/chat` route checks **two** guards: `Settings.feature_document_chat` AND `system_config.feature.document_chat` in the DB. Both must be `True` or every endpoint returns 404.
- The foundation migration seeds `feature.document_chat = False` in `system_config` (production safety default).
- Integration tests must override **both**: pass `feature_document_chat=True` to `Settings(...)` AND run `INSERT OR REPLACE INTO system_config (key, value) VALUES ('feature.document_chat', 'true')` in the test setup fixture.
- `.env` sets `FEATURE_MEILISEARCH_SEARCH=true`; `_settings()` helpers must explicitly override `feature_meilisearch_search=False` to prevent test workers attempting a Docker-DNS connection to `meilisearch:7700`.

Impact:
- Any new feature with a similar dual-gate pattern must be handled the same way in tests.
- Skipping either override produces 404 on every request — a confusing failure mode when the feature code itself is correct.

Next action:
- Document this pattern in `docs/context/chat.md` if a context file is created for Phase C.

## 2026-05-21 — Document Chat: typed UUID path params

Status: Active
Source: issue #473, `src/services/api/routers/chat.py`

Decision:
- Route handlers that accept a resource ID path param must type it as `UUID` (not `str`) in FastAPI.
- FastAPI validates the param on entry and returns 422 for malformed input; manual `UUID(hex=str_param)` would raise unhandled `ValueError` → 500.
- The pattern: `def get_session(session_id: UUID, ...)` with no manual conversion; pass `session_id` directly to repository methods that accept `UUID`.

Impact:
- All 4 chat route handlers (`get_session`, `update_session`, `delete_session`, `create_message`) follow this pattern.
- Apply the same pattern to any new route with a UUID path segment.

## 2026-05-20 — Repo memory is the durable record

Status: Active
Source: project manager chat summary

Decision:
- Store durable project memory in `docs/memory/*.md`.
- Use optional indexing only as a retrieval helper.
- Keep important decisions visible in normal code review.

Impact:
- Claude, OpenCode, and Codex should read relevant memory before substantial work.
- New durable decisions should be added here in compact form.

Next action:
- Keep this file short and update stale entries when decisions change.
