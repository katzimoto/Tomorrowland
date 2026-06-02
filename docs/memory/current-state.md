# Tomorrowland Current State

Canonical shared memory for active project state. Keep this file compact and factual.

## 2026-06-02 — verified: tag-cut RC ships no Ollama model bundle (workflow + build-script + static proof)

Status: Active
Source: Claude Code session 2026-06-02; commits cc6e203 + static build proof

**Verified the next tag-cut RC excludes the Ollama model-weights bundle** (user goal: ship RC without the local-LLM bundle, run on LiteLLM). Three independent confirmations:
1. `.github/workflows/release-artifact.yml`: the `build-ollama-model-bundle` job is `if: inputs.build_ollama_bundle` (default false); on a `push: tags` event `inputs.*` is empty → job skipped. The `build-artifact` job attaches ONLY `tomorrowland-release-*.tar.gz` + `tomorrowland-images-*.tar.part-*` — never a bundle.
2. `scripts/build-release-artifact.sh`: archive is an explicit allow-list (no `*ollama-bundle*` copied in); model weights live in the `ollama_data` Docker VOLUME, never in an image, so `docker save` of the runtime images cannot capture them. The `ollama/ollama:0.5.13` RUNTIME image stays bundled so the service still starts.
3. Static proof: `RELEASE_DIST_DIR=/tmp SKIP_DOCKER_BUILD=1 SPLIT_IMAGE_BUNDLE=0 bash scripts/build-release-artifact.sh v1.0-rc6` → archive file list clean of bundle/weights/blobs/.gguf; ollama runtime present in manifest.

**Doc follow-up (committed cc6e203):** README-airgap.md + generated README-airgap.txt now state the no-bundle path — external LLM (LiteLLM/openai-compatible via LLM_PROVIDER) OR optional bundle; keyword search + ingest work with no model at all.

**Note:** `validate-airgap-artifact.sh` auto-discovers any stray `tomorrowland-ollama-bundle-*.tar.gz` in the artifact dir or its parent `dist/` and validates it (warning-only, never attached). CI runs on a clean checkout so this is a no-op there; only matters for LOCAL builds where old bundles sit in `dist/`. See [[project_airgap_compose_parity]].

---

## 2026-06-02 — air-gapped LiteLLM / external-LLM enabled (compose passthrough) + RC state

Status: Active
Source: Claude Code session 2026-06-02; working tree (uncommitted)

**Found + fixed (uncommitted working tree):** the air-gapped stack could not be switched to an external local LLM (LiteLLM / OpenAI-compatible) even though the code fully supports it. `Settings` defines `LLM_PROVIDER`/`LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY` (factory.py → OpenAICompatibleLLMProvider; `litellm`/`openai-compatible`/`openai`/`llama-cpp`) and the embedding factory supports `EMBEDDING_PROVIDER=openai-compatible` + `EMBEDDING_API_KEY`, but **none of those vars were in the `x-app-environment` anchor** of either compose file, so they never reached the containers (proven via `docker compose config`). Default provider stayed hard-pinned to Ollama.

**Fix:** added `LLM_PROVIDER`/`LLM_BASE_URL`/`LLM_MODEL`/`LLM_API_KEY`/`EMBEDDING_API_KEY` (empty defaults → no behavior change) to BOTH `docker-compose.airgap.yml` and `docker-compose.yml`; documented the LiteLLM path in `.env.airgap.example` + `docs/operations/air-gapped-deployment.md`; softened the "must use EMBEDDING_PROVIDER=ollama" line; CHANGELOG Added entry. Because the pipeline workers (intelligence/enrich/slow) build via `build_llm_provider(settings)` (env factory), setting `LLM_PROVIDER=litellm` now routes api AND all workers. Verified: override flows into every service; compose still renders; validator assertions (meili + 7 workers, no build steps) hold.

**Also fixed:** untracked `scripts/bundle-from-running-ollama.sh` defaulted `COMPOSE_SERVICE=ollama-llm` (a main-compose name) while its default `COMPOSE_FILE=docker-compose.airgap.yml` only has `ollama` → realigned to `ollama`. Script still untracked.

**Release state:** tag `v1.0-rc5` = `8f1b98e` (#621 airgap fix IS included). `[Unreleased]` now holds #622–#625 + this LiteLLM passthrough → a fresh tag (rc6) is needed to ship them. Did NOT tag/build (outward-facing).

**Watch (not changed):** (1) compose defaults vs `.env.airgap.example` drift — `OLLAMA_MODEL` qwen3:4b vs mistral, `EMBEDDING_MODEL`/`EMBEDDING_DIMENSION` qwen3-embedding:8b/4096 vs nomic-embed-text/768 (harmless when operator copies the .env, dangerous dim mismatch only if relying on compose defaults). (2) `embed-worker`/`intelligence-worker` still `depends_on ollama:healthy`; bundled ollama idles (empty=healthy) under LiteLLM so workers still start — acceptable, no profile added (memory warns against touching the ollama service).

See [[project_airgap_compose_parity]].

---

## 2026-06-02 — #625 merged (rebase preserved #624); stale-base pattern now spans 2 author branches

Status: Watch
Source: PR #625 (6b1719c), Claude Code session

**#625** (`fix/pipeline-bugs-15`) was force-pushed onto stale **#623**, re-doing #624's pipeline work *without* its review fixes and conflicting in `parse_worker`/`scheduler`/`slow_worker`. Rebased onto current main and resolved to keep #624 (attachment cycle guard) + only the net-new work (tombstone wiring in `sync_now`, `build_index_cleanup`, scheduler reconnect guard, bare-`except` logging). Also fixed a **no-op intelligence timeout** — `as_completed()` only yields finished futures, so `future.result(timeout=120)` never fired; moved the budget onto `as_completed(futures, timeout=120)` + non-blocking `pool.shutdown(cancel_futures=True)`.

**Broadened Watch:** the *stale-base → force-push → re-do-already-merged-work* pattern (with PR descriptions that undercount files) now spans **both** of this author's branches — `fix/bug-bounty-rounds-1-3` (#622, #623; airgap revert) and `fix/pipeline-bugs-15` (#624 → #625). For any PR from **katzimoto**: diff against current `main` (not the description), confirm it isn't based on a pre-merge commit, and check it doesn't revert prior merged fixes. Airgap specifics in the #622–#624 entry below.

Still open (unverified): the `translate*`/`embed` double-index question — untouched by #625.

---

## 2026-06-01 — bug-bounty + pipeline hardening merged (#622, #623, #624)

Status: Done — all three squash-merged to main; 2 Watch items below
Source: PRs #622 (d3abd92), #623 (49d7470), #624 (cec926d) — Claude Code review+fix sessions

Three review-and-fix passes merged the same day:
- **#622** bug-bounty rounds 1-3. Review fixes: chat SSE keeps the user message on client disconnect (own txn), `/notifications` pagination wired through the endpoint, SSRF rejects private IPs on *both* DNS resolutions, vault deterministic `ORDER BY`, search seeds URL state once.
- **#623** SQL-safety + sanitizer. `profile_repository._ALLOWED_COLUMNS` whitelist before `UPDATE ... SET` interpolation. Review fix: `preview/service.py` HTML sanitizer now `html.escape`s attribute values + text — the rewrite had attribute-breakout + entity-smuggle XSS; kept dependency-free (no nh3/bleach) for air-gap. Removed orphaned legacy QA UI.
- **#624** 15 ingest→embed pipeline bugs (claim_next double-claim race, consumer_base retry rewrite, attachments as child docs, embed citation metadata). Review fix: async attachment processing has a cycle/depth guard + `has_extractor()` filter.

**Watch:**
- **Recurring airgap revert (branch `fix/bug-bounty-rounds-1-3`, author katzimoto):** re-introduced the Ollama removal in `docker-compose.airgap.yml` (reverting #621) in BOTH #622 and #623 — never in the PR description. Both PRs also omitted their largest changes (#623 silently deleted the QA UI). On any PR from this branch, reset `docker-compose.airgap.yml` + `scripts/{build-release,validate}-airgap*.sh` to main and don't trust its "validation passed" claims against the diff.
- **Double-index (unverified):** `translate_worker` + `translation_worker` both `publish_index`, and `embed_worker` also `publish_index`, so index → intelligence/alert may double-fire per translated doc. Pre-existing; left in #624. Needs a holistic DAG fix or confirmation it's intentional index-resilience for the embed-skipped path.

---

## 2026-05-31 — feat(auth): LDAP group mapping via live DC search — #582, PR #601

Status: Done — squash-merged to main (branch deleted), issue #582 closed
Source: issue #582, PR #601, Claude Code session

Live LDAP group search and explicit LDAP→Tomorrowland group mappings. Review found 3 blocking bugs; all fixed before merge.

| Area | Detail |
|---|---|
| LdapClient | `search_groups()` — service-account bind, RFC 4515 filter escaping, timeout/limit, ephemeral (no DB writes) |
| Repository | `LdapGroupMappingRepository` — CRUD with duplicate DN rejection and target group validation |
| Admin API | `GET /admin/ldap/groups/search`, `GET/POST/DELETE /admin/ldap/group-mappings`; admin-only; audit events on create/delete |
| Auth | `upsert_ldap_user()` resolves groups through explicit mappings only; unmapped LDAP groups silently dropped |
| Migration | `l1m2n3o4p5q6` — `ldap_group_mappings` table, DN uniqueness, FK to groups (RESTRICT), FK to users (SET NULL) |
| Config | `LDAP_GROUP_SEARCH_BASE_DNS`, `LDAP_GROUP_SEARCH_FILTER`, `LDAP_GROUP_SEARCH_LIMIT`, `LDAP_GROUP_SEARCH_TIMEOUT`, `LDAP_GROUP_EXTERNAL_ID_ATTR`, `LDAP_GROUP_DISPLAY_NAME_ATTR` |
| Frontend | `AdminLdapPage` at `/admin/ldap` — ephemeral search, map-to-group dialog, delete confirmation; EN + HE i18n |
| Tests | 14 unit tests: repo CRUD, duplicate rejection, missing target group, filter escaping, auth integration |

Review bugs fixed in commit c845406 before merge:
- `setup-env.sh`: missing newline collapsed `LDAP_BIND_PASSWORD=""` and `if` onto one line (broken bash)
- `distinguished_name` → `dn` in schema + `ldap_client.py` dict key (frontend type expected `dn`; DN column was blank and POST sent `ldap_dn: undefined`)
- Removed dead `Limit` TextInput in `AdminLdapPage` (frontend sent `?limit=N` but backend only reads `q`)

---

## 2026-05-30 — test(agents): permission regression tests for researcher queries — #562, PR #598

Status: Done — PR #598 squash-merged to main (commit 0462d30), branch deleted
Source: issue #562, PR #598, Claude Code session

Permission regression test suite for the six `/api/agent/v1/*` researcher endpoints and MCP tools.

| Area | Detail |
|---|---|
| Cross-user isolation | 4 tests: user A / user B symmetric isolation across search, get_document, get_passages, get_related_documents |
| Source filter scope | 2 tests: filter for existing-but-inaccessible source returns no docs; `_SourceFilteringMeili` double verifies narrowing within allowed corpus |
| Over-limit safety | 1 test: 429 body contains no document IDs or auth tokens |
| MCP parity | 24 unit tests: all 6 tools translate 401/403 to static safe messages; 403 body doc IDs not forwarded; 429 metadata not forwarded |
| Bug fixed | `_FakeMeiliProvider` returned hex UUIDs (no dashes) while router's `docs` dict uses dashed keys — `r.document_id in docs` was always False, silently masking BM25-only path tests. Fixed `str(r[0])` → `str(UUID(r[0]))`. No product code changed |
| Test counts | integration: 30 → 38; unit (MCP): 37 → 61 |
| Verified | ruff clean, ruff format clean, mypy strict clean, 38 integration + 61 MCP unit tests pass |

---

## 2026-05-30 — feat(agents): audit logging and usage limits for researcher API — #561, PR #595

Status: Done — PR #595 squash-merged to main (commit 9d28657), branch deleted
Source: issue #561, PR #595, Claude Code session

Structured audit logging and per-user rate limiting for all six `/api/agent/v1/*` endpoints.

| Area | Detail |
|---|---|
| Audit logging | `_agent_audit_log()` helper in `agent.py` — emits structured `INFO` log line per call; logs route, user id, correlation id, query length, result count, latency, status; never logs raw text, JWTs, or auth headers |
| Rate limiter | `AgentRateLimiter` in `src/shared/rate_limit.py` — in-memory sliding window; two independent per-user buckets: general (100/60s) and ask_corpus (20/60s); fail-closes on invalid config at startup |
| MCP inheritance | MCP tools proxy to REST — limits and audit events inherited automatically; no separate MCP enforcement; 429 added to `_translate_error` |
| Config | `AGENT_RATE_LIMIT_ENABLED` (true), `AGENT_RATE_LIMIT_WINDOW_SECONDS` (60), `AGENT_RATE_LIMIT_CALLS_PER_WINDOW` (100), `AGENT_RATE_LIMIT_ASK_CORPUS_CALLS_PER_WINDOW` (20) |
| Bug fix | `_StubLLM` in integration test fixture set `self.model` as instance attribute against read-only `@property` on `LLMProvider` Protocol — fixed to `@property` |
| Operator docs | New section in `docs/operators/ai-surfaces.md` — audit event format, what is/isn't logged, rate limit table, MCP behavior, troubleshooting |
| Tests | 18 unit tests (rate limiter) + 8 integration tests (audit emission, no-leak, 429, per-user isolation, disabled limiter, MCP 429 translation) |
| Verified | ruff clean, ruff format clean, mypy clean on changed files, 31 integration tests pass |

---

## 2026-05-30 — feat(admin): source profiles P1 — #585, PR #594, commit cf1d41d

Status: Done — PR #594 squash-merged to main, branch deleted
Source: issue #585, PR #594, Claude Code session

New `source_profiles` system for per-source strategy configuration (domain type,
chunking, retrieval, extraction). Admin-only API with full CRUD, activate/deprecate
lifecycle, and audit logging. Foundational wiring into `IntelligenceWorker`.

| Area | Detail |
|---|---|
| Migration | `c4d5e6f7a8b9` — `source_profiles` table with DB-level CheckConstraints on all enum fields (sa.text() consistent) |
| Repository | `ProfileRepository` — CRUD + `activate_profile` (atomic one-active-per-source) + `deprecate_profile` + `delete_profile` (blocks active) in `src/services/intelligence/profile_repository.py` |
| Admin API | 8 endpoints under `/admin/source-profiles` incl. `GET /active/{source_id}`; all admin-only with audit logs (update includes source_id/domain_type) |
| Worker integration | `IntelligenceWorker.process_document()` accepts `source_id`, resolves active profile for strategy routing (logging only; dispatch deferred) |
| Tests | 22 unit tests (repository + worker profile path) + 20 integration tests (incl. active-by-source) |
| Verified | ruff clean, ruff format clean, mypy clean on changed files |

---

## 2026-05-30 — feat(agents): Hermes MCP adapter for researcher API — #560, PR #593

Status: Done — PR #593 merged to main (squash), branch deleted
Source: issue #560, PR #593, Claude Code session

Six read-only MCP tools exposing the permissioned `/api/agent/v1/*` endpoints (#558) via Streamable HTTP transport.

| Area | Detail |
|---|---|
| Package | `src/services/mcp/` — FastMCP server + HTTP client |
| Tools | `tomorrowland_search_documents`, `tomorrowland_get_document`, `tomorrowland_get_passages`, `tomorrowland_ask_corpus`, `tomorrowland_get_related_documents`, `tomorrowland_list_facets` |
| Transport | Streamable HTTP (FastMCP built-in) at `/mcp`; stdio via `transport="stdio"` |
| Auth | Bearer token from `TOMORROWLAND_API_KEY` forwarded as-is; never inspected or logged |
| Config | `TOMORROWLAND_API_URL`, `TOMORROWLAND_API_KEY`, `MCP_HOST`, `MCP_PORT`, `API_TIMEOUT` |
| Entry point | `tomorrowland-mcp-server` CLI via `pyproject.toml` |
| Docs | `docs/operations/mcp-adapter.md` — config, auth, tools, Hermes snippet, troubleshooting |

**Security:**
- No direct DB, Qdrant, or Meilisearch access — all calls proxy through #558
- No write tools, no ACL duplication, no secrets in logs
- Error mapping: 401→auth, 403→denied, 404→not found, 422→invalid, 503→unavailable

**Verification:** ruff clean, mypy strict clean (3 files), 45/45 unit tests pass.

Next action: #561 (audit/usage limits) or #562 (permission regression expansion).

---

## 2026-05-30 — feat(agents): permissioned researcher API endpoints — #558/#592 merged  (+ CI fixes)

Status: Done — PR #592 merged to main (squash), branch deleted
Source: issue #558, PR #592, Claude Code session

New read-only `/api/agent/v1` surface with 6 endpoints that future Hermes/MCP clients (#560) can call through the same source/document ACL as normal users.

| Area | Detail |
|---|---|
| Endpoints | `search_documents`, `get_document`, `get_passages`, `ask_corpus`, `get_related_documents`, `list_facets` — all under `/api/agent/v1` |
| Auth | Every endpoint enforces transitive group expansion via `AuthRepository.get_effective_group_ids` and `assert_doc_access`; admin bypass uses `allow_all=True` |
| Security | `ask_corpus` re-checks per-citation source ACLs as defence in depth — Qdrant payload corruption cannot leak inaccessible documents |
| New query | `QdrantSearchClient.list_chunks_by_document` scrolls chunks in stable `chunk_index` order with the same group-id filter |
| Scope | No write tools, no MCP adapter, no Hermes runtime in this PR |

**CI fixes applied before merge:**
- Migration `a57fee5a821d`: changed `source_id` from `sa.String(32)` to `sa.Uuid()` to match `ingestion_sources.id` type (PostgreSQL FK mismatch)
- Fixed E501 line length violations in migration, `source_qa_repository.py`, test files
- Fixed mypy error: used `sqlalchemy.RowMapping` type instead of `Mapping` in `SourceQACheck.from_row`
- Ran `ruff format` on all changed files
- All unit tests pass (ruff, mypy strict, pytest)

**Agent router file:** `src/services/api/routers/agent.py` — new file, registered in `main.py`

Next action: #560 (Hermes MCP adapter) can start now that #592 is merged.

---

## 2026-05-30 — feat(#579): #544 S6 admin UI — COMPLETE, PR #591 merged

Status: Done — squash-merged to main (commit 2ab796d, branch deleted)
Source: issue #579 (S6 of #544), PR #591, Claude Code session

Admin UI and operator docs for the model provider registry. Completes the full #544 track (S1–S6 all on main).

| Area | Detail |
|---|---|
| Route | `/admin/model-providers` — lazy-loaded under appRoute |
| Provider list | Name, type badge, locality badge (local/self_hosted/external), enabled/disabled, credential_set state |
| Create/edit | Dialog with provider type, base URL, locality, credential (masked, type=password, autoComplete=new-password) |
| Delete | Explicit Dialog confirmation; warns all descriptors removed |
| Credential UX | `credential_set: boolean` only — plaintext never sent to frontend; `api_key_ref` nulled in `_provider_to_response` |
| Descriptor management | Per-provider dialog: list, create/edit/delete (Dialog confirmations); context window display in K |
| Task defaults | Table + add/edit/delete (Dialog confirmations); env fallback text when empty |
| Health/discover | Per-row Test + Discover buttons; results inline; consistent error display |
| Reload | `Reload` button triggers `POST /admin/model-providers/reload` in-process |
| Admin hub | `Cpu` icon card added to AdminHubPage |
| Operator docs | `docs/operations/model-providers.md` — Ollama, OpenAI-compat, LiteLLM, llama.cpp, locality/SSRF, credential handling, air-gapped deployment, task defaults with env fallback |
| Tests | 23 unit tests (23/23 pass) — list, CRUD, credential masking, descriptor, task defaults, health/discover, empty/loading/error, Add Task Default dialog |

Review findings fixed before merge:
- Blocking: "Add Task Default" button was a no-op (`setTaskDefaultEdit(null)` on already-null state); dialog guard `open={!!taskDefaultEdit}` never opened for new creates. Fixed via `addTdOpen` state.
- `api_key_ref` (internal credential store key name) traveled over the wire unnecessarily — nulled in `_provider_to_response`; dropped from frontend TypeScript type.
- `renderTestResult` variable `isOk` was named backwards (logic correct, name misleading) — renamed to `isError`.
- Mutation payload types tightened from `Record<string, unknown>` to `ModelProviderUpdatePayload` / `ModelDescriptorCreatePayload`.
- Descriptor and task-default deletes replaced inline `confirm()` with Dialog confirmations (consistent with provider delete).
- Whitespace churn on `LazyAdminUserDetailPage` in routes.tsx reverted.

---

## 2026-05-30 — feat(models): task-default resolver wired into consumers — #578 merged

Status: Done — PR #590 squash-merged to main (branch feat/task-default-resolver-578)
Source: issue #578 (S5 of #544), OpenCode + Claude Code session

Created `TaskDefaultResolver` with `resolve(task_type)` and `build_llm_provider(task_type)` interface. Wired into `app.state.task_default_resolver` at startup. Chat router, admin intelligence endpoints, and `IntelligenceWorker` use the resolver. Zero-row DB returns None — callers fall back to env/Settings behavior unchanged. `POST /admin/model-providers/reload` reloads both the provider registry and the resolver. 19 unit tests + 2 integration tests covering all fallback paths, disabled/missing provider/descriptor, reload, and no-secret-leakage.

| Area | Detail |
|---|---|
| Resolver | Loads task defaults + providers + descriptors + API keys at startup; `reload()` refreshes from DB |
| Fallback | No DB row → None; disabled/missing provider → None; disabled descriptor → None (env fallback) |
| LLM builder | `build_llm_from_resolution()` creates `OllamaClient` or `OpenAICompatibleLLMProvider` from a `TaskResolution` |
| Chat router | Resolves `chat` LLM, `utility` model, `reranker` model independently |
| Worker | Accepts optional `TaskDefaultResolver` in constructor; resolves `utility` model when not explicitly set |
| Secrets | API keys loaded at init, never logged; `mask_credential` pattern for safe display |
| Reload | `POST /admin/model-providers/reload` reloads both `ProviderRegistry` and `TaskDefaultResolver` in-process |

---

## 2026-05-30 — feat(admin): S4 admin provider registry API — #544 S4, PR #589 merged

Status: Done — PR #589 squash-merged to main (commit c06a72e, branch deleted)
Source: issue #577 (S4 of #544), PR #589, Claude Code session

Admin CRUD for model providers, descriptors, and task defaults. `CredentialStore` (Fernet-encrypted API keys), `ProviderRegistry` (startup adapter map), SSRF URL validation, and full integration test suite.

| Area | Detail |
|---|---|
| CredentialStore | Fernet encryption in `provider_credentials` table; `credential_set` bool in responses; plaintext never returned |
| SSRF | `validate_provider_url()` blocks RFC 1918 / loopback / link-local for `external` locality; `local`/`self_hosted` unrestricted |
| Admin API | Full CRUD at `/admin/model-providers`, `/admin/model-providers/{id}/descriptors`, `/admin/model-task-defaults` |
| Health/discover | `POST .../test` (10s timeout) + `POST .../discover` (15s timeout); admin-only |
| ProviderRegistry | Loads enabled providers at startup; wired to `app.state.provider_registry`; no consumers yet (pending #578) |
| Migration | `a0b1c2d3e4f5` — `provider_credentials` table; clean downgrade |
| Tests | 68 unit + 41 integration tests |

Review fix applied before merge (commit 62267ef):
- `_derive_fernet_key("dev-only")` was calling `Fernet.generate_key()` (random key per call) — fixed to use `_make_key("dev-only")` (deterministic SHA-256). Added round-trip regression test.

---

## 2026-05-30 — feat(models): generation provider adapters — #544 S3, PR #588 merged

Status: Done — PR #588 squash-merged to main (branch feat/generation-provider-adapters-576 deleted)
Source: issue #576 (S3 of #544), PR #588, Claude Code session

`OpenAICompatibleLLMProvider` now supports Bearer auth, SSE streaming, and clean error handling. Three review fixes applied before merge.

| Area | Detail |
|---|---|
| Auth | `LLM_API_KEY` env var → `Bearer` header; never logged — only key length at DEBUG |
| Streaming | `generate_stream()` parses `data: ...` SSE chunks, terminates on `[DONE]`, skips blank/bad-JSON lines |
| Errors | HTTP status, ConnectError, TimeoutException all caught and re-raised with log; malformed JSON returns `""` |
| Factory | `openai`, `litellm`, `llama-cpp` added to `_OPENAI_COMPATIBLE_PROVIDERS`; `openai` enforces `LLM_API_KEY` at startup |
| Reranker | `CrossEncoderEndpointReranker` added — TEI-compatible endpoint, identity fallback; unwired (factory wiring is #578) |
| Config | `llm_api_key: str = ""` added to `Settings` |
| Tests | 64 unit tests pass (streaming error paths, auth header present/absent, factory guard, reranker all covered) |

Review fixes applied before merge:
- `factory.py`: `ValueError` at startup when `LLM_PROVIDER=openai` and `LLM_API_KEY` is unset
- `llm_provider.py`: streaming `HTTPStatusError` handler uses `exc.response.status_code` (not the `with`-block variable)
- `test_llm_provider.py`: 3 streaming error tests + `test_factory_openai_requires_api_key` added

Remaining #544 slices:
- S4 #577 — admin provider registry API
- S5 #578 — task-default resolver/service wiring (also wires `CrossEncoderEndpointReranker`)

Next action: Pick up S4 (#577) — admin provider registry API.

---

## 2026-05-30 — feat(models): OpenAI-compatible embedding encoder — #544 S2, PR #587 merged

Status: Done — PR #587 squash-merged to main (branch feature/openai-embedding-encoder deleted)
Source: issue #575 (S2 of #544), PR #587, Claude Code session

`OpenAICompatibleEmbeddingEncoder` on main. No runtime behavior change — new provider only activates when `embedding_provider="openai-compatible"` is explicitly configured.

| Area | Detail |
|---|---|
| Encoder | `OpenAICompatibleEmbeddingEncoder` in `src/services/search/encoder.py` — calls `/v1/embeddings`, sorts by `index`, validates count |
| Config | `embedding_api_key: str = ""` added to `Settings` — optional, defaults empty |
| Factory | `build_encoder()` routes `embedding_provider="openai-compatible"` to new encoder; all existing paths unchanged |
| Tests | 16 encoder unit tests + 5 factory tests; all passing |

Review fixes applied before merge:
- Missing-`index` field in response entries now raises RuntimeError (was silently defaulting to 0)
- Count mismatch (server returns fewer embeddings than inputs) now raises RuntimeError (was silent truncation)
- Dead `.side_effect` assignment removed from `test_encode_raises_on_http_error`
- `test_encode_request_payload` mock fixed to return matching embedding count

Remaining #544 slices:
- S3 #576 — DONE (PR #588)
- S4 #577 — admin provider registry API
- S5 #578 — task-default resolver/service wiring

Next action: Pick up S4 (#577) — admin provider registry API.

---

## 2026-05-30 — feat(models): model provider registry foundation — #544 S1, PR #584 merged

Status: Done — PR #584 merged to main (squash commit 6860555)
Source: issue #574 (S1 of #544), PR #584, Claude Code session

Model provider registry foundation on main. No runtime behavior change.

| Area | Detail |
|---|---|
| Protocol | `BaseModelProviderAdapter`, `ProviderCapabilities`, `ProviderHealthResult` in `src/services/intelligence/adapters/base.py` |
| DB schema | `model_providers`, `model_descriptors`, `model_task_defaults` — locality/enabled/timestamps/unique constraints |
| Migration | `z0a1b2c3d4e5` — additive, empty tables, no seed data; downgrade is clean |
| Repository | `ModelProviderRepository` typed CRUD in `src/services/intelligence/model_provider_repository.py` |
| Tests | 32 unit + 4 migration tests |

Review fixes applied before merge (commit 0497647):
- `set_task_default` re-queries DB after upsert so returned `id` matches the actual row (not the discarded new UUID)
- Removed dead `repo` fixture from unit tests
- Dropped `frozen=True` from `ProviderCapabilities`/`ProviderHealthResult` (mutable `extra: dict` was inconsistent)

Remaining #544 slices:
- S2 #575 — embedding adapter extensions
- S3 #576 — generation/chat adapters
- S4 #577 — admin provider registry API
- S5 #578 — task-default resolver/service wiring

Next action: Pick up S2 (#575) — embedding adapter.

---

## 2026-05-30 — docs: canonical MVP runtime cleanup (#545 S5)

Status: Done
Source: issue #545 (S5), PR #???

Accurate project docs, smoke assumptions, and memory files for the canonical
MVP runtime: NiFi → Kafka/Redpanda → NiFiKafkaDrain → RabbitMQ →
parse/translate/embed/index → Meilisearch/Qdrant.

Changes:
- `docs/` — removed stale Elasticsearch, DB-poll, pipeline-worker, vector-worker,
  runner.py, vector_worker.py, INGEST_MODE references. Updated worker architecture
  docs to reflect RabbitMQ chain. Updated service tables, health checks, backup
  guidance, troubleshooting.
- `README.md` — Elasticsearch → Meilisearch in service lists.
- `scripts/` — removed ELASTIC_URL, INGEST_MODE, ELASTICSEARCH_VOLUME from
  setup-env.sh; removed ES from smoke-test.sh diagnostics; updated
  build-release-artifact.sh to reference meilisearch not ES; updated backup
  and restore scripts to remove ES guidance.
- `.github/workflows/smoke.yml` — removed `ES_JAVA_OPTS` env var.
- `docs/operators/ai-surfaces.md` — Elasticsearch → Meilisearch throughout.
- `docs/operations/pipeline-workers.md` — full rewrite for RabbitMQ worker chain.
- `docs/operations/production-compose.md` — removed ES service, volume, health
  check, backup, and troubleshooting references.
- `docs/memory/decisions.md` — updated BM25 graceful degradation entry.

Total issue #545 (S1–S5) complete:
- Legacy comments API removed.
- Meilisearch is the primary BM25 index.
- Elasticsearch removed entirely.
- DB-poll entrypoints and workers removed.
- Docs, smoke assumptions, and memory files updated.

Next action: #544 and #558 remain out of scope.

---

## 2026-05-30 — refactor(search): remove Elasticsearch entirely (#545 S2 + S3)

Status: Done — PR #573 merged to main
Source: issue #545, OpenCode session

Elasticsearch removed from the entire codebase:

| Area | Change |
|---|---|
| `src/services/search/elastic.py` | Deleted (231 lines) |
| `src/shared/config.py` | Removed `elastic_url` field |
| `pyproject.toml` | Removed `elasticsearch>=8.14,<9` dep |
| `docker-compose.yml`, `.airgap.yml` | Removed ES service, volume, ELASTIC_URL |
| `.env.example`, `.env.airgap.example` | Removed `ELASTIC_URL` |
| CI workflows (`smoke.yml`, `containers.yml`) | Removed ES from service lists |
| `src/services/api/main.py` | `create_app()` no longer accepts `es_client` |
| `src/services/api/readiness.py` | Removed ES probe |
| `src/services/api/routers/search.py` | Removed ES fallback `else` branch |
| `src/services/api/routers/admin/intelligence.py` | Removed `es_client` creation |
| Pipeline workers (`worker.py`, `slow_worker.py`, `runner.py`, `intelligence_consumer.py`) | Removed `es_client` param, ES `index_document` calls |
| `index_worker.py` | Meilisearch required (not optional); shadow-flag gating removed |
| `src/services/intelligence/worker.py` | Removed `_update_es_field` / `_update_es_fields` |
| Test files (15 files across unit/integration) | Removed ES mocks, imports, assertions; deleted `test_search_elastic.py` |

New test file: `tests/unit/test_index_consumer.py` (9 tests, ES-free IndexConsumer).

Key decision: Intelligence worker ES updates removed entirely — canonical data lives in DB via `IntelligenceRepository`; ES sync was a secondary write no longer needed with Meilisearch as primary.

Coverage threshold (90%) is not met — deleting `elastic.py` removed 231 lines of covered code. Pre-existing test failures (`test_admin_jobs_routes`, PostgreSQL uniquq violations) also reduce effective coverage.

Next action: #544 and #558 remain out of scope.

---

## 2026-05-29 — feat(rag): retrieval trace foundation — issue #537

Status: Done — PR #570 merged to main
Source: issue #537, PR #570

`RetrievalTrace`, `RetrievalStageTrace`, `RetrievalCandidateTrace` Pydantic models in `src/services/rag/trace_models.py`.
`_retrieve_chunks` returns `(chunks, stages)` with per-stage timing and counts for vector, BM25, metadata, translated, merge/dedup, rerank, and final_context.
`answer()` and `answer_stream()` both attach a `RetrievalTrace` to their output (field on `AnswerResponse`; `retrieval_trace` key in SSE `done` event).

Key constraints:
- Candidates carry only identifiers, scores, and allowed metadata — no raw chunk text, no prompts, no secrets
- `RetrievalCandidateTrace` is frozen (immutable)
- No persistence, no admin endpoint, no frontend UI — foundation only
- `retrieval_trace` is optional (`None` default) on `AnswerResponse` — existing callers unaffected

Deferred to future PRs: chat message persistence of trace, admin trace endpoint, frontend trace display (#538, #557).

---

## 2026-05-29 — ci(e2e): PR-gated Playwright and document-flow smoke — issue #547

Status: Done — PR #567 merged to main
Source: issue #547, PR #567

`.github/workflows/smoke.yml` adds two CI jobs triggered on `pull_request` (any path-matching PR) and `push` to `main`:

- **playwright**: installs Chromium (cached by `package-lock.json` hash), runs `npm run test:e2e:ci` (`playwright test --project=1440x900`), uploads `playwright-report/` artifact (7-day). Tests use `page.route` mock backend — no live API required.
- **document-flow**: starts Compose stack (postgres/kafka/ES/Qdrant/Meilisearch/migrate/api/frontend), waits for health, runs `SMOKE_MODE=ci scripts/dev/smoke_document_flow.sh`, uploads `tmp/smoke-document-flow-result.json` (30-day), tears down with `--volumes --remove-orphans`. ES capped at 512MB heap; `EMBEDDING_PROVIDER=""` disables embedding.

Key constraints enforced: no Ollama model pulls, no external LLM API keys, `COMPOSE_PROJECT_NAME` scoped per run_id to prevent collisions, `permissions: contents: read` only.

Review fixes applied (commit 9a926f9): added `test:e2e:ci` npm script (acceptance-criteria gap), removed redundant env vars in smoke step, expanded diagnostics to include `migrate`/`postgres`/`elasticsearch`, restricted push trigger to `main` only, added Playwright browser cache.

---

## 2026-05-29 — feat(admin): ingestion pipeline status API — issue #529 backend slice

Status: Done — PR #568 merged to main (commit 7f78d5b)
Source: issue #529, PR #568

`GET /admin/ingestion/status` and `GET /admin/ingestion/status/{document_id}` added.
Admin-only. Filters: status, source_id, since, limit, offset. Per-filter summary counts.
Trace endpoint returns jobs ordered by `created_at ASC`; 404 when no jobs exist.

Key constraints:
- `summary_by_status` is filter-scoped, not global totals
- `pipeline_jobs.document_id` has ON DELETE CASCADE — no "orphaned job" scenario in prod
- `limit` has no upper bound (consistent with `/admin/jobs`); hardening deferred

Frontend admin page (#529 frontend half) still deferred.

---

## 2026-05-29 — feat(chat): side-by-side source preview — issue #536

Status: Done — PR #559 merged to main (squash commit a598fed)
Source: issue #536, PR #559

Citation click-to-highlight shipped: clicking a chat citation opens an evidence
panel beside the chat that loads the document preview, passes the excerpt as
searchQuery for in-document highlighting, and navigates to the cited page in PDFs.

Key components: `EvidencePanel`, `PreviewWithHighlight`, `initialPage` prop on
`PdfViewer`/`PreviewPane`, `onOpenCitation` callback chain through chat components,
`selectedCitation` state on `ChatPage`, mobile fixed-overlay layout.

Post-merge fix (same squash): `PdfViewer initialPage` ref guard — original
effect had `pageNum` in deps, resetting navigation on every user page change.
Fixed with `appliedInitialPageRef` so jump fires once per citation value.

Deferred: URL query param sync for shareable citation views (component state only).

---

## 2026-05-29 — feat(search): source-scoped BM25 filtering — issue #552

Status: Done — PR #555 merged to main
Source: issue #552, OpenCode session

`metadata.source_id` added to Meilisearch ChunkMetadata payloads and indexed as a filterable attribute. `search_rag`, `search_rag_metadata`, and `search_rag_translated` accept `source_ids` and apply `metadata.source_id IN [...]` at query time. `_apply_scope_to_bm25` post-filters stale records that lack a matching `source_id`. Settings version bumped to 2; operators must backfill/reindex after deploy.

---

## 2026-05-29 — feat(smoke): document-flow smoke test foundation — issue #541

Status: Done — PR #554 merged to main
Source: issue #541, PR #554

`scripts/dev/smoke_document_flow.sh` implements 10-stage smoke test:
1. check_dependencies 2. api_health 3. frontend_health (skip if FRONTEND_URL unset)
4. doc_bootstrap (Docker-based fixture via `services.ops.smoke_bootstrap`, skip if Docker absent)
5. auth_login (skip if SMOKE_ADMIN_EMAIL/PASSWORD unset)
6. doc_ingest (POST /admin/ingestion/{source}/sync-now)
7. doc_search (extracts first document_id)
8. doc_preview (GET /preview/{id})
9. doc_text (GET /documents/{id}/text)
10. doc_download (GET /download/{id})

Key design choices:
- `SMOKE_MODE=ci` hard-fails on any stage, `SMOKE_MODE=local` collects all failures
- All data-dependent stages gracefully skip when prerequisites absent
- `SMOKE_DOCUMENT_ID` bypasses search-based doc discovery for preview/text/download
- `SMOKE_TIMEOUT_SECONDS=8` default with `--connect-timeout 5` on curl probes
- Machine-readable JSON result at `tmp/smoke-document-flow-result.json`
- New `docs/development/local-demo.md` documents the smoke workflow

Verified against real Docker Compose stack: 10/10 stages pass in 6s.
Issue #547 consumed this script in GitHub Actions `Smoke` workflow
(`.github/workflows/smoke.yml`): `document-flow` job starts the Compose stack
and runs with `SMOKE_MODE=ci`. Separate `playwright` job runs Playwright E2E
tests with mock backend. Both jobs upload result artifacts.

---

## 2026-05-29 — feat(extraction): Markdown Office extraction — merged PR #533

Status: Done — commit f6fbebb on main
Source: PR #533, issue #526

Native DOCX/PPTX/XLSX → Markdown converters added and enabled by default (`enable_markitdown=True`).
Preserves headings, tables, slide titles, bullets, and sheet structure for improved RAG chunking.
Each converter wraps the original extractor as fallback on empty output or error.
No new dependencies — implemented with python-docx/python-pptx/openpyxl (already in deps).
Disable with `ENABLE_MARKITDOWN=false`.

Key constraint: markitdown 0.1.x requires `magika<0.7`, conflicting with `magika>=1.0` (core dep).
Decision: implement natively rather than take the package dependency. See decisions.md.

---

## 2026-05-29 — test(extraction): pre-benchmark fixture corpus — merged PR #535

Status: Done — PR #535 merged to main
Source: PR #535, issue #527

Fixture corpus and assertion layer built as prerequisite for Onyx benchmark comparison:
- 5 fixture files added to `tests/fixtures/`: `sample-with-headings.docx`, `sample-multisheet.xlsx`, `wrong-extension.docx` (PPTX rename), `corrupt.pdf`, `encrypted.pdf`
- 15 unit tests in `tests/unit/test_extraction_fixture_corpus.py` covering extraction shape, failure-modes, and `has_extractor` boundary
- 1 integration test in `tests/integration/test_chunk_index_pipeline.py` verifying every Qdrant chunk payload has non-null integer `chunk_index`
- `PdfExtractor` now catches `FileNotDecryptedError` so encrypted PDFs return empty text instead of crashing

---

## 2026-05-29 — fix(security): ACL audit HIGH findings — regression tests added (#551)

Status: Done — tests on main, issue open (needs close)
Source: issue #551, Claude Code session

All H1–H5 HIGH findings and M1–M4 MEDIUM findings from `docs/context/acl-audit.md` were already fixed in source code. This session added the missing regression tests required by the acceptance criteria:

- H1 (`/search` admin bypass): `test_search_admin_passes_allow_all_to_backends` — asserts ES receives `is_admin=True` and Qdrant receives `allow_all=True`
- H2 (`/expertise` admin bypass): `test_expertise_admin_passes_allow_all_to_qdrant` — service-level test, `allow_all=True` forwarded to Qdrant
- H3 (orphaned vector leak): `test_search_drops_orphaned_qdrant_vector` — orphaned doc_id in Qdrant result not present in response
- H4 (subscription user-discovery leak): `test_expertise_subscription_excluded_when_no_group_overlap` — outsider subscriber excluded when no group overlap with requester
- H5 (`/related` transitive groups): `test_related_documents_router_uses_transitive_group_expansion` — router passes parent group ID to Qdrant for child-group user

Also fixed 2 pre-existing broken tests: `RelatedService(...)` calls in test_related_api.py were missing the required `job_repo` argument.

Pre-existing failures NOT caused by this work (already failing before):
- `test_search_es_failure_still_fails` — expects 500 but ES failures now degrade gracefully
- `test_excessive_limit_on_comments_returns_422` — expects 422 but gets 410 Gone for missing doc

Next action: Close issue #551. Fix the 2 pre-existing test failures in a follow-up.

---

## 2026-05-29 — roadmap: issues #526–#532 created from Onyx comparison (#525)

Status: Active
Source: Planning session, issue #525

7 issues opened following Onyx reference architecture comparison planning:
- #526 MarkItDown extraction — DONE (PR #533 merged)
- #527 Pre-benchmark fixture corpus + assertions — DONE (PR #535 merged)
- #528 LLM generation provider abstraction (OpenAI-compatible) — DONE (PR #538 merged)
- #529 Ingestion pipeline debug status page (admin UI) — backend slice DONE (PR #568 merged); frontend page deferred
- #530 Exact-location citation grounding (page/section) — DONE (PR #556 merged)
- #531 Connector credential store — status:deferred
- #532 Canonical metadata sidecar format — status:deferred

Next recommended order: #529 → #531 → #532.

---

## 2026-05-28 — dist: v0.2.0 air-gapped release artifact created

Status: Active — files written, not yet tarred or CI-built
Source: Claude Code session

`dist/tomorrowland-release-v0.2.0/` created from rc3 baseline with these changes:
- `release-manifest.json`: version `v0.2.0`, commit `16ff0ab`, image tags `v0.2.0`, `ollama_data` split into `ollama_llm_data` + `ollama_embed_data`, new `ollama_model_bundles` section for all 3 bundles.
- `docker-compose.airgap.yml`: single `ollama` → `ollama-llm` (port 11434) + `ollama-embed` (port 11435); `EMBEDDING_PROVIDER` defaults to `ollama`; `api` depends_on both.
- `.env.airgap.example`: version stamped, `EMBEDDING_PROVIDER=ollama` set, RC3 comments removed.
- `README-airgap.txt`: all 3 bundles listed with sizes and target containers.
- `docs/air-gapped-deployment.md`: mistral → qwen3.5:35b-a3b throughout; 3-bundle table; per-container load commands; port 11435 for embedding validation; updated Qdrant collection example (`documents_v4096`).
- `docs/air-gapped-upgrade.md` + `docs/production-compose.md`: same model/volume updates.
- `scripts/validate-ollama-model.sh`: default `mistral` → `qwen3.5:35b-a3b`.
- `scripts/load-ollama-model-bundle.sh`: usage updated for `--compose-service` flag.
- `checksums.txt`: regenerated for all changed files.

Three v0.2.0 bundle metadata dirs created:
- `dist/tomorrowland-ollama-bundle-qwen3.5-35b-a3b-v0.2.0/` — model-manifest.json + README (target: `ollama-llm`)
- `dist/tomorrowland-ollama-bundle-qwen3-14b-v0.2.0/` — model-manifest.json + README (target: `ollama-llm`)
- `dist/tomorrowland-ollama-bundle-qwen3-embedding-8b-v0.2.0/` — model-manifest.json + README (target: `ollama-embed`)

Remaining build-time step: CI must rebuild `images/tomorrowland-images.tar` with `v0.2.0` image tags, then `sha256sum images/tomorrowland-images.tar >> checksums.txt`, then produce `tomorrowland-release-v0.2.0.tar.gz` and split image parts.

Key architectural decision: `ollama-llm` and `ollama-embed` are now separate Compose services with separate volumes (`ollama_llm_data`, `ollama_embed_data`). Operators upgrading from rc3 must re-load model weights into both containers.

---
