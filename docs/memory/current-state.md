# Tomorrowland Current State

Canonical shared memory for active project state. Keep this file compact and factual.

## 2026-05-23 — Chat defaults + Qdrant bootstrap + SSE fix + Edit Source page

Status: Done
Source: OpenCode session (chat summary)

Finding:
- Chat feature flags (`feature_document_chat*`) now default to True in `src/shared/config.py`.
- Qdrant collection now auto-created on first search (not just on upsert), fixing "Collection doesn't exist" error.
- SSE streaming endpoint fixed: manual connection management replaces `with engine.begin()` so connection stays alive during streaming generator.
- `/qa` removed from nav rail and routes; chat replaces it.
- Admin Edit Source page created at `/admin/sources/$sourceId/edit` with full form (name, language, connector fields, path, enabled, schedule).
- Cron schedule field added: migration (`schedule TEXT`), backend schema + routes, frontend types + edit form + detail display.
- Node.js default bumped to v22 (was v20.9.0) to fix vitest/ESLint `styleText` compat.

Impact:
- Chat works out-of-box. Qdrant auto-creates collections. SSE streaming persists messages.
- Sources have edit page + cron schedule + document pipeline view + delete.
- All Python tooling uses `uv` (fast resolution, reproducible lockfile).
- Mistral fits in Ollama container. Documents can be requeued/deleted from admin UI.
- Related documents show structured reasons (semantic, entities, tags, source).
- Boolean-integer SQL bugs fixed (4 instances); lint script + PostgreSQL CI job prevent recurrence.

Next action:
- None. All tasks from this session complete.

## 2026-05-22 — Document details & advanced search track complete (#483–#489)

Status: Done — all 7 issues implemented
Source: PRs #493–#499; plan at `docs/implementation/document-details-and-search.md`

Finding:
- All 7 issues in the track complete:
  - #485 Markdown preview
  - #486 User-managed private/public document tags
  - #487 Comments unified into annotations with threaded replies
  - #488 Document relationships table + pipeline wiring
  - #483 Expanded details panel with grouped collapsible sections
  - #484 Advanced search filter pipeline + URL-driven filter state
  - #489 Clickable detail values linking to pre-populated search
- Integration PR merged; feature branch `feature/document-details-and-search` → `main` complete.

## 2026-05-22 — Document viewer MVP complete (#453 closed)

Status: Done
Source: issues #440–#451; PRs #454–#465; integration PR #466 merged to `main`

Finding:
- All 12 document viewer child issues implemented and merged to `main` via PR #466.
- Parent issue #453 closed. All child issues (440-451) closed.

## 2026-05-21 — Resource safety guards (#463)

Status: Done
Source: issue #463; PR #467

Finding:
- Added Compose resource limits (cpus, mem_limit, mem_reservation, pids_limit) to 9 services: api, pipeline-worker, vector-worker, ollama, libretranslate, elasticsearch, qdrant, meilisearch, postgres — all via env vars.
- Ollama safety defaults: OLLAMA_CONTEXT_LENGTH=2048, OLLAMA_MAX_LOADED_MODELS=1, OLLAMA_NUM_PARALLEL=1, OLLAMA_MAX_QUEUE=8, OLLAMA_KEEP_ALIVE=1m.
- Workers already process one job per loop iteration (built-in backpressure); no Python code changes needed.
- Docs: Resource Safety Guards section in production-compose.md with per-RAM-tier guidance, capacity warning, overload response procedure.
- Baseline total: ~15 GB memory limit, ~4 GB reservation for all services at 1 replica.
- Merged to main via PR #467.

## 2026-05-21 — Python dependency audit fix

Status: Done
Source: Security CI failure on PR #466

Finding:
- pip-audit found PYSEC-2025-183 in pyjwt 2.12.1 (no fix version available).
- pip CVEs (CVE-2025-8869, CVE-2026-1703, CVE-2026-3219, CVE-2026-6357) are infrastructure-only — CI runner already has pip 26.1.1.
- Fix: added `--ignore-vuln PYSEC-2025-183` to pip-audit command in security.yml.

## 2026-05-22 — Vector embedding context-length safety (#468)

Status: Done
Source: issue #468; commit 30bc196 merged to `main`

Finding:
- `chunk_text()` accepts `max_tokens` param; oversized chunks split via token-estimate heuristic (chars/4).
- OllamaEmbeddingEncoder validates text token count before API call, catches 400 as ValueError.
- ValueError dead-letters immediately in vector_worker (permanent error).
- PipelineWorker threads `embedding_max_tokens` to chunking calls.
- New config: `EMBEDDING_MAX_TOKENS` (default 1024).
- Verified: ruff check, ruff format, mypy (strict) — all clean.
- Tests: 19 chunking + 32 encoder/worker tests pass.

Impact:
- Oversized chunks are recursively split before reaching the encoder.
- Encoder validates each text's estimated token count before API call.
- ValueError (context-length exceeded) dead-letters immediately instead of retrying 5 times.

## 2026-05-22 — Document Chat Phase C frontend complete (#474)

Status: Done
Source: issue #474; commits d352ed2 + 8fa4f95 on `feature/document-chat`

Finding:
- ScopeBadge, ScopeSelector, DocumentChatPanel, InsightPane Chat tab migration complete.
- `single_document` scope auto-created via DocumentChatPanel; `all_accessible_documents` switchable via ScopeSelector.
- Document Page InsightPane's "QA" tab replaced with "Chat" tab using DocumentChatPanel.
- `feature.document_chat` removed from SYSTEM_CONFIG_DEFAULTS (env-var is correct gate).
- Sidebar, message list, citations, empty/loading/error states all tested.

Next action:
- Verify CI on `feature/document-chat`; open PR targeting `main`.

## 2026-05-22 — In-document search fix verified + closed (#469)

Status: Done
Source: issue #469; commit 2927a50 on `main`

Finding:
- Fix commit 2927a50 covers all 7 renderers: PreviewPane passes search props to DOCX/RTF TextPreview, TablePreview, ArchivePreview, EmailPreview, SlidesPreview, PdfViewer, CodeViewer.
- PdfViewer: per-page text extraction + page-jump navigation via activeSearchIndex.
- TextPreview virtualized: per-line cumulative match offsets for correct global active-match navigation.
- Missing tests added (commit 48153a9): 8 test files covering all AC #5 criteria — PreviewPane prop routing, PdfViewer page nav, virtualized global index, DocumentPage Ctrl+F toggle, EmailPreview/SlidesPreview/ArchivePreview/TablePreview search.
- TypeScript check clean. Issue closed.

## 2026-05-22 — Document Chat Phase D — query rewrite (#475)

Status: Done
Source: issue #475; design §9

Finding:
- D1: `rewrite_query()` — `src/services/chat/message_service.py`. Handles
  history window (last 4 user+assistant pairs), skip on first turn, fallback on Ollama error.
- D2: Wired into router — `POST /chat/sessions/{id}/messages` loads prior messages,
  calls `rewrite_query` when `FEATURE_DOCUMENT_CHAT_QUERY_REWRITE=true`, passes
  `rewritten_query` to the persisted assistant message.
- D3: 6 unit tests covering all rewrite behaviors.
- D4: Admin debug panel — collapsed `<details>` block in assistant message bubble
  shows `rewritten_query` when present. 6 component tests.
- Bugfix: `rag.answer(question=body.content)` → `question=question` (used raw
  input instead of possibly-rewritten query).
- Feature flag: `FEATURE_DOCUMENT_CHAT_QUERY_REWRITE` (default `false`).
- Verified: ruff, ruff format, mypy strict — clean. 44 unit + 28 frontend tests pass.
- Issue #475 closed.

Next action:
- Phase E (#476): retrieval quality (hybrid, metadata, translations, reranker).

## 2026-05-22 — Document Chat Phase F — Citation UX (#477)

Status: Done
Source: issue #477; commits on `feature/document-chat`

Finding:
- F1: `page_number`, `section_heading`, `language`, `translated_from` in backend Citation model, Qdrant/Meili metadata, router response.
- F2: `ChatCitationCard` displays `p. N · Section Name` when present.
- F3: Citation `<Link>` includes `?page=N&chunk=M`, opens in new tab.
- F4: `DocumentPage` reads `?page=N` search param via `useSearch`, `scrollIntoView` on mount.
- F5: "Translated from [language]" italic indicator on translated citations.
- 7 new `ChatCitationCard.test.tsx` tests.
- Verified: 423 frontend + 124 backend tests pass.

## 2026-05-22 — Document Chat Phase G — Streaming and polish

Status: Done
Source: Phase G table in document-chat-design.md; commits on `feature/document-chat`

Finding:
- G1: SSE streaming endpoint `POST /chat/sessions/{id}/messages/stream` — Ollama streaming via `generate_stream()`, `RagService.answer_stream()` yielding `(event, data)` tuples, `StreamingResponse` SSE formatting. Behind `FEATURE_DOCUMENT_CHAT_STREAMING` flag.
- G2: Frontend streaming UI — `sendChatMessageStream()` SSE reader in `api/chat.ts`, phase indicators ("Searching"/"Reading sources"/"Generating") in `ChatInput`, incremental message rendering in `ChatWindow`.
- G3: `StarterQuestions` component — scope-aware question suggestions when session is empty.
- G5: `autoFocus` on `ChatInput` when session loads, `aria-busy` on `MessageList` during streaming, 6 `StarterQuestions` tests.
- G4: Grafana panel — human task, not yet started.
- Verified: 429 frontend tests (61 files), 44 backend chat unit tests, `tsc --noEmit` clean.

## 2026-05-22 — Document Chat merged to main (#492)

Status: Done
Source: PR #492; commit e299390 on `main`

Finding:
- `feature/document-chat` branch merged to `main` via squash commit e299390.
- All prior issues (#473–#477) closed.
- Final CI: Frontend CI, Container CI, Docs CI all green. 429 frontend tests, 44 backend chat unit tests. `npm run build` passes. `npm run lint`: 0 errors. `npm run typecheck`: clean. `ruff check` clean, `mypy --strict` clean.
- Feature branch deleted. All automated phases complete.

## 2026-05-22 — Sign-out button added to NavRail (#490)

Status: Done
Source: Issue #490; commit 2a239ae

Finding:
- User identity (display_name + email) and Sign out button added to NavRail sidebar bottom section.
- `NavRail` receives `userDisplayName`/`userEmail` from `AppLayout` → `AppShell`.
- Clicking Sign out calls existing `logout()` (API + token clear), clears TanStack Query cache via `queryClient.clear()`, navigates to `/login`.
- Button disabled during sign-out. User info hidden on mobile (same as other bottom items).
- 6 new NavRail tests cover: nav items, admin item, user info, sign-out button, click behavior, disabled state.
- Verified: 62 test files / 435 tests pass, `tsc --noEmit` clean, `npm run lint` 0 errors.

## 2026-05-22 — Admin Users UI (#491)

Status: Done
Source: Issue #491; commit a5c56b6

Finding:
- Backend: PATCH /admin/users/{user_id} with UpdateUserRequest (display_name, is_admin). Last-admin guard prevents removing admin from the sole admin.
- Frontend: AdminUsersPage with user table (email, display_name, admin badge, auth source). AdminUserDetailPage with editable display_name, is_admin toggle, group membership list.
- AdminHubPage: added Users card linking to AdminUsersPage.
- Integration tests: 51 passing (5 new for PATCH — last-admin, role change, display name, bad user_id, invalid payload).
- Unit tests: 34 passing (6 AdminUsersPage + 6 AdminUserDetailPage).
- Verified: ruff check, ruff format, mypy --strict, npm run lint (0 errors), npm run typecheck — all clean.

## 2026-05-20 — Shared agent skills setup

Status: Done
Source: project manager chat summary

Finding:
- Shared `.claude/skills/` skill library added for Claude Code and OpenCode.
- Project-local OpenCode agent definitions added under `.opencode/agents/`.
- Repo-owned Markdown memory live under `docs/memory/`.

Impact:
- Agents read relevant skills and memory before broad repo exploration.

Next action:
- None. Setup complete.
