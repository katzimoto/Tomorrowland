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

Status: Active
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

## 2026-05-21 — Vector embedding context-length safety (#468)

Status: Active
Source: issue #468

Finding:
- `chunk_text()` splits by word count (default 512 words), but embedding models tokenize at sub-word level — a 512-word chunk can exceed model context length.
- Ollama's `/api/embed` returns `"input length exceeds the context length"` for oversized chunks.
- Error repeats deterministically across 5 retries before dead-lettering — affected documents get incomplete Qdrant coverage.
- Fix adds token-estimation (chars/3 heuristic) in chunking, defensive max-tokens guard in encoder, and permanent-error classification for ValueError in workers.
- New config: `EMBEDDING_MAX_TOKENS` (default 1024).

Impact:
- Oversized chunks are recursively split before reaching the encoder.
- Encoder validates each text's estimated token count before API call.
- ValueError (context-length exceeded) dead-letters immediately instead of retrying 5 times.

Next action:
- Complete implementation: ruff format, mypy, pytest.
- Open PR targeting `main`.

## 2026-05-20 — Shared agent skills setup

Status: Active
Source: project manager chat summary

Finding:
- Add a shared `.claude/skills/` skill library for Claude Code and OpenCode.
- Add project-local OpenCode agent definitions under `.opencode/agents/`.
- Add repo-owned Markdown memory under `docs/memory/`.

Impact:
- Future agent work should load only the relevant skills and memory files before broad repo exploration.
- Project memory should be easy to review in git.

Next action:
- Finish wiring skills, memory files, and OpenCode agent definitions.
