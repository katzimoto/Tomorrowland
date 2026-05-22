# Tomorrowland Current State

Canonical shared memory for active project state. Keep this file compact and factual.

## 2026-05-21 — Document viewer track in progress (#440–#449)

Status: Superseded
Source: issues #440–#449, #453; PRs #454–#462

Finding:
- Document viewer MVP track (parent #453) is underway.
- #440 (HTML sandbox) — Done. PR #454 merged to `main`.
- #441 (full text API) — Done. PR #455 merged to `feature/document-viewer`.
- #442 (PDF.js viewer) — Done. PR #456 merged to `feature/document-viewer`.
- #443 (view mode switcher + fidelity bar) — Done. PR #457 merged to `feature/document-viewer`.
- #444 (image viewer) — Done. PR #458 merged to `feature/document-viewer`.
- #445 (metadata Details tab) — Done. PR #459 merged to `feature/document-viewer`.
- #447 (code/syntax viewer) — Done. PR #460 merged to `feature/document-viewer`.
- #448 (media viewer) — Done. PR #461 merged to `feature/document-viewer`.
- #449 (in-document search) — Done. PR #462 merged to `feature/document-viewer`.

## 2026-05-21 — Document viewer a11y, perf, telemetry hardening (#450)

Status: Done
Source: issue #450; PR #464

Finding:
- #450 (a11y, perf, telemetry hardening) — Done. PR #464 targets `feature/document-viewer`.
- A11y: download link aria-label, table aria-label + th scope="col", sr-only status text, focus management on view mode switch and search close.
- Perf: TextPreview virtualized with react-window v2 `List` when >10K lines; TablePreview virtualized with ARIA role-based table when >1K rows.
- Telemetry: viewer.text/pdf/image.load events via named performance timers.
- Backend: X-Content-Type-Options: nosniff on download endpoint.
- react-window v2 key differences from v1: `List` replaces `FixedSizeList`, `rowCount`/`rowHeight`/`rowComponent` props, `rowProps={{}}` required (crashes if undefined).
- ResizeObserver global mock added to test setup (required by react-window v2 in jsdom).

Impact:
- react-window@2.2.7 added to frontend dependencies.
- Virtualized TablePreview uses `role="table"` / `role="rowgroup"` / `role="row"` / `role="columnheader"` / `role="cell"` instead of native `<table>` / `<thead>` / `<tbody>` / `<tr>` / `<th>` / `<td>` (react-window constraint).
- `src/test/setup.ts` now includes ResizeObserver mock, scrollIntoView mock, HTMLDialogElement mocks.
- Download endpoint returns `X-Content-Type-Options: nosniff` on both full and range responses.

Next action:
- Check parent issue #453 for remaining MVP child issues.
- Consider browser-based virtualization verification (#451 follow-up).

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

## 2026-05-21 — Document Chat feature in progress (#471–#478)

Status: Active
Source: issue #471 (parent), #472 Phase A, #473 Phase B; PRs merged to `feature/document-chat`

Finding:
- Document Chat design doc at `docs/design/document-chat-design.md` (committed 06fae05 to main).
- Phase A (RAG + backend foundation): merged to main via PR #472.
- Phase B (backend API + frontend UI, B1–B6): implementation on `feature/document-chat`.
  - Backend: `src/services/api/routers/chat.py` — sessions CRUD, message send, citations.
  - Frontend: `frontend/src/features/chat/` — ChatPage, ChatSidebar, ChatWindow, MessageList, ChatInput, ChatCitationList, all CSS modules; route `/chat` added; NavRail entry added.
  - i18n: full `chat` namespace in en.ts + he.ts.
  - Tests: 11 cases in ChatPage.test.tsx covering empty state, session CRUD, send+reply, citations, loading/error.
- B7 integration tests: done. 25 integration + 18 unit backend tests pass (43 total). 16 frontend tests cover lifecycle, error, and citation fields.
- Phase C backend (scope-aware chat): done. Commit d7ab8e8 on feature/document-chat.
  - `ChatScope` model + `build_qdrant_filter()` in `src/services/rag/service.py`.
  - `QdrantSearchClient.search_filtered()` for pre-built filter path.
  - Chat router validates revoked doc access (409) and passes `ChatScope` to RAG.
  - 17 unit tests (scope validation + filter builder) + 8 new integration tests.
  - 68 total tests pass (unit + repository + integration).
- Phase C frontend (ScopeBadge, ScopeSelector, InsightPane migration) not started.

Impact:
- DELETE `/chat/sessions/{id}` returns `{"ok": true}` 200 (not 204) — `deleteChatSession` typed as `Promise<{ ok: boolean }>`.
- TanStack Query v5: `onSuccess` removed from `useQuery`; seeding uses `useEffect` with seed-once ref guard.
- Node 22 required for test/lint in frontend; CI runs on 22, local env at 20.9.0.
- Session_id path params typed as `UUID`; FastAPI validates on entry (422 on malformed, not 500).
- Dual-gate feature flag: tests must seed `system_config` key `feature.document_chat = true` AND pass `feature_document_chat=True` in Settings.
- Foundation migration seeds `feature.document_chat = False` by default (production safety) — test harness overrides this in `_setup_users()`.
- `folder` scope returns 400 (Qdrant payload has no folder field — deferred).
- `source` scope: Qdrant filter by `source_id` built; revocation validation TODO (group filter still applied for safety).

Next action:
- Phase C frontend: ScopeBadge, ScopeSelector, InsightPane Chat tab migration.
- Open PR for #473/#474 when frontend Phase C is ready.

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
