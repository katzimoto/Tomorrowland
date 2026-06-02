# Tomorrowland Handoffs

Shared record for concise cross-agent handoffs that remain useful after a chat or tool session ends.

## 2026-06-01 — review+fix+merge of #622, #623, #624 (bug-bounty + pipeline)

Status: Done — all three squash-merged to main; 2 watch items carry forward
Source: PRs #622 (d3abd92), #623 (49d7470), #624 (cec926d) — Claude Code session

**Done:** reviewed each PR, fixed the blocking findings, verified (ruff/mypy + targeted tests), squash-merged. Details + review fixes in `current-state.md` (same date); durable decisions (QA removal, async cycle-guard convention) in `decisions.md` (same date).

**Watch (carry forward):**
- Branch `fix/bug-bounty-rounds-1-3` (katzimoto) reverted the airgap Ollama setup (reverts #621) in BOTH #622 and #623, undocumented each time, and omitted its largest changes from both descriptions. On any further PR from this branch: reset `docker-compose.airgap.yml` + `scripts/{build-release,validate}-airgap*.sh` to main; verify the diff, not the description.
- Open question: is the `translate*→index` + `embed→index` double-publish intentional (index-resilience when embed is skipped) or a double-fire bug? Unresolved; left intact in #624.

**Next agent prompt:**
> #622/#623/#624 are on main (d3abd92 / 49d7470 / cec926d). Local `main` may be behind — `git pull`. Reviewing another PR from `fix/bug-bounty-rounds-1-3`? Re-check the airgap files against main first. Then resolve the double-index question or pick the next issue from the release queue in AGENTS.md.

---

## 2026-05-31 — feat(auth): LDAP group mapping via live DC search — #582, PR #601

Status: Done — squash-merged to main (commit ea7f65d), branch deleted, issue #582 closed
Source: issue #582, PR #601, Claude Code session

**Goal:** Allow admins to search LDAP/DC groups live and explicitly map selected groups to existing Tomorrowland groups, without mirroring all LDAP groups or using raw LDAP groups in source/document ACLs.

**Changed files:**
- `src/services/auth/ldap_client.py` (new) — `LdapClient` + `search_groups()`; RFC 4515 escaping, service-account bind, timeout/limit, ephemeral results
- `src/services/auth/ldap_group_mapping_repository.py` (new) — CRUD; `get_mapped_tomorrowland_group_ids()` for auth integration
- `src/services/api/routers/admin/ldap.py` (new) — 4 admin-only endpoints with audit logging
- `src/services/auth/repository.py` — `upsert_ldap_user()` resolves groups via explicit mappings only; raw LDAP DNs no longer reach `set_user_groups()`
- `src/services/api/schemas.py` — `LdapGroupSearchResult` (field `dn`), `CreateLdapGroupMappingRequest`, `LdapGroupMappingResponse`
- `src/shared/config.py` — 6 new LDAP group search settings
- `migrations/versions/l1m2n3o4p5q6_add_ldap_group_mappings.py` (new)
- `frontend/src/features/admin/AdminLdapPage.tsx` (new) — search, map dialog, mappings table, delete confirmation; EN + HE i18n
- `tests/unit/test_ldap_group_mapping.py` (new) — 14 tests

**Review bugs fixed (commit c845406) before merge:**
- `setup-env.sh`: `LDAP_BIND_PASSWORD=""` and `if [[ ... ]]` collapsed onto one line — broken bash
- Schema/client: `distinguished_name` → `dn` — frontend expected `dn`; DN column was blank and POST sent `ldap_dn: undefined` → 422
- `AdminLdapPage`: removed dead Limit TextInput — backend ignores `?limit=N`

**Key invariants:**
- `search_groups()` makes zero DB writes — results are ephemeral
- Only explicit `ldap_group_mappings` rows grant Tomorrowland group membership at login
- Raw LDAP group DNs never appear in source/document ACL tables
- Deleting a mapping does not cascade to the Tomorrowland group (`ondelete="RESTRICT"`)

**Next agent prompt:**
> #582 is on main (PR #601, commit ea7f65d). LDAP group mapping is live at `/admin/ldap`. Pick up the next issue from the release queue in AGENTS.md.

---

## 2026-05-30 — test(agents): permission regression tests for researcher queries — #562, PR #598

Status: Done — PR #598 squash-merged to main (commit 0462d30), branch deleted
Source: issue #562, PR #598, Claude Code session

**Goal:** Add regression coverage proving the researcher REST API and MCP tools follow the same access rules as the rest of the app and do not leak inaccessible documents.

**Changed files:**
- `tests/integration/test_agent_api.py` — +273 lines: cross-user isolation (4 tests), source filter scope (2 tests), over-limit safety (1 test), `_FakeMeiliProvider` UUID normalisation fix
- `tests/unit/test_mcp_server.py` — +135 lines: `TestMCPAuthorizationParity` class (24 tests across all 6 tools × 401/403, plus targeted 403/429 data-leak checks)

**Key invariants verified:**
- `user@example.com` (group `users`) and `other@example.com` (group `other`) have symmetric, disjoint access across all four ACL-enforcing endpoints
- Source filter for an existing-but-inaccessible source returns no docs from that source (ACL defence-in-depth)
- 429 response body never contains document IDs or auth tokens
- All 6 MCP tools translate 401/403 to static safe messages; 403 response body content (doc IDs) is never forwarded
- No product code changed — test-only PR

**Infrastructure bug fixed:**
- `_FakeMeiliProvider.search` returned document IDs as 32-char hex strings (SQLite `db_uuid` format). The router builds its `docs` dict with standard dashed-UUID string keys, so `r.document_id in docs` was always False — silently making every BM25-only search test return empty results. Fixed `str(r[0])` → `str(UUID(r[0]))`. Existing tests were unaffected because they relied on the Qdrant mock path, which already used proper UUID strings.

**Next agent prompt:**
> #562 is on main (PR #598, commit 0462d30). All researcher API and MCP permission regression tests are in place. Next candidates: #563 (Hermes workflow docs) or #564 (air-gapped behavior).

---

## 2026-05-30 — feat(agents): audit logging and usage limits — #561, PR #595

Status: Done — PR #595 squash-merged to main (commit 9d28657), branch deleted
Source: issue #561, PR #595, Claude Code session

**Goal:** Add safe audit logging and per-user rate limiting to the six `/api/agent/v1/*` researcher endpoints. MCP inherits both via REST proxying.

**Changed files:**
- `src/shared/rate_limit.py` (new) — `AgentRateLimiter`: in-process sliding window, two independent per-user buckets (general + ask_corpus), fail-closed on invalid config
- `src/shared/config.py` — 4 new settings: `AGENT_RATE_LIMIT_ENABLED/WINDOW_SECONDS/CALLS_PER_WINDOW/ASK_CORPUS_CALLS_PER_WINDOW`
- `src/services/api/main.py` — `AgentRateLimiter` instantiated in `create_app`, stored as `app.state.agent_rate_limiter`
- `src/services/api/routers/agent.py` — `_agent_audit_log()` helper + rate-check + audit call in all 6 endpoints
- `src/services/mcp/server.py` — HTTP 429 added to `_translate_error`
- `tests/unit/test_rate_limit.py` (new) — 18 tests; `tests/unit/test_mcp_server.py` — 429 case
- `tests/integration/test_agent_api.py` — 8 new tests; `_StubLLM.model` fixed from instance attr to `@property`
- `docs/operators/ai-surfaces.md` — operator reference section added; `CHANGELOG.md` — entry added

**Key invariants:**
- Audit log never contains raw query/question text, document content, JWTs, auth headers, or secrets
- MCP tools do NOT have separate audit events or rate limits — REST-side enforcement covers both paths automatically
- Limits are in-memory only — reset on restart; not synchronized across replicas

**Next agent prompt:**
> #561 is on main (PR #595, commit 9d28657). Researcher API has audit logging and per-user rate limits. MCP inherits both. Normal search/RAG paths unaffected. Next candidates: #562 (permission regression test expansion) or #563 (Hermes workflow docs).

---

## 2026-05-30 — feat(admin): source profiles P1 — #585, PR #594

Status: Done — PR #594 squash-merged to main (commit cf1d41d), branch deleted
Source: issue #585, PR #594, Claude Code session

**Goal:** Allow admins to configure per-source strategy profiles (domain type,
chunking/retrieval/extraction strategies) with a full lifecycle: draft → active →
deprecated. Wire the active profile into `IntelligenceWorker` for future strategy
routing.

**Key invariants:**
- One active profile per source enforced atomically in `activate_profile` (previous active auto-deprecated)
- Active profiles cannot be deleted (must deprecate first)
- `model_policy_provider_id` FK uses `ON DELETE SET NULL`
- Worker integration is logging-only — strategy dispatch deferred to future work
- `GET /admin/source-profiles/active/{source_id}` returns 404 when no active profile exists

**Verification:** ruff clean, ruff format clean, mypy clean on changed files, 22 unit + 20 integration tests pass.

**Next agent prompt:**
> #585 source profiles P1 is on main (PR #594, commit cf1d41d). Admin API at `/admin/source-profiles` (8 endpoints). Strategy dispatch — mapping profile fields to actual chunking/retrieval/extraction behavior in the intelligence worker — is the next piece.

---

## 2026-05-30 — feat(agents): Hermes MCP adapter for researcher API — #560, PR #593

Status: Done — PR #593 merged to main (squash), branch `feature/mcp-adapter-560` deleted
Source: issue #560, PR #593, Claude Code session

**Goal:** Add an MCP server that exposes Tomorrowland researcher tools to Hermes/MCP clients by forwarding all tool calls to the permissioned `/api/agent/v1/*` API (#558). No direct DB/storage access.

**Changed files:**
- `src/services/mcp/__init__.py` (new) — package init; exports `create_mcp_server`, `run_server`, `main`
- `src/services/mcp/client.py` (new) — `TomorrowlandClient` HTTP client wrapping all 6 `/api/agent/v1/*` endpoints
- `src/services/mcp/server.py` (new) — FastMCP server with 6 tools; `_sanitize_log_env()` for secrets protection
- `src/shared/config.py` — added `MCPConfig` inner class (`tomorrowland_api_url`, `tomorrowland_api_key`, `mcp_host`, `mcp_port`, `api_timeout`)
- `pyproject.toml` — `mcp[cli]>=1.27` dep; `tomorrowland-mcp-server` console_scripts entry point
- `tests/unit/test_mcp_server.py` (new) — 45 tests covering all tools, auth forwarding, error translation, log sanitization, no direct store imports
- `docs/operations/mcp-adapter.md` (new) — operations doc with Hermes config snippet, auth, troubleshooting
- `CHANGELOG.md` — #560 entry added

**Verification:** ruff clean, mypy strict clean, 45/45 tests pass.

**Next agent prompt:**
> PR #593 is on main — the MCP adapter is live at `tomorrowland-mcp-server`. Use `TOMORROWLAND_API_URL=http://localhost:8000 TOMORROWLAND_API_KEY=<token> tomorrowland-mcp-server`. Pick up #561 (audit/usage limits) or #562 (permission regression expansion) next.

---

## 2026-05-30 — feat(agents): permissioned researcher API endpoints — #558/#592

Status: Done — PR #592 squash-merged to main (branch deleted)
Source: issue #558, PR #592, Claude Code session

**Goal:** Add read-only `/api/agent/v1` API surface that future Hermes/MCP clients (#560) can call through the same source/document ACL as normal users.

**Changed files:**
- `src/services/api/routers/agent.py` (new) — 6 endpoints: `search_documents`, `get_document`, `get_passages`, `ask_corpus`, `get_related_documents`, `list_facets`
- `src/services/api/main.py` — router registered at `/api/agent/v1`

**Security:**
- Every endpoint enforces `AuthRepository.get_effective_group_ids` and `assert_doc_access`
- Admin bypass uses `allow_all=True` path (standard)
- `ask_corpus` re-checks per-citation source ACLs as defence in depth
- `QdrantSearchClient.list_chunks_by_document` filters by group IDs

**CI fixes applied before merge:**
- Migration `source_id` type: `String(32)` → `Uuid()` to match `ingestion_sources.id` (PostgreSQL FK type mismatch)
- E501 line length violations fixed in migration, `source_qa_repository.py`, test files
- mypy fix: `RowMapping` type instead of `Mapping` in `SourceQACheck.from_row`
- `ruff format` applied to all changed files

**Verification:** ruff clean, mypy strict clean, all unit tests pass.

**Next agent prompt:**
> PR #592 is on main — the `/api/agent/v1` endpoints are live. Pick up #560 (Hermes MCP adapter) next: build an MCP server process that wraps each endpoint as an MCP tool. The endpoint schemas in `agent.py` are the source of truth for tool input/output shapes.

---

## 2026-05-30 — feat(#579): #544 S6 admin UI — COMPLETE, PR #591

Status: Done — squash-merged to main (commit 2ab796d, branch deleted)
Source: issue #579 (S6 of #544), PR #591, Claude Code session

**Goal:** Admin UI for model providers, model descriptors, and task defaults. Operator docs. Completes #544.

**Changed files:**
- `frontend/src/api/admin.ts` — 15 API methods + TypeScript types for provider/descriptor/task-default endpoints; `api_key_ref` dropped from `ModelProvider` interface
- `frontend/src/app/routes.tsx` — `/admin/model-providers` route added
- `frontend/src/features/admin/AdminHubPage.tsx` — `Cpu` icon card added
- `frontend/src/features/admin/AdminModelProvidersPage.tsx` (new) — full CRUD with confirmation dialogs, masked credentials, test/discover actions, descriptor dialog, task default section, reload button
- `frontend/src/features/admin/AdminModelProvidersPage.test.tsx` (new) — 23 unit tests
- `docs/operations/model-providers.md` (new) — operator guide covering all provider types
- `CHANGELOG.md` — S6 entry added
- `src/services/api/routers/admin/model_providers.py` — `api_key_ref=None` in `_provider_to_response`

**Review findings fixed before merge (commit 30d2e5c):**
- Blocking: `addTdOpen` state added; "Add Task Default" button was calling `setTaskDefaultEdit(null)` (no-op) so dialog never opened for new creates
- `api_key_ref` nulled in backend response; removed from TypeScript `ModelProvider` interface
- `isOk` renamed `isError` in `renderTestResult` (logic correct, name was inverted)
- Mutation types tightened from `Record<string, unknown>` to concrete payload interfaces
- Descriptor and task-default deletes converted from `confirm()` to Dialog confirmations

**Key invariants:**
- `credential_set: boolean` is the only credential signal sent to frontend; `api_key_ref` stays backend-only
- All destructive actions use Dialog confirmation
- Task default dialog serves both create (`addTdOpen=true`) and edit (`taskDefaultEdit=<row>`) paths

**#544 is fully complete. S1–S6 all on main.**

**Next agent prompt:**
> #544 is done — all six slices on main. Admin UI at `/admin/model-providers`. Operator docs at `docs/operations/model-providers.md`. Pick up from the release queue in AGENTS.md.

---

## 2026-05-30 — feat(models): S5 task-default resolver wired into consumers — #544 S5, PR #590

Status: Done — squash-merged to main (commit 65f0094, branch deleted)
Source: issue #578 (S5 of #544), PR #590, Claude Code session

**Goal:** Add `TaskDefaultResolver`, wire it into `app.state`, and update chat router, admin intelligence endpoints, and `IntelligenceWorker` to resolve LLM providers from DB-backed `model_task_defaults`. Zero-row DB must leave existing env/Settings behavior unchanged.

**Changed files:**
- `src/services/intelligence/task_defaults.py` (new) — `TaskDefaultResolver`, `TaskResolution`, `build_llm_from_resolution()`
- `src/services/api/main.py` — `TaskDefaultResolver` wired to `app.state.task_default_resolver` at startup
- `src/services/api/routers/admin/model_providers.py` — added `POST /admin/model-providers/reload`
- `src/services/api/routers/admin/intelligence.py` — passes resolver to `IntelligenceWorker`
- `src/services/api/routers/chat.py` — resolves `chat` LLM, `utility` model, `reranker` model via resolver
- `src/services/intelligence/worker.py` — accepts optional `resolver: TaskDefaultResolver | None`
- `src/services/intelligence/__init__.py` — exports `TaskDefaultResolver`, `TaskResolution`, `build_llm_from_resolution`
- `tests/unit/test_task_default_resolver.py` (new) — 19 tests
- `tests/integration/test_provider_wiring.py` (new) — 2 tests

**Key invariants:**
- `resolve()` returns `None` for: no DB row, missing/disabled provider, or configured-but-disabled descriptor → all callers fall back to `app.state.llm_provider` / `Settings`
- Deleted descriptor → `ON DELETE SET NULL` makes `model_descriptor_id=NULL`, treated as "no descriptor configured" (provider used with empty/default model name)
- `app.state.llm_provider` remains set — not removed; other callers unaffected during transition
- `POST /admin/model-providers/reload` reloads both `ProviderRegistry` and `TaskDefaultResolver` in-process; cross-process reload still requires rolling restart

**Review fixes applied before merge:**
- `resolve()` changed to return `None` (not `TaskResolution(model_name=None)`) when configured descriptor is disabled — prevents `build_llm_from_resolution()` from creating a provider with `model=""` that bypasses the env fallback chain
- Added `POST /admin/model-providers/reload` (was missing from original PR)
- Added `tests/integration/test_provider_wiring.py` (zero-row compat + reload round-trip)
- CHANGELOG test count corrected; stale branch name in `current-state.md` fixed

**Deferred (not in this slice):**
- Encoder resolution (`get_encoder()` / `"embed"` task type) — chat router still calls `build_encoder(settings)` directly
- Frontend admin UI — #579
- Cross-process reload for workers — #432
- `slow_worker` / `embed_worker` wiring to registry

**Next agent prompt:**
> S5 (#544/#578) is on main. The `TaskDefaultResolver` is wired into app state and all API-layer consumers. Next slice is the frontend admin UI (#579) for managing model providers and task defaults, or pick up the embedding/encoder resolution gap if that is higher priority. Do not remove `app.state.llm_provider` yet — workers still read it directly.

---

## 2026-05-30 — feat(admin): S4 admin provider registry API — #544 S4, PR #589

Status: Done — merged to main (commit c06a72e, branch deleted)
Source: issue #577 (S4 of #544), PR #589, Claude Code session

**Goal:** Admin CRUD for model providers, model descriptors, and model task defaults. Encrypted credential store, SSRF URL validation, `ProviderRegistry` startup wiring.

**Changed files:**
- `migrations/versions/a0b1c2d3e4f5_add_provider_credentials_table.py` (new)
- `src/services/intelligence/credential_store.py` (new) — `CredentialStore`, `mask_credential`
- `src/services/intelligence/ssrf_validation.py` (new) — `validate_provider_url`, `validate_locality`
- `src/services/intelligence/provider_registry.py` (new) — `ProviderRegistry`
- `src/services/api/routers/admin/model_providers.py` (new) — full admin CRUD + test + discover
- `src/services/intelligence/model_provider_models.py` — added `ModelProviderResponse` (credential_set bool, no plaintext)
- `src/shared/config.py` — `credential_store_key: str = ""`
- `src/services/api/main.py` — `ProviderRegistry` wired to `app.state.provider_registry`; admin router registered
- `src/services/intelligence/__init__.py` — exports `CredentialStore`, `ProviderRegistry`, `mask_credential`, `validate_provider_url`
- `tests/integration/test_model_provider_api.py` (new) — 41 tests
- `tests/unit/test_credential_store.py` (new) — 14 tests
- `tests/unit/test_provider_registry.py` (new) — 7 tests
- `tests/unit/test_ssrf_validation.py` (new) — 20 tests

**Review fix applied (commit 62267ef on PR branch before merge):**
- `_derive_fernet_key("dev-only")` called `Fernet.generate_key()` — random key per `CredentialStore` instantiation, so credentials written in one request were unreadable in any subsequent request. Fixed to route through `_make_key("dev-only")` (deterministic SHA-256). Added `test_dev_only_key_is_deterministic_across_instances` regression test.

**Key invariants:**
- `ModelProviderResponse` exposes `credential_set: bool` and `api_key_ref` (opaque key name) — never plaintext credential
- SSRF validation runs at create/update time; `external` locality rejects RFC 1918, loopback, link-local, IPv6 private
- `ProviderRegistry._build_adapter()` returns `None` for all provider types — no concrete adapters yet (pending #578)
- `app.state.provider_registry` is populated at startup but no consumers read from it until #578

**Open non-blocking notes (deferred to #578):**
- `ProviderRegistry` goes stale after admin CRUD — add `request.app.state.provider_registry.reload()` at end of mutating endpoints when wiring consumers
- `test`/`discover` endpoints follow HTTP redirects by default — consider no-redirect handler
- `api_key_ref` (opaque key name) is exposed in `ModelProviderResponse` — could be omitted if callers don't need it

**Next agent prompt:**
> S4 (#544/#577) is on main. Pick up S5 (#578) — task-default resolver/service wiring. This wires `app.state.provider_registry` into the chat, RAG, and embedding consumers so they select providers from the DB task-default table instead of env vars. Also wires `CrossEncoderEndpointReranker` (already on main from S3). The `ProviderRegistry` in `app.state.provider_registry` is ready to use. Do not add frontend UI (#579) in this slice.

---

## 2026-05-30 — feat(models): generation provider adapters — #544 S3, PR #588

Status: Done — merged to main (branch deleted)
Source: issue #576 (S3 of #544), PR #588, Claude Code session

**Goal:** Extend `OpenAICompatibleLLMProvider` with Bearer auth + SSE streaming; add `CrossEncoderEndpointReranker`; register `openai`/`litellm`/`llama-cpp` provider names.

**Changed files:**
- `src/services/intelligence/factory.py` — `_OPENAI_COMPATIBLE_PROVIDERS` frozenset; `openai` startup guard (ValueError when `LLM_API_KEY` missing)
- `src/services/intelligence/llm_provider.py` — `_build_headers()`, `api_key` param on `__init__`, full SSE `generate_stream()`, error handling on both paths
- `src/services/rag/reranker.py` — `CrossEncoderEndpointReranker` (unwired; factory wiring deferred to #578)
- `src/shared/config.py` — `llm_api_key: str = ""`
- `tests/unit/test_llm_provider.py` — streaming error path tests, auth tests, factory guard test
- `tests/unit/test_rag_reranker.py` — full endpoint reranker coverage
- `CHANGELOG.md` — Unreleased entries for S3

**Review fixes (commit cff1239 on PR branch before merge):**
- Factory: `ValueError` at startup when `LLM_PROVIDER=openai` and `LLM_API_KEY` unset
- Streaming error handler: `exc.response.status_code` instead of `response.status_code` (scope dependency)
- Tests: streaming error paths (HTTPStatusError, ConnectError, TimeoutException) + `test_factory_openai_requires_api_key`

**Key invariants:**
- Default `llm_provider=""` → `"ollama"` → `OllamaClient` — unchanged
- `LLM_API_KEY` unset → no `Authorization` header on any request
- API keys and full prompts never logged; only key length at DEBUG and prompt length at DEBUG
- `CrossEncoderEndpointReranker` identity-fallback on any error — RAG pipeline never blocked

**Next agent prompt:**
> S3 (#544/#576) is on main. Pick up S4 (#577) — admin provider registry API. This adds CRUD REST endpoints for the `model_providers` / `model_descriptors` / `model_task_defaults` tables laid down in S1. The `ModelProviderRepository` in `src/services/intelligence/model_provider_repository.py` is the data layer. Do not implement frontend UI (#579) or service wiring (#578) in this slice.

---

## 2026-05-30 — feat(models): model provider registry foundation — #544 S1, PR #584

Status: Done — merged to main
Source: issue #574 (S1), PR #584, Claude Code session

**Goal:** Lay the schema and protocol foundation for multi-provider model registry. No runtime behavior change.

**Changed files:**
- `migrations/versions/z0a1b2c3d4e5_add_model_provider_registry_tables.py` (new)
- `src/services/intelligence/adapters/__init__.py` (new)
- `src/services/intelligence/adapters/base.py` (new) — `BaseModelProviderAdapter` Protocol, `ProviderCapabilities`, `ProviderHealthResult`
- `src/services/intelligence/model_provider_models.py` (new) — Pydantic CRUD models
- `src/services/intelligence/model_provider_repository.py` (new) — `ModelProviderRepository`
- `tests/unit/test_model_provider_repository.py` (new) — 32 tests
- `tests/test_migrations.py` — 4 new migration tests appended
- `CHANGELOG.md` — Unreleased entry added

**Review fixes (commit 0497647 on PR branch before merge):**
- `set_task_default`: ON CONFLICT upsert returned freshly generated UUID instead of existing row id — fixed by re-querying with `get_task_default(task_type)` after execute
- `test_set_task_default_upsert`: added `assert upserted.id == original.id` to lock in fix
- Removed dead `repo` fixture (connection closed before any test could use it)
- Dropped `frozen=True` from `ProviderCapabilities` / `ProviderHealthResult` — mutable `extra: dict` made frozen inconsistent

**Verification:** 32 unit tests passed; 4 migration tests passed; ruff/mypy clean per PR body.

**Next agent prompt:**
> S1 (#544/#574) is on main. Pick up S2 (#575) — embedding adapter extensions. The `BaseModelProviderAdapter` protocol in `src/services/intelligence/adapters/base.py` is the extension point; add an `EmbeddingAdapter` sub-protocol there and implement the Ollama embedding adapter as the first concrete class. Do not touch service wiring (S5/#578).

---

## 2026-05-29 — ci(e2e): PR-gated smoke workflows — issue #547, PR #567

Status: Done — merged to main
Source: issue #547, PR #567, Claude Code review session

**Goal:** Wire #541's `smoke_document_flow.sh` into GitHub Actions and add Playwright E2E CI.

**Changed files:**
- `.github/workflows/smoke.yml` (new) — `playwright` + `document-flow` jobs; path-filtered triggers; Playwright browser cache; diagnostics cover migrate/postgres/elasticsearch; teardown `if: always()`
- `frontend/package.json` — `test:e2e` + `test:e2e:ci` scripts added
- `docs/development/testing.md` — local smoke commands documented
- `docs/development/local-demo.md` — #547 placeholder replaced
- `CHANGELOG.md` — Unreleased entry added

**Review findings applied (commit 9a926f9):**
- Missing `test:e2e:ci` script (acceptance-criteria gap) — added
- Redundant step-level env vars — removed
- Diagnostics expanded to include `migrate`, `postgres`, `elasticsearch`
- Push trigger restricted to `main` only (was `feature/**`/`fix/**` too)
- Playwright browser cache added (`actions/cache@v4` keyed on `package-lock.json`)

**Watch:** Confirm `http://localhost:8080/health` exists as a real frontend endpoint — if missing, the health-wait loop burns the 35-minute budget on every run.

---

## 2026-05-29 — feat(admin): ingestion pipeline status UI (#529 frontend slice)

Status: Done — PR #569 merged to main
Source: issue #529, PR #569, commit c068d6e

**Goal:** Admin `/admin/ingestion` page with summary cards, filter bar, paginated job table, per-document trace expansion, and requeue action.

**Review fixes applied (c068d6e):**
- `onSuccess` now checks `result.requeued`: warning toast when 0 dead-letter jobs found, count-bearing success toast otherwise.
- 3 new tests added for requeue: success path, requeued=0 warning, rejection error toast. 19 tests total, all passing.

**Issue #529 closed** — both backend (PR #568) and frontend (PR #569) slices merged.

---

## 2026-05-29 — feat(admin): ingestion pipeline status API (#529 backend slice)

Status: Done — PR #568 merged to main (commit 7f78d5b)
Source: issue #529, PR #566 (closed), PR #568

**Goal:** Admin-only endpoints for operator visibility into pipeline job status.

**Routes:**
- `GET /admin/ingestion/status` — list jobs with status/source_id/since/limit/offset filters + per-filter summary
- `GET /admin/ingestion/status/{document_id}` — per-document trace ordered by created_at ASC; returns 404 when no jobs

**Key design notes:**
- `summary_by_status` is filter-scoped, not global totals — consumers expecting global breakdown should be aware
- `limit` has no upper bound (consistent with `/admin/jobs`); hardening deferred
- `last_error` returned raw via `_sanitize_error` from `jobs.py` (already truncated/sanitized upstream); safe
- `pipeline_jobs.document_id` has `ON DELETE CASCADE` — "deleted document with surviving jobs" cannot occur in production PostgreSQL; the defensive queries are harmless but the scenario is impossible

**Changed files:**
- `src/services/pipeline/jobs.py` — `list_ingestion_status()`, `list_document_trace()`
- `src/services/api/schemas.py` — `IngestionStatusJob`, `IngestionStatusResponse`, `DocumentTraceJob`, `DocumentTraceResponse`
- `src/services/api/routers/admin/ingestion_status.py` (new)
- `src/services/api/main.py` — router registration
- `tests/unit/test_pipeline_jobs.py` — 7 new tests
- `tests/integration/test_admin_ingestion_status.py` — 8 new tests
- `CHANGELOG.md`

**Review blocker resolved:** Original PR #566 targeted wrong base branch (`feat/536-side-by-side-preview` instead of `main`) and had two tests documenting a cascade-impossible scenario. Both fixed in commit 75db186; new PR #568 targets main.

**Next agent prompt:**
> #529 backend slice is on main. Pick up the frontend admin page for #529, or the next queued issue.

---

## 2026-05-29 — fix(security): ACL regression tests — issue #551

Status: Done — tests merged to main; issue open
Source: issue #551, Claude Code session

**Goal:** Prove the H1–H5 ACL code fixes (already in source) with regression tests.

**Changed files:**
- `tests/integration/test_search_api.py` — added `test_search_admin_passes_allow_all_to_backends` (H1), `test_search_drops_orphaned_qdrant_vector` (H3)
- `tests/integration/test_related_api.py` — fixed 2 broken `RelatedService(...)` calls missing `job_repo`; added `test_expertise_admin_passes_allow_all_to_qdrant` (H2), `test_expertise_subscription_excluded_when_no_group_overlap` (H4), `test_related_documents_router_uses_transitive_group_expansion` (H5); new imports: `TestClient`, `patch`, `hash_password`, `PipelineJobRepository`
- `CHANGELOG.md` — Unreleased entry added

**Verification:** 26 passed (2 excluded pre-existing failures); ruff clean; mypy clean.

**Pre-existing test failures (not caused here):**
- `test_search_es_failure_still_fails` — expects 500; ES degradation now returns 200 with empty results
- `test_excessive_limit_on_comments_returns_422` — expects 422; gets 410 Gone for missing doc

**Next agent prompt:**
> Close issue #551. Fix the 2 pre-existing test failures (`test_search_es_failure_still_fails`, `test_excessive_limit_on_comments_returns_422`) in a focused patch PR. Then pick up #529 (admin ingestion debug page) or #552 (BM25 source-scope filtering).

---

## 2026-05-29 — feat(intelligence): LLM provider abstraction (#528)

Status: Done — PR open
Source: issue #528, Claude Code session

**Goal:** Allow operators to use any OpenAI-compatible local inference server (LM Studio, llama.cpp, vLLM) instead of Ollama-only for LLM generation. Air-gapped first; no openai SDK.

**Changed files:**
- `src/services/intelligence/llm_provider.py` (new) — `LLMProvider` Protocol, `OpenAICompatibleLLMProvider`, standalone `parse_json_array()`
- `src/services/intelligence/factory.py` (new) — `build_llm_provider(settings)`
- `src/services/intelligence/__init__.py` — exports `LLMProvider`, `OpenAICompatibleLLMProvider`, `build_llm_provider`
- `src/services/intelligence/worker.py` — `OllamaClient` → `LLMProvider` type; `parse_json_array` from module
- `src/services/rag/reranker.py`, `rag/service.py`, `chat/message_service.py` — type hints updated
- `src/services/api/main.py` — `ollama_client` param → `llm_provider`; `app.state.llm_provider` set from factory
- `src/services/api/routers/chat.py`, `admin/intelligence.py` — use `app.state.llm_provider`
- `src/services/pipeline/runner.py`, `slow_worker.py`, `intelligence_consumer.py` — use `build_llm_provider(settings)`
- `src/shared/config.py` — `llm_provider`, `llm_base_url`, `llm_model` fields added
- `.env.example` — `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL` commented block added
- `tests/unit/test_llm_provider.py` (new) — 18 tests

**Key constraint:** `generate_stream` is in the protocol; `OpenAICompatibleLLMProvider` raises `NotImplementedError` for streaming (OpenAI SSE format out of scope per issue). Streaming chat endpoint only works with `LLM_PROVIDER=ollama`.

**Verification:** ruff clean, mypy strict clean (8 files), 18 new + 36 existing related unit tests pass.

**Next agent prompt:**
> Pick up issue #529 (ingestion pipeline debug status page) or #530 (citation grounding). Both are status:next and unblocked.

---

## 2026-05-28 — dist: v0.2.0 air-gapped release artifact

Status: Active — files ready; CI build required before distributing
Source: Claude Code session

**Goal:** Produce a deployment-ready `dist/tomorrowland-release-v0.2.0/` replacing `v1.0-rc3` with correct version, new models (qwen3.5:35b-a3b, qwen3:14b, qwen3-embedding:8b), and split-Ollama compose.

**Changed files in `dist/tomorrowland-release-v0.2.0/`:**
- `release-manifest.json` — v0.2.0, 16ff0ab, v0.2.0 image tags, 3-bundle section, split ollama volumes
- `docker-compose.airgap.yml` — ollama → ollama-llm + ollama-embed; EMBEDDING_PROVIDER=ollama default
- `.env.airgap.example` — version stamp, EMBEDDING_PROVIDER=ollama
- `README-airgap.txt` — all 3 bundles, correct containers and sizes
- `docs/air-gapped-deployment.md` — full mistral → qwen3.5:35b-a3b sweep; 3-bundle table; port 11435 for embed validation
- `docs/air-gapped-upgrade.md` — 3-bundle upgrade path; per-container validation commands; ollama_llm/embed volume names
- `docs/production-compose.md` — volume table split; pull commands per container
- `scripts/validate-ollama-model.sh` — default model → qwen3.5:35b-a3b
- `scripts/load-ollama-model-bundle.sh` — usage updated for --compose-service
- `checksums.txt` — regenerated

**New bundle metadata dirs:**
- `dist/tomorrowland-ollama-bundle-qwen3.5-35b-a3b-v0.2.0/` (model-manifest.json + README)
- `dist/tomorrowland-ollama-bundle-qwen3-14b-v0.2.0/` (model-manifest.json + README)
- `dist/tomorrowland-ollama-bundle-qwen3-embedding-8b-v0.2.0/` (model-manifest.json + README)

**Verification:** Zero stale `mistral`/`v1.0-rc3`/`ollama_data`/`nomic-embed-text`/`mxbai-embed-large` strings in any text file in the release directory. 138 occurrences of correct v0.2.0/qwen3/ollama-llm/ollama-embed strings confirmed.

**Remaining (CI/build-time):**
1. Build and tag Docker images as `tomorrowland/backend:v0.2.0`, `frontend:v0.2.0`, `libretranslate:v0.2.0`.
2. Re-bundle `images/tomorrowland-images.tar` containing the v0.2.0-tagged images.
3. `sha256sum images/tomorrowland-images.tar >> dist/tomorrowland-release-v0.2.0/checksums.txt`
4. `tar czf dist/tomorrowland-release-v0.2.0.tar.gz -C dist tomorrowland-release-v0.2.0/`
5. `sha256sum dist/tomorrowland-release-v0.2.0.tar.gz > dist/tomorrowland-release-v0.2.0.tar.gz.sha256`
6. Split image tar into 1900m parts: `split -b 1900m images.tar tomorrowland-images-v0.2.0.tar.part-`
7. Bundle each model dir into its `.tar.gz` and compute `.sha256`.

**Operator note — upgrading from rc3:**
- `ollama` service is now two services (`ollama-llm` + `ollama-embed`). Volumes renamed: `ollama_data` → `ollama_llm_data` + `ollama_embed_data`. Models must be re-loaded into both containers after upgrade.
- `EMBEDDING_PROVIDER=ollama` is now the default in `.env.airgap.example` (was empty).

**Next agent prompt:**
> Run the CI build pipeline for v0.2.0: build and tag Docker images, bundle images/tomorrowland-images.tar, update checksums.txt with the image tar hash, produce the platform archive and split parts, and bundle each of the 3 model directories into their .tar.gz files with .sha256 companions.

---

## 2026-05-28 — refactor(pipeline): enforce extraction boundary — only parse/worker may call .extract()

Status: Done — pushed to main
Source: Claude Code session

**Goal:** No worker or service outside the designated extraction stage may call `ExtractorRegistry.extract()` directly. All non-extractor callers must read pre-extracted text from `document_payloads`.

**Changes (7 files):**
- `pipeline/vector_worker.py`: removed `extractor` param from `run_vector_once`/`run_vector_loop`; removed fallback extraction block; removed `ExtractorRegistry` import.
- `pipeline/slow_worker.py`: removed `extractor_registry` constructor param and `self._extractor`; `process_document`/`_run`/`_run_versioned`/`_run_legacy` now accept `content_text: str = ""`; `run_enrich_once` fetches payload and passes `content_text` down.
- `related/service.py`: replaced `extractor_registry` constructor param with `job_repo: PipelineJobRepository`; `related_documents` reads `content_text` from payload.
- `api/routers/documents.py`: both `RelatedService(...)` calls pass `job_repo=PipelineJobRepository(connection)`.
- `api/routers/alerts.py`: admin re-match endpoint reads payload instead of calling extractor.
- `api/routers/admin/intelligence.py`: both trigger + summary-regenerate endpoints read payload.
- `tests/unit/test_slow_worker.py`: `_FakeEnrichRepo` gains `get_payload()`; assertion updated.

**Intentional exception:** `preview/service.py:302` — last-resort fallback after payload check fails, guarded by file-exists check, intentional for pre-pipeline uploads.

**Verification:** 8/8 slow-worker unit tests pass; zero `.extract()` calls outside `extraction/`, `pipeline/worker.py`, `pipeline/parse_worker.py`.

---

## 2026-05-27 — feat(extraction): uniform ExtractionResult envelope — commit 5e46f1f

Status: Done — pushed to main
Source: Claude Code session

**Goal:** Pipeline workers fully agnostic to file type — no `hasattr(extractor, "extract_attachments")` branch anywhere.

**Changes:**
- `base.py`: `ExtractionResult(text: str, attachments: list[AttachmentData] = [])` dataclass; `Extractor` protocol returns `ExtractionResult`.
- `__init__.py`: exports `ExtractionResult`.
- Container extractors (eml, msg_extractor, zip_extractor, tar_extractor): single-pass extraction — body text + attachment bytes in one file-open block; public `extract_attachments()` method removed.
- 16 non-container extractors: `return ExtractionResult(text=...)`.
- `registry.py`: `extract() -> ExtractionResult`; sniff-and-retry checks `result.text`.
- `pipeline/worker.py`: unpacks `result.text` + `result.attachments`; `hasattr` branch gone; `_extraction_result: ExtractionResult | None = None` guards attachment path (None when `pre_extracted_text` bypasses file extraction).
- `pipeline/parse_worker.py`, `slow_worker.py`, `vector_worker.py`, `related/service.py`, `preview/service.py`, `alerts.py`, `intelligence.py`: `.text` suffix added.
- All 25 extraction + pipeline unit test files updated to `.text` assertions.

**Verification:** 204 unit tests pass; mypy 0 new errors (8 pre-existing import-untyped warnings in unchanged files).

---

## 2026-05-27 — fix(frontend): 5 UX bugs across documents, chat, admin, and annotations

Status: Done — pushed to main
Source: Claude Code session

**Bugs fixed (4 files):**

1. **`FidelityStatusBar.tsx` — silent download failure** — "download original" button had no `.catch()`; added `r.ok` check and `showToast("error", …)` on failure.
2. **`InsightPane.tsx` (AnnotationsTab) — no Enter-to-submit** — annotation input lacked `onKeyDown`; inconsistent with `CommentComposer`/`AnnotationEditor`. Added Enter handler guarded by non-empty + not-pending.
3. **`AdminAddSourceWizard.tsx` — empty array treated as loading** — `!connectorTypes.length` was the loading gate; a system with zero connectors would show "Loading…" forever. Changed to `isLoading: connectorTypesLoading` from `useQuery`.
4. **`ChatWindow.tsx` — no retry on session load error** — error state rendered `EmptyState` with no recovery action. Added `variant="secondary"` Button that invalidates the query (uses `t.chat.retry`).
5. **`InsightPane.tsx` cache key mismatch (`["doc-annotations"]` vs `["annotations"]`)** — AnnotationsTab used a different key than `AnnotationList`/`AnnotationEditor`; mutations on one never invalidated the other (up to 2 min stale). Standardized all InsightPane keys to `["annotations", docId]`.

**Verification:** `tsc --noEmit` — 0 errors.

---

## 2026-05-27 — fix(extraction): generic Office extraction — commit 023f9e0

Status: Done — pushed to main
Source: Claude Code session

**Root cause (4 bugs):**

1. **XLS never extracted** — `application/vnd.ms-excel` had no extractor; fell to GenericExtractor which returns `""` for OLE binary files.
2. **DOCX/XLSX/PPTX with wrong stored MIME** — `application/zip` routed to ZipExtractor (returns XML file-listing, not text); `application/octet-stream` routed to GenericExtractor (returns `""`).
3. **Office MIME variants unregistered** — `.docm`, `.dotx`, `.pptm`, `.potx`, `.xltx`, `.xltm`, and `application/msword`-mislabeled DOCX all fell to GenericExtractor.
4. **Settings not wired in 3 workers** — `parse_worker`, `slow_worker`, `vector_worker` created `ExtractorRegistry()` without `enable_ocr`/`enable_legacy_office` from Settings.

**Fix:**
- `xls.py` — new `XlsExtractor` using `xlrd` (pure Python); registered for `application/vnd.ms-excel`. `xlrd>=2.0` in pyproject.toml.
- `mime_detector.py` — new `sniff_office_mime(path)`: reads ZIP contents (stdlib) to identify DOCX/XLSX/PPTX/ODF; detects OLE magic bytes for legacy. Used as last-resort in `detect()`.
- `registry.py` — sniff-and-retry in `extract()` for `application/zip` and `application/octet-stream` (always) and any MIME when result is empty. New aliases for all Office MIME variants.
- `parse_worker`, `slow_worker`, `vector_worker` — pass settings flags to `ExtractorRegistry`.

**Remaining limit:** `.doc` / `.ppt` (binary OLE) still need `ENABLE_LEGACY_OFFICE=true` + LibreOffice. No pure-Python library covers these.

**Tests:** 51 tests pass; 20 new (16 sniffing + 4 XLS). Ruff + mypy --strict clean.

---

## 2026-05-26 — fix/office-extraction-empty-text — 3-bug sweep (PR #521)

Status: Done — merged to main
Source: Claude Code session

**Root cause:** Three independent bugs all produced empty text for PPTX/DOCX documents.

**Bug 1 — preview snippet from deleted temp files (`src/services/preview/service.py`)**
`_generate_snippet` fell through to file re-extraction when no translation was found. SMB/Atlassian connectors delete the temp file after pipeline processing — file re-extraction always returned `""` even though `content_text` was safely stored in `document_payloads`. Fix: read `document_payloads.content_text` before the file fallback. Primary-key lookup; negligible overhead.

**Bug 2 — content_text lost on retry (`src/services/pipeline/consumer_base.py`)**
The manual retry path (`attempt >= retry_limit`, `< max_attempts`) rebuilt the retry JSON without `content_text`. Translate/embed/index workers all received `content_text=""` on retried messages. Fix: call `job_repo.get_payload(document_id)` in the retry branch and include `content_text` when the payload exists.

**Bug 3 — extractor exception gaps (`src/services/extraction/pptx_extractor.py`, `docx.py`)**
Both caught `(OSError, KeyError, PackageNotFoundError)` but not `zipfile.BadZipFile` or `ValueError`. Corrupted or mis-identified ZIP-based Office files propagated unhandled exceptions. Fix: added `zipfile.BadZipFile` and `ValueError` to both tuples.

**Changed files:**
- `src/services/preview/service.py`
- `src/services/pipeline/consumer_base.py`
- `src/services/extraction/pptx_extractor.py`
- `src/services/extraction/docx.py`
- `tests/unit/test_preview_service.py` (new)
- `tests/unit/test_extraction_pptx.py` (+2 tests)
- `tests/unit/test_extraction_docx.py` (+2 tests)
- `tests/unit/test_consumer_base.py` (+2 tests)

**Verification:** 17/17 targeted tests pass; ruff clean; mypy clean (4 source files, strict).

**Remaining risks:**
- Early retry attempts (attempt < `retry_limit` = `min(3, max_attempts)`) still use `basic_nack` → RabbitMQ DLQ re-route which does not carry `content_text`. Downstream workers can re-read from `document_payloads` if needed.
- `_generate_snippet` now makes one additional primary-key DB query per non-translated preview; negligible at current scale.

---

## 2026-05-26 — pipeline connector parity — 6-bug sweep

Status: Done — committed to main
Source: Claude Code session

**Root cause:** Both ingestion paths (`sync-now` API and scheduler) used hard-coded `connector_type == "smb"` string checks instead of capability-based checks, causing SMB temp files to be deleted too early (before the async worker reads them), Atlassian attachment temp files to leak, RabbitMQ messages to never be published from the scheduler, generator-level exceptions to be silently swallowed, and a logically unreachable `"failed"` sync outcome.

**Bugs fixed:**
1. **Temp file deleted before worker reads it** — `sync-now` called `os.unlink` on `item.path` inside the ingestion loop; the pipeline worker needs the file after the HTTP request returns. Removed the early unlink entirely.
2. **Atlassian temp files leaked** — SMB-only `os.unlink` never ran for Confluence/Jira attachment paths. Moved cleanup into `PipelineWorker._run()` via `_maybe_delete_connector_temp()`: deletes `doc.path` only if it lives under `tempfile.gettempdir()` (SMB + Atlassian), leaves Folder/NiFi staged files alone.
3. **Scheduler never published RabbitMQ messages** — `_sync_source` returned nothing; messages were enqueued in `pipeline_jobs` but never published. Added `_publish_scheduled_rabbit_messages()` mirroring the sync-now API path; refactored `_run_scheduled_syncs` to accept `engine` + `settings` and publish post-commit.
4. **`sync_outcome = "failed"` logically unreachable** — condition was `failed_discovery > 0 and discovered == 0` which can never be true. Fixed to `discovered > 0 and failed_discovery == discovered`.
5. **Generator exception swallowed** — `try/except` wrapped `connector.fetch_documents()` (the call), not the iteration. Since all real connectors are generators, the call always succeeds; mid-iteration errors (page 2 network failure etc.) were uncaught. Moved `try/except` around the `for item in documents:` loop.
6. **NiFi missing from `_classify_connection_error`** — Folder, SMB, Confluence, Jira all had connector-specific error classification; NiFi was absent, defaulting to a generic branch. Added NiFi branch for `staging_root`/`does not exist`/`not a directory` → `config_invalid` and `connection`/`timeout`/`refused` → `unreachable`.

**Changed files:**
- `src/services/api/_helpers.py` — Bug 6: NiFi branch in `_classify_connection_error`
- `src/services/api/routers/admin/ingestion.py` — Bugs 1+4: removed early `os.unlink`; fixed `sync_outcome` condition
- `src/services/pipeline/worker.py` — Bugs 1+2: added `_maybe_delete_connector_temp()`, called after extraction
- `src/services/pipeline/scheduler.py` — Bugs 1+2+3+4+5: refactored to per-source transactions, added RabbitMQ publish, fixed generator iteration guard, fixed `sync_outcome`
- `tests/integration/test_pipeline.py` — updated SMB cleanup test (temp files now preserved for worker)
- `tests/unit/test_pipeline_worker.py` — 4 new tests for `_maybe_delete_connector_temp`

**Verification:** 80 unit tests passed, 35 integration tests passed, ruff clean, mypy clean.

**Remaining risks:**
- `_maybe_delete_connector_temp` relies on `Path.is_relative_to(tempfile.gettempdir())`. On systems where a connector writes to a custom temp dir outside `gettempdir()` (e.g. Docker volume mounts), files would not be cleaned up. A future `ConnectorDocument.owned_by_caller: bool` flag would be cleaner.
- NiFi `staging_root` temp files are permanent staged paths — not cleaned up by the new helper (correct behavior: NiFi manages its own staging). No change needed, but worth noting.

**Next agent prompt:**
> Continue the ACL HIGH items from `docs/context/acl-audit.md`: `/search` admin bypass, `/expertise` admin bypass, stub `SearchResultItem`, transitive-group expansion, and `/expertise` subscription leak.

---

## 2026-05-26 — annotations router — security fixes (delete_reply + list_replies)

Status: Done — committed to main
Source: Claude Code session

**Changed files:**
- `src/services/annotations/repository.py` — added `get_reply_by_id()` (returns non-deleted reply by id)
- `src/services/api/routers/annotations.py` — extracted `_get_annotation_or_404_with_access()`; fixed `delete_reply` (missing `assert_doc_access`); fixed `list_replies` (private annotation visibility); refactored `update_annotation`, `delete_annotation`, `create_reply` to use helper
- `tests/integration/test_annotations_api.py` — 2 regression tests: `test_delete_reply_blocked_without_doc_access`, `test_list_replies_hidden_for_private_annotation`

**Verification:** 22 integration tests passed (ruff clean, mypy clean).

**Remaining risks:**
- `create_reply` does not gate on annotation visibility (can reply to a private annotation if you have doc access + know annotation ID). Pre-existing; deliberate policy decision needed before fixing.
- ACL audit HIGH items still open — see current-state.md.

**Next agent prompt:**
> Implement the ACL audit HIGH items from `docs/context/acl-audit.md`: fix `/search` and `/expertise` admin bypass, drop stub `SearchResultItem`, add transitive-group expansion, and tighten the `/expertise` subscription leak. These block the D2 PR.

## 2026-05-26 — fix/extractor-bugs — 15-bug sweep (extractors + translation pipeline)

Status: Merged — main
Source: Claude Code session

**Changed files:**
- `src/services/extraction/html.py` — depth counter for nested skip tags; latin-1 fallback
- `src/services/extraction/rtf.py` — latin-1 fallback for Win-1252 RTF files
- `src/services/extraction/xml_extractor.py` — ET.parse() + itertext() (tag stripping + encoding)
- `src/services/extraction/docx.py` — merged-cell dedup by `_tc` identity
- `src/services/extraction/msg_extractor.py` — `msg.close()` in finally; contextlib.suppress import
- `src/services/extraction/xlsx.py` — `wb.close()` in finally block
- `src/services/extraction/epub.py` — re.DOTALL on `_TAG_RE`
- `src/services/extraction/eml.py` — filename-guessed MIME when no explicit Content-Type
- `src/services/extraction/registry.py` — remove self-alias + dead x-zip-compressed entry
- `src/services/pipeline/translation_worker.py` — graceful skip for empty content_text
- `src/services/pipeline/slow_worker.py` — `type(exc).__name__` in loop error log
- `src/services/pipeline/translate_worker.py` — use doc.target_language (default "en") instead of hardcoded "en"
- `tests/unit/test_extractor_bug_fixes.py` — 20 regression tests (new file; +2 for bug 15)
- `tests/unit/test_translation_worker.py` — 2 tests updated for new graceful-skip behavior

**Verification:** 28/28 targeted tests pass. 28 pre-existing failures in `test_compose_volumes.py` are unrelated.

**Remaining risks:**
- `test_compose_volumes.py` pre-existing failures need a separate fix (airgap compose YAML shape).
- `.doc`/`.xls`/`.ppt` (legacy Office) still return empty unless `ENABLE_LEGACY_OFFICE=true`.
- Scanned PDFs still need `ENABLE_OCR=true` for any text extraction.

**Next agent prompt:**
- Consider a backfill job to re-extract documents that had XML, RTF, or HTML files previously returning empty.

## Handoff template

```md
## YYYY-MM-DD — Short title

Status: Active | Done | Watch
Source: issue | PR | commit | chat summary

What changed:
- ...

Verification:
- ...

Open risks:
- ...

Next agent prompt:
- ...
```

Status: Done
Source: OpenCode session (no issue)

What changed:
- `src/shared/config.py` — all 6 `feature_document_chat_*` flags → True
- `src/services/search/qdrant.py` — `create_collection_if_not_exists()` in `search()` + `search_filtered()`
- `src/services/api/routers/chat.py` — SSE: manual connection mgmt; `data.get("answer")` fallback; generator exception handler
- `src/services/api/routers/qa.py` — **deleted**
- `src/services/api/main.py` — removed qa_router
- `src/services/pipeline/scheduler.py` — **new** cron scheduler worker
- `src/services/api/routers/admin/sources.py` — schedule in CRUD; `GET /admin/sources/{id}/documents` with job aggregation; `DELETE /admin/sources/{id}`; `DELETE /admin/documents/{id}`
- `src/services/api/routers/admin/dlq.py` — `POST /admin/documents/{id}/requeue`
- `src/services/api/schemas.py` — `UpdateSourceRequest.schedule`
- `migrations/versions/u5v6w7x8y9z0_add_source_schedule.py` — `schedule TEXT` on ingestion_sources
- `docker/backend.Dockerfile` — `uv pip install --system` from ghcr.io/astral-sh/uv
- `.github/workflows/backend.yml`, `security.yml`, `release.yml` — `astral-sh/setup-uv@v5` replacing pip cache + pip install
- `pyproject.toml` → `uv.lock` — generated lockfile (98 packages)
- `AGENTS.md` — all dev commands prefixed with `uv run`
- `.env` — `OLLAMA_MEM_LIMIT=5g`, `OLLAMA_CONTEXT_LENGTH=1024`, chat flags enabled
- `.bashrc` — `nvm use 22` + Node 22 bin in PATH; `.nvmrc` created
- `frontend/src/api/admin.ts` — `SourceDocument`, `PipelineJob`, `SourceDocumentsResponse` types; `getSourceDocuments`, `requeueDocument`, `deleteDocument`, `deleteSource` methods
- `frontend/src/features/admin/AdminSourcesPage.tsx` — delete source button
- `frontend/src/features/admin/AdminSourceDetailPage.tsx` — Edit Source → edit page; `SourceDocumentsSection` with progress bar, expandable job rows, auto-refresh, rerun, delete per document; delete source button
- `frontend/src/features/admin/AdminEditSourcePage.tsx` — **new** dedicated edit page
- `frontend/src/app/routes.tsx` — removed qaRoute; added `adminEditSourceRoute`
- `frontend/src/components/layout/NavRail.tsx` — removed /qa; removed `MessageSquare`
- `frontend/src/components/feedback/CommandMenu.tsx` — /qa → /chat

Verification:
- Backend: 51/51 admin tests, 30/30 chat tests, ruff + mypy clean
- Frontend: 34/34 admin tests, 1/1 CommandMenu test, `tsc --noEmit` clean, `npm run build` passes
- `uv run` verified: ruff, pytest, mypy all functional

Open risks:
- None remaining in scope.

Next agent prompt:
- (All tasks from this session complete.)
