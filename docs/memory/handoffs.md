# Tomorrowland Handoffs

Shared record for concise cross-agent handoffs that remain useful after a chat or tool session ends.
<!-- Compaction cutoff: 2026-05-30. Older entries archived to docs/memory/archive/handoffs.md. -->

## 2026-06-08 — docs: documentation overhaul on feature/documentation-wiki

Status: Active
Source: PR #647, feature/documentation-wiki branch

**Done:** MkDocs Material wiki built, 65+ historical docs archived, documentation policy established, README modernized, CI enforces mkdocs build.

**Changed files:**
- `mkdocs.yml` — MkDocs Material config with 7-section nav
- `docs/index.md` — audience-routed home page
- `docs/roadmap.md` — links to GitHub Issues/CHANGELOG/git log
- `docs/api/*.md` — 6 auto-generated API Reference pages (mkdocstrings)
- `docs/agents/documenting-features.md` — comprehensive change-type → docs mapping
- `docs/agents/coding-behavior.md` — added rule #6 (Document Your Changes)
- `docs/agents/templates.md` — added Documentation section to issue template
- `docs/agents/token-efficiency.md` — archive/ location note
- `docs/agents/issue-context-template.md` — archive/implementation/ paths
- `docs/design/README.md` — landing page for Design & Specs
- `docs/context/frontend.md`, `docs/context/search.md` — removed broken implementation/ links
- `README.md` — modernized with badges, emoji grid, architecture diagram
- `AGENTS.md` — Pre-PR checklist item #6 (documentation)
- `.github/workflows/docs.yml` — new mkdocs job with build --strict
- `pyproject.toml` — mkdocs-material + mkdocstrings in optional-dependencies.dev
- `.gitignore` — site/ excluded
- `archive/` — 65+ historical docs moved from docs/, README.md explains contents
- `docs/memory/current-state.md` — documentation overhaul entry added

**Key invariants:**
- `mkdocs build --strict` passes clean — no broken links
- Historical docs (implementation plans, agent missions, superpowers) live in `archive/`, not `docs/`
- Every new feature must be documented per `docs/agents/documenting-features.md`
- CI enforces via mkdocs job on docs-touching PRs
- `docs/memory/archive/` intentionally left in place (shared-memory system's own lifecycle)

**Next agent prompt:**
> PR #647 is open on `feature/documentation-wiki` targeting `main`. Review the CI mkdocs job result, check the diff, and merge if approved. After merge, update docs/memory/current-state.md status to Done.

---

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
