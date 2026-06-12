# Project-Review Remediation Plan — 2026-06

Source: full-project review (2026-06-12, Claude Code session, branch
`claude/project-review-recommendations-x8a428`). Owner decisions incorporated:
NiFi ingestion is wanted but deferred; graphify rules are removed; pipeline
enrichment fires on the **final** index pass so intelligence is always based on
the updated (translated) document.

## Verified findings (ground truth for this plan)

The review audited backend, frontend, tests/CI, and security/ops. Several
agent-reported "critical" items were **disproved by code inspection** and are
excluded:

- `/search` admin bypass — fixed (`routers/search.py:138` passes `allow_all=is_admin`).
- Orphaned-Qdrant-vector chunk_text leak — fixed (`routers/search.py:264` drops missing-row results).
- `/expertise` subscription user-discovery leak — fixed (co-membership check, `related/service.py:175-178`).
- `/related` narrow group expansion — fixed (`routers/documents.py:564` uses effective groups).
- `/me/activity` post-revocation visibility — fixed (`routers/documents.py:243-249`).
- `/admin/config` secret masking — fixed (`routers/admin/config.py:19-39`).

`docs/context/acl-audit.md` still describes the pre-fix state — updating it is
Workstream 2.

Confirmed-open findings:

- **Double enrichment firing**: `translate_worker.py:102` publishes `index` AND
  `:110` publishes `embed`; `embed_worker.py:137` publishes `index` again;
  `index_worker.py:76,86` publishes `intelligence` + `alert` on every index
  message → intelligence/alert run twice per document with content.
- **Dead code**: `src/services/pipeline/translation_worker.py` (290 lines) has
  no entrypoint in `pyproject.toml`, no compose `command`, and zero callers.
- **NiFi drain unwired**: `NiFiKafkaDrain` (`kafka_consumer.py:99`) is
  instantiated nowhere; `production-compose.md` overstates NiFi readiness.
- **Silent failures**: ~80 log-and-continue `except Exception` blocks; the
  high-risk cluster is `slow_worker.py:245-327` (enrichment swallowed),
  `worker.py:520-545` + `parse_worker.py:267-272` (attachment/publish failures
  swallowed post-commit), `rag/service.py:498-521` (degraded retrieval
  indistinguishable from empty results).
- **Test gaps**: zero backend tests for `documents`, `ops`, `vault` services;
  frontend `auth/` untested; eval harness (#667) never runs in CI; no migration
  downgrade tests; no coverage floor.
- **Hardening**: backend image runs as root (no `USER` in
  `docker/backend.Dockerfile`); `docker/ollama-llm.Dockerfile:1` uses `:latest`;
  worker health servers bind `0.0.0.0` (`consumer_base.py:215`); no preflight
  rejection of `change-me-*` defaults; `admin@local.com`/`admin` bootstrap
  (`auth/service.py:29-36`).
- **Structural debt**: `routers/documents.py` (872 LOC), `admin/sources.py`
  (757), `rag/service.py` (688), `connectors/atlassian.py` (1566);
  `AdminModelProvidersPage.tsx` (853 LOC, 37 `useState`);
  `AdminSourceDetailPage.tsx` (942 LOC); hand-written API types drifting
  (`api/chat.ts:15-16` carries both `doc_title` and `document_title`);
  `Settings` has never-checked feature flags and `extra="ignore"`.

## Owner decisions (2026-06-12)

1. **NiFi**: wanted, not urgent. Keep `kafka_consumer.py` and the `kafka`
   compose service. File a `status:deferred` feature issue for wiring the drain
   (new worker or API background task + Kafka client dependency + read
   `settings.kafka_broker` + drain loop with offset commit). Correct the
   `production-compose.md` claim now.
2. **Graphify**: remove the graphify sections from `CLAUDE.md` and `AGENTS.md`
   (rules reference a `graphify-out/` that does not exist in the repo).
3. **Double-index fix**: enrichment (intelligence + alert) must run on the
   **updated** document — fire on the final index pass, not the early one.

## Workstream 1 — Pipeline correctness (`feature/pipeline-correctness`)

### 1a. Enrichment fires once, on the final index pass

Goal: intelligence/alert run exactly once per pipeline pass, after translation
is persisted, so enrichment always reads the updated document.

Approach:

1. Add an `enrich: bool` field to the index message payload
   (`publisher.publish_index`), defaulting to `True` for backward compatibility
   with in-flight messages during deploy.
2. `translate_worker.py:102` publishes the early index message with
   `enrich=False` — keeps BM25/keyword search available immediately and
   preserves the embed-degraded resilience path.
3. `embed_worker.py:137` publishes the final index message with `enrich=True`.
4. `index_worker.py` gates `publish_intelligence` / `publish_alert` on the
   flag. Meilisearch indexing itself stays unconditional (idempotent upsert).
5. Empty-content path (`translate_worker.py:54-64`) already skips the early
   index publish — embed's final publish carries enrichment. No change.

Tests: unit test asserting (a) early index message does not publish
intelligence/alert, (b) final message does, (c) default-True compatibility.

Risk: if the embed stage dead-letters (e.g., embedding model down while an
external LLM is up), enrichment never fires for that document. Mitigation: the
admin requeue endpoint already resets dead-letter jobs; note in ops docs.
Accepted by owner (enrichment requires an LLM anyway).

### 1b. Delete dead `translation_worker.py`

Remove `src/services/pipeline/translation_worker.py` and any test references;
CHANGELOG entry under Removed. Zero runtime references verified.

### 1c. Silent-failure tiering (three PRs)

1. **Enrichment visibility**: `slow_worker.py:302-327` — on alert/intelligence
   failure, dead-letter the corresponding pipeline job instead of swallowing,
   so the admin ingestion page surfaces it. No new tables.
2. **Post-commit publish failures**: `parse_worker.py:267-272`,
   `translate_worker.py` — a failed `publish_*` after the job is marked
   succeeded strands the document; mark the job for retry via the existing
   claim/retry machinery instead of logging only.
3. **RAG degraded flag**: `rag/service.py:498-521` returns
   `retrieval_degraded: bool` when the Qdrant/BM25 futures fail; thread through
   `SearchResponse` and the chat retrieval trace (same pattern as
   `reranker_applied`, #650); Evidence Inspector shows a warning chip.

## Workstream 2 — Truth reconciliation (docs, parallel-safe, targets `main`)

1. `docs/context/acl-audit.md`: add a Status column; mark H1, H3, H4, H5, M1,
   M2 **Fixed** with commit refs (`git log -S` per fix). Open tail: M3
   (per-version ACL — design-time), L-items (incl. symlink-traversal regression
   test).
2. `docs/operations/production-compose.md`: correct the NiFi claim — drain
   implemented but not wired; reference the deferred issue.
3. `CLAUDE.md` + `AGENTS.md`: remove graphify sections (owner decision #2).
4. `docs/memory/current-state.md`: resolve the double-index Watch item
   (answered: unintentional, fix = WS1a); keep or archive the stale-base PR
   Watch item at owner's discretion.

## Workstream 3 — Deployment hardening (one PR, targets `main`)

1. `docker/backend.Dockerfile`: add non-root `USER`; same PR must fix
   named-volume write ownership (entrypoint `chown` or compose `user:`) — root
   is currently load-bearing for volume writes (memory 2026-06-02).
   Air-gapped upgrade note required.
2. `docker/ollama-llm.Dockerfile:1`: pin to `0.5.13` (matches airgap).
3. `consumer_base.py:215`: bind health servers to `127.0.0.1` **after**
   verifying compose healthchecks probe in-container (they curl localhost).
4. New `scripts/check-prod-env.sh` wired into `tomorrowland-airgap.sh up`:
   fail on literal `change-me-*` / `changeme` / `dev-meilisearch-master-key`,
   empty `credential_store_key`, and warn if the bootstrap admin password is
   unchanged.

## Workstream 4 — Test-gap closure (issue per item, parallel-safe)

1. `tests/unit/test_documents_repository.py` — core paths of
   `documents/repository.py` (784 LOC, zero direct tests). Highest priority.
2. `tests/unit/test_vault*.py` — secrets handling.
3. Frontend: `auth/` login/signup validation + error states; search
   filter/debounce; chat streaming error path (fix `ChatWindow.tsx:160`
   toast-only catch with an error UI in the same PR as its test).
4. `tests/test_migration_downgrade.py` — last-5 migrations
   `upgrade → downgrade -1 → upgrade` smoke.
5. `.github/workflows/nightly-integration.yml` — nightly integration suite +
   `pytest tests/eval --eval` against the compose stack; archive the JSON
   results artifact.
6. After 1–3 land: ratchet coverage — frontend vitest thresholds 30→50%;
   backend `--cov-fail-under` at measured-floor-minus-2.

## Workstream 5 — Structural debt (normal queue, lowest urgency)

1. Split `routers/documents.py` by domain (core / intelligence / translation /
   related). Mechanical; no behavior change.
2. `AdminModelProvidersPage.tsx` → react-hook-form + Zod; reuse for other
   admin forms; then decompose `AdminSourceDetailPage.tsx`.
3. `DocumentChatPanel.tsx` → established seed-once TanStack Query pattern.
4. `Settings`: prune never-checked feature flags (`feature_summarization`,
   `feature_entity_extraction`, …); warn on unknown env vars (full
   `extra="forbid"` may break operators — evaluate).
5. Decide OpenAPI type generation (`openapi-typescript`) vs hand-written +
   Zod guards; fix `api/chat.ts:15-16` field duplication either way.

## Deferred feature issue (file with `status:deferred`)

**Wire NiFi → Kafka drain into the runtime.** Scope: choose runner (dedicated
worker service vs API background task), add a Kafka client dependency, read
`settings.kafka_broker`, periodic `NiFiKafkaDrain.drain()` loop with offset
commit, compose service + healthcheck, integration test against Redpanda.
Blocked on: owner promotion (wanted, not urgent — decision 2026-06-12).

## Sequence

- Week 1: WS2 (docs truth) + WS1a/1b on `feature/pipeline-correctness`.
- Week 2: WS1c + WS3.
- Weeks 3–4: WS4 items 1–4; then WS4 5–6.
- WS5 flows through the normal issue queue.

Each workstream becomes a GitHub issue with a Context Budget; WS1 gets a parent
tracker + feature branch per the feature-branch policy.

## Verification (per workstream)

- Backend: `uv run ruff check --fix src/ tests/ migrations/` →
  `uv run ruff format` → `uv run mypy src --strict` → targeted
  `uv run pytest tests/unit/test_<area>.py -q` → full `uv run pytest tests/unit -q`
  before push.
- Frontend: `npm run typecheck`, `npx vitest run src/features/<area>/`.
- Compose-touching PRs: `docker compose config` renders; airgap validator
  passes.
- Docs-touching PRs: `uv run mkdocs build --strict`.
