# Agent-Efficiency GAP Analysis V2 — Tomorrowland

Date: 2026-06-08
Researcher: researcher profile, kanban task t_21257362

## Audit Summary (what EXISTS — verified)

The repo already has substantial agent-efficiency infrastructure:

| Feature | Status | Location |
|---|---|---|
| CLAUDE.md entry point | Exists, delegates to AGENTS.md | `CLAUDE.md` |
| CODEX.md entry point | Exists | `CODEX.md` |
| AGENTS.md (multi-agent rules) | Comprehensive | `AGENTS.md` |
| Token efficiency rules | Detailed | `docs/agents/token-efficiency.md` |
| Coding behavior rules | Detailed | `docs/agents/coding-behavior.md` |
| Agent templates | Claim/transfer/handoff/issue/PR | `docs/agents/templates.md` |
| Shared memory system | `docs/memory/` directory | `docs/memory/` (6 files) |
| Shared-file discipline | In AGENTS.md + token-efficiency.md | — |
| Pre-PR cleanliness script | Exists | `scripts/check-pr-cleanliness.sh` |
| Area context maps | 4 areas covered | `docs/context/` (6 files) |
| Reusable agent skills | 6 tl-* skills | `.agents/skills/` |
| Graphify knowledge graph | Multiple snapshots | `graphify-out/` |
| Copilot instructions | Exists | `.github/copilot-instructions.md` |
| OpenCode config | Exists | `opencode.json` |
| .editorconfig | Exists | `.editorconfig` |
| .gitignore | Comprehensive | `.gitignore` |

## Identified GAPS (ranked by impact/effort)

### GAP 1: Pytest addopts produce extreme token waste for agents (CRITICAL)

**Verification:** `pyproject.toml` line 77 sets addopts that include `--cov-report=term-missing`. Running a single passing test file (`tests/unit/test_config_cache.py`) with 34 tests produced 100+ lines of coverage-missing output followed by only 2 lines of actual test results. CI `backend.yml:146` runs bare `pytest` (inheriting these addopts), while only the Postgres variant (`backend.yml:189`) uses `-q`.

**Impact:** Every agent that runs or debugs tests locally or in CI faces a wall of coverage noise. The addopts make even passing runs verbose. For CI debugging, the actual error is buried under thousands of coverage lines.

**Fix:** Remove `--cov-report=term-missing` from `pyproject.toml` line 77 addopts. Move coverage reporting to a dedicated command:

```toml
# pyproject.toml - line 77, change from:
addopts = "-m 'not e2e' --strict-markers --cov=src --cov-branch --cov-report=term-missing --cov-fail-under=90"
# to:
addopts = "-m 'not e2e' --strict-markers -q"
```

Then create `scripts/dev/cov.sh`:
```bash
#!/usr/bin/env bash
# Run full test suite with coverage report (for humans; agents use `uv run pytest -q`)
uv run pytest --cov=src --cov-branch --cov-report=term-missing --cov-fail-under=90 "$@"
```

And update `backend.yml:146` to run coverage separately from the test step.

**Effort:** <30 minutes. Single-line `pyproject.toml` change, small CI workflow tweak, one new script.

---

### GAP 2: No service manifest / module index (HIGH)

**Verification:** Searched for `SERVICES.md` across the entire repo — 0 results. Searched for `ARCHITECTURE*` — 0 results. The 21 services under `src/services/` are listed in AGENTS.md as a prose paragraph but with no one-line descriptions. `docs/context/README.md` only covers 4 of 21 services (backend-api, frontend, search, extraction). The remaining 17 services (alerts, annotations, auth, chat, chunking, connectors, intelligence, mcp, ops, permissions, pipeline, preview, rag, related, translation, vault) have no context map.

**Impact:** Every agent must grep or read source to understand what services exist and what each does. Combined with the lack of `__init__.py` docstrings (most are empty), there's zero discoverability beyond the prose in AGENTS.md.

**Fix:** Create `docs/SERVICES.md`:

```markdown
# Tomorrowland Services

| Service | Purpose | Key files |
|---|---|---|
| alerts | Alert evaluation and notification dispatch | `src/services/alerts/` |
| annotations | Document annotations (highlights, notes) | `src/services/annotations/` |
| api | FastAPI application, routes, routers | `src/services/api/` |
| auth | JWT, password, LDAP authentication | `src/services/auth/` |
| chat | Chat/conversation storage and retrieval | `src/services/chat/` |
| chunking | Document chunking for indexing | `src/services/chunking/` |
| connectors | External source connectors (Atlassian, SMB, NiFi) | `src/services/connectors/` |
| documents | Document metadata repository | `src/services/documents/` |
| extraction | File-type extraction (PDF, DOCX, EML, etc.) | `src/services/extraction/` |
| intelligence | AI-powered document analysis | `src/services/intelligence/` |
| mcp | Model Context Protocol server and client | `src/services/mcp/` |
| ops | Operations helpers | `src/services/ops/` |
| permissions | Authorization guards, document access | `src/services/permissions/` |
| pipeline | Ingest→parse→translate→embed→index workers | `src/services/pipeline/` |
| preview | Document preview generation | `src/services/preview/` |
| rag | Retrieval-augmented generation | `src/services/rag/` |
| related | Related document discovery | `src/services/related/` |
| search | Hybrid search (Meilisearch + Qdrant) | `src/services/search/` |
| translation | Document translation | `src/services/translation/` |
| vault | Credential vault | `src/services/vault/` |
```

**Effort:** <30 minutes. One new markdown file.

---

### GAP 3: graphify-out accumulates 513MB of stale generated data (MEDIUM)

**Verification:** `du -sh graphify-out/` = 513MB. Contains 48 dated subdirectories (e.g., `2026-06-06_4`, `2026-06-08_21`), each with ~12MB `graph.json`. These are gitignored (`.gitignore` line 44) but remain on every developer's disk. The canonical `graphify-out/graph.json` is MISSING — only dated snapshots exist. CLAUDE.md (line 60) instructs agents to use `graphify query` which requires `graphify-out/graph.json` — it will fail silently, forcing a fallback to `rg`.

**Impact:** 513MB of disk waste per developer. Missing canonical `graph.json` means every agent invocation of `graphify query` fails and falls back to grep. Stale snapshots could be accidentally explored by agents.

**Fix:** Add cleanup to the `graphify` invocation pattern. Update CLAUDE.md lines 60-63:

```markdown
- After running `graphify update .`, clean up old snapshots:
  `ls -dt graphify-out/2* | tail -n +4 | xargs rm -rf` (keep last 3)
```

And create a `scripts/dev/clean-graphify.sh`:
```bash
#!/usr/bin/env bash
# Keep last 3 graphify snapshots, remove the rest
set -euo pipefail
cd "$(dirname "$0")/../.."
if [ -d graphify-out ]; then
  ls -dt graphify-out/2* 2>/dev/null | tail -n +4 | xargs rm -rf
  echo "Cleaned old graphify snapshots. Remaining:"
  ls -d graphify-out/2* 2>/dev/null || echo "  (none)"
fi
```

**Effort:** <20 minutes. One new script, one CLAUDE.md update.

---

### GAP 4: Two monolithic test files waste agent context (MEDIUM)

**Verification:** `tests/unit/test_mcp_server.py` = 88,529 bytes, `tests/unit/test_connectors.py` = 81,866 bytes. These are 2-3x larger than the next-largest test files. An agent targeting a specific test must load the entire file. For comparison, `test_config_cache.py` (which passed in 8s with clean output) is much smaller.

**Impact:** When an agent needs to read or fix a test in these areas, it loads 80KB+ regardless of which specific test is relevant. MCP server has 33KB of implementation in `src/services/mcp/server.py` — the test file is nearly 3x that.

**Fix:** Split these files by feature area:
- `test_mcp_server.py` → `test_mcp_server_tools.py`, `test_mcp_server_resources.py`, `test_mcp_server_prompts.py`
- `test_connectors.py` → `test_connectors_atlassian.py`, `test_connectors_smb.py`, `test_connectors_nifi.py`, `test_connectors_factory.py`

**Effort:** <1 hour. Pure code movement, no logic changes.

---

### GAP 5: No CI failure summary / structured error extraction (MEDIUM)

**Verification:** CI workflows (`backend.yml`, `frontend.yml`, `docs.yml`) run tools with raw output only. When `ruff check`, `mypy`, or `pytest` fails, the agent sees the full raw output with no post-processing. The backend CI runs 4 jobs (dependency-contracts, quality, migrations, tests) — an agent debugging a failure must read the full log to find the error.

**Impact:** Agents debugging CI failures spend context tokens re-reading logs that are 90% noise. No error fingerprinting means each CI failure investigation starts from scratch.

**Fix:** Add a CI failure summary to `scripts/dev/ci-failure-summary.sh`:
```bash
#!/usr/bin/env bash
# Extract structured error info from common tools
# Usage: ruff check ... 2>&1 | bash scripts/dev/ci-failure-summary.sh ruff
#        pytest 2>&1 | bash scripts/dev/ci-failure-summary.sh pytest
```

The script would:
1. For ruff: Extract only error lines (lines with `E`/`F` codes)
2. For mypy: Extract only `error:` lines with file:line references
3. For pytest: Extract FAILED test names and their assertion errors (strip coverage output)

**Effort:** <1 hour. One new script with 3 tool-specific extractors.

---

## What was deliberately skipped (verified — these patterns ALREADY EXIST)

| Pattern | Why skipped |
|---|---|
| CLAUDE.md recommendations | Already exists, delegates to AGENTS.md |
| Cursor rules | Already exists (`.cursor/rules/sqz.mdc`); user doesn't use Cursor |
| Multi-agent merge conflict rules | Already comprehensive in AGENTS.md shared-file discipline |
| Context budget templates | Already in `docs/agents/templates.md` |
| Pre-PR cleanliness checks | Already `scripts/check-pr-cleanliness.sh` |
| Lockfile/migration protection | Already in AGENTS.md shared-file caution + .gitignore |
| `.editorconfig` style consistency | Already exists |
| Graphify-based codebase navigation | Already referenced in CLAUDE.md |
| `docs/memory/` shared state | Already exists with 6 files |
| `.agents/skills/` reusable workflows | Already 6 tl-* skills exist |
| OpenCode/Copilot-specific instructions | Already in `docs/agents/opencode.md` and `docs/agents/copilot.md` |
| `.env.example` | Already exists |
