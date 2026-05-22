# Tomorrowland Current State

Canonical shared memory for active project state. Keep this file compact and factual.

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

## 2026-05-22 — Document Chat Phases A–C complete (#471–#474)

Status: Active (Phases D–G pending)
Source: issues #471–#474; PRs #472, #473, #474 on `feature/document-chat`

Finding:
- #472 Phase A (Q&A foundation) — Done. Merged to `main`. Issue closed.
- #473 Phase B (persistent chat sessions) — CI verified (58 files, 410 tests). Issue closed.
- #474 Phase C (scope-aware chat) — Done. On `feature/document-chat`. Pending merge to `main`.
- Remaining phases D–G (#475–#478) not started; listed on GitHub as `status:next`.
- Pre-existing bugs discovered during #473 verification: CitationList.tsx `idx` variable, PdfViewer.tsx `allPdfText` state (both fixed).

Next action:
- Open integration PR `feature/document-chat` → `main`.
- Phase D (#475): conversation-aware query rewrite.

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
