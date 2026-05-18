# ACL Audit — Document-Derived API Surfaces (D1 #400 #142)

Read-only audit of every document-derived API surface, the auth pattern each
uses, and a D2 fix checklist for hardening the next PR.

Scope: surfaces that return or accept information derived from a single
document, its intelligence projection, or aggregated document evidence.
Out of scope: pure infrastructure endpoints (`/healthz`, `/readyz`,
auth/login, generic metrics), and frontend.

Auth primitives (`src/services/permissions/enforcer.py`):

- `current_user` — bearer-token dep; raises 401 on missing/invalid token.
- `require_admin(user)` — raises 403 unless `user.is_admin`.
- `assert_source_access(source_id, user, repo)` — admin bypass, else checks
  `repo.user_can_access_source` (source grants via `source_permissions` keyed
  by `group_id`).
- `assert_doc_access(document_id, user, repo)` — resolves `documents.source_id`
  via `repo.document_source_id` (404 if missing), then `assert_source_access`.
- Effective groups expansion: `AuthRepository.get_effective_group_ids` —
  transitive child-group membership. Used inconsistently across surfaces (see
  matrix and risks).
- Backend ACL filter on stores: `QdrantSearchClient.search` (group_ids filter,
  optional `allow_all`) and `ElasticsearchSearchClient.search`
  (`allowed_group_ids` terms filter, optional `is_admin`).

## Permission matrix

| Surface | Endpoint | Auth required | `assert_doc_access()` | Group filter | Admin bypass | Leakage risk | D2 fix needed |
|---|---|---|---|---|---|---|---|
| Document search (hybrid) | `POST /search` | yes | n/a (multi-doc) | ES `allowed_group_ids` + Qdrant `group_id` filter (effective groups for non-admins) | broken: passes `group_ids=[]` to ES & Qdrant without `is_admin=True`/`allow_all=True`; admins receive zero hits | stub `SearchResultItem` produced when DB row missing → may surface chunk_text from orphaned Qdrant vectors | YES — pass `is_admin`/`allow_all` for admins; drop stub fallback or 404 the result |
| Document preview | `GET /preview/{document_id}` | yes | yes | n/a (single-doc gate) | inherited from `assert_source_access` (admin bypass at source-grant level) | low | none required, but confirm version-family lookups still gate by doc access |
| Document download | `GET /download/{document_id}` | yes | yes | n/a | inherited | path is resolved + `is_relative_to(files_root)`; symlinks resolve before check — OK | none |
| User activity | `GET /me/activity` | yes | NO (returns whatever `preview_service.get_user_activity` emits) | NO post-filter against current group access | n/a | activity may include documents the user has since lost access to (revoked group → stale audit row still visible) | YES — filter the result by `assert_doc_access`/source membership at read time |
| Document metadata (versions) | `GET /documents/{document_id}/versions` | yes | yes (parent doc only) | family lookup returns all versions of family regardless of per-version source grant | partial | if a version was reassigned to a different source with narrower grants, the parent check still exposes its id/title/timestamp | YES — assert_doc_access on each returned version, not just the parent |
| Translation versions | `GET /documents/{document_id}/translation-versions` | yes | yes | n/a | inherited | low | none |
| Request translation | `POST /documents/{document_id}/translate` | yes | yes | n/a | inherited | low (writes pending translation_version) | none |
| Summary | `GET /documents/{document_id}/summary` | yes | yes | n/a | inherited | low | none |
| Entities | `GET /documents/{document_id}/entities` | yes | yes | n/a | inherited | low | none |
| Tags | `GET /documents/{document_id}/tags` | yes | yes | n/a | inherited | low | none |
| Key points (planned B2) | `GET /documents/{document_id}/key-points` | planned | planned: yes | n/a | planned: inherited | n/a — not yet exposed | YES — at implementation time, must mirror summary/entities pattern |
| Intelligence projection (planned B2) | `GET /documents/{document_id}/intelligence` | planned | planned: yes | n/a | planned: inherited | n/a | YES — at implementation time, single `assert_doc_access` then bundle summary/entities/tags/key-points |
| Related documents | `GET /documents/{document_id}/related` | yes | yes (parent doc) | Qdrant `group_id` filter with raw `user.groups` only (no `get_effective_group_ids`) | NO bypass (admins get only their own groups; no `allow_all`) | narrower than `/search` and `/qa` — admin in a transitive parent group will miss related docs they could reach via search | YES — apply `get_effective_group_ids` and admin `allow_all` path; align with `/qa` |
| Expertise / top_docs evidence | `GET /expertise?topic=...` | yes | n/a (aggregated) | uses effective groups for non-admins; admins get `[]` | broken: passes `group_ids=[]` to `_qdrant.search` without `allow_all=True` (related/service.py `_qdrant.search` call) → admins get no results | subscription branch leaks `display_name`/`user_id` of any user whose subscription matches the topic AND who can access ≥1 doc in the requester's accessible set; `top_docs` per evidence carries doc ids the requester already has access to | YES — pass `allow_all` to Qdrant for admins; gate subscription leakage on a stricter co-membership check; do not return `display_name` of users outside any of the requester's groups |
| QA/RAG retrieval | `POST /qa` | yes | optional (per `document_id` body field, gated by `allow_all`) | uses effective groups; admin sends `group_ids=[]` plus `allow_all=user.is_admin` | YES — correct | citation payload includes `chunk_text`, `chunk_index`, `source_id`, `doc_title` — all are content the user already has filter access to via group_ids | none, except: when `body.document_id` is supplied, the service does not re-verify that the document is in any of the user's accessible groups; relies on Qdrant filter — fine, but log a regression test for the admin path |
| QA citations | (same response) | yes | inherited (Qdrant ACL) | same | YES | same | none |
| Comments — list | `GET /documents/{document_id}/comments` | yes | yes | n/a | inherited | returns `author_id` + `author_display_name` for every commenter | LOW: confirm that admin-only audit information (e.g. deleted-by) is not surfaced through this endpoint |
| Comments — create | `POST /documents/{document_id}/comments` | yes | yes | n/a | inherited | low | none |
| Comments — update | `PATCH /documents/{document_id}/comments/{comment_id}` | yes | yes + `repo.can_edit(... is_admin)` | n/a | yes (admin can edit any) | author edits own; admin edits any — intentional | none |
| Comments — delete | `DELETE /documents/{document_id}/comments/{comment_id}` | yes | yes + `repo.can_delete(... is_admin)` | n/a | yes | same as update | none |
| Annotations — list | `GET /documents/{document_id}/annotations` | yes | yes | n/a + `is_private` filtered in repo via user_id+is_admin | yes (admin sees all) | low | none |
| Annotations — create | `POST /documents/{document_id}/annotations` | yes | yes | n/a | inherited | low | none |
| Annotations — update | `PUT /annotations/{annotation_id}` | yes | yes (re-resolved via annotation.document_id) | `repo.can_modify` | yes | low | none |
| Annotations — delete | `DELETE /annotations/{annotation_id}` | yes | yes | `repo.can_modify` | yes | low | none |
| Subscriptions — list/CRUD | `/subscriptions`, `/subscriptions/{id}` | yes | n/a | NO doc gate; rows scoped by `user_id == user.sub` | n/a | low; verify cross-user enumeration via id is not possible (currently the GET/PUT/DELETE compare `subscription["user_id"]` against `user.sub` → safe) | none |
| Notifications — list/read | `/notifications`, `/notifications/{id}/read` | yes | n/a | scoped by `user_id == user.sub` | n/a | low (notification rows may reference documents the user lost access to between creation and read — same shape as `/me/activity`) | YES — drop notifications whose target document is no longer accessible to the user (or gate the link client-side via 403 on doc fetch) |
| Vault/export (planned E1) | `POST /vault/export/{document_id}` (or equivalent) | planned | planned: yes | n/a | planned: inherited | n/a | YES — at implementation time, hard requirement: `assert_doc_access`, no admin-only export bypass without explicit re-auth/scope flag |
| Admin: trigger alert matching | `POST /admin/alerts/{document_id}/trigger` | yes | NO (relies on `require_admin`); admin operates on raw document path | n/a | admin-only | low — admin already has full source bypass | LOW: when alerts grow to per-tenant scope, switch to `assert_doc_access` + admin check, not pure `require_admin` |
| Admin: trigger intelligence | `POST /admin/intelligence/{document_id}/trigger` | yes | NO (relies on `require_admin`) | n/a | admin-only | low | LOW: same as above |
| Admin: enrichment queue | `GET /admin/enrichment-queue` | yes | NO | n/a | admin-only | leaks every pending document id + title to any admin (intended) | none |
| Admin: activity audit log | `GET /admin/activity` | yes | NO | n/a | admin-only | intended | none |
| Admin: config | `GET/PUT/POST /admin/config[/...]` | yes | n/a | n/a | admin-only | values returned raw; sensitive keys must remain in `_SENSITIVE_CONFIG_KEYS` masking pattern (sources router does this, config router does not) | YES — apply the `_SENSITIVE_CONFIG_KEYS` mask in `/admin/config` GET responses for any secret-shaped keys (jwt_secret-equivalent etc.) |
| Admin: sources CRUD + permissions | `/admin/sources[...]`, `/admin/sources/{id}/permissions[...]` | yes | n/a | n/a | admin-only | source `config` is masked on detail; LIST endpoint does not return `config` (good) | none |
| Admin: users / groups / memberships | `/admin/users[...]`, `/admin/groups[...]` | yes | n/a | n/a | admin-only | passwords are hashed before insert; group cycle check exists | none |

## D2 fix checklist

Priority ordered. Items marked (HIGH) block the D2 PR.

1. **(HIGH)** Fix `/search` admin path so it actually returns results. In
   `src/services/api/routers/search.py`:
   - Pass `is_admin=user.is_admin` to `ElasticsearchSearchClient.search` (the
     client already supports it).
   - Pass `allow_all=user.is_admin` to `QdrantSearchClient.search` when
     `search_group_ids` is empty for admins.
   - Add a regression test asserting an admin with no explicit group
     membership receives non-empty results.
2. **(HIGH)** Fix `/expertise` admin path in
   `src/services/related/service.py` (`RelatedService.expertise`): forward
   an `allow_all` flag from the router into `self._qdrant.search`. Currently
   admins pass `group_ids=[]` and receive zero hits because no `allow_all` is
   threaded through `_qdrant.search`.
3. **(HIGH)** Drop or 404 the stub `SearchResultItem` produced in `/search`
   when the DB row is missing for a Qdrant-hit document_id. This currently
   surfaces `chunk_text` for orphaned vectors. Either filter out missing rows
   (preferred) or trigger a stale-vector purge job and 404 here.
4. **(HIGH)** Add transitive-group expansion (`get_effective_group_ids`) to
   `/documents/{document_id}/related` so its visibility matches `/search`
   and `/qa`. Today it uses `user.groups` only; users with access via
   parent-group membership see a narrower related-doc set than their search
   results.
5. **(HIGH)** Tighten `/expertise` subscription leak. The subscription
   branch in `RelatedService.expertise` adds any subscription owner whose
   query matches the topic and who can access ≥1 of the requester's docs.
   Strengthen: require the subscription owner to share at least one group
   with the requester (not just one matching doc), and avoid returning
   `display_name`/`user_id` when the only overlap is via admin bypass on
   the requester side.
6. **(MEDIUM)** Filter `/me/activity` results by current doc-access. Today a
   user whose group access has been revoked still sees the prior activity
   row referencing the now-inaccessible document. Apply
   `assert_source_access` or batch-filter by `get_allowed_groups(user)`.
7. **(MEDIUM)** Filter `/notifications` against current doc-access for the
   same reason — notifications may outlive group access changes.
8. **(MEDIUM)** Per-version ACL on `/documents/{document_id}/versions`.
   Today only the parent document is checked; iterate
   `assert_doc_access` over the family list before returning rows. This
   matters once cross-source version reassignment is allowed.
9. **(MEDIUM)** Mask sensitive keys in `GET /admin/config` responses using
   the existing `_SENSITIVE_CONFIG_KEYS` pattern from
   `src/services/api/routers/admin/sources.py`. Today every config value is
   returned raw, including any future secret-shaped key. Even for admins,
   masking-by-default is the safer pattern; require an explicit query flag
   for reveal.
10. **(MEDIUM)** Document — and enforce in tests — the expected admin policy
    across all RAG/search/related/expertise surfaces. The audit found three
    different conventions: `/qa` (admin bypass via `allow_all=True`),
    `/search` (admin bypass intended but broken), `/expertise` (admin
    bypass intended but broken), `/related` (no admin bypass at all). Pick
    one and apply it consistently. Add an integration test fixture per
    surface for admin / multi-group / single-group / no-group user shapes.
11. **(LOW, planned B2)** Key points & intelligence projection endpoints
    must mirror the `summary`/`entities`/`tags` pattern: single
    `assert_doc_access` at the top, no per-field guards, no admin
    short-circuit. Document this contract in the B2 PR description.
12. **(LOW, planned E1)** Vault export must require `assert_doc_access`
    even for admins, and ideally an explicit `?confirm=true` or re-auth
    step for high-value documents. Add as an acceptance criterion when E1
    is opened.
13. **(LOW)** Replace `require_admin`-only on
    `POST /admin/alerts/{document_id}/trigger` and
    `POST /admin/intelligence/{document_id}/trigger` with `require_admin +
    assert_doc_access` once multi-tenant scoping lands. Today these are
    cluster-admin operations so the current pattern is acceptable.
14. **(LOW)** Add a regression test that
    `QdrantSearchClient.search(group_ids=[], allow_all=False)` returns `[]`,
    to prevent a future refactor from breaking the fail-closed default.

## Risk ranking

Highest first.

### HIGH

- **H1. `/search` admin bypass is broken** (fail-closed but functionally
  wrong). Admins effectively get an empty hybrid search. Confidentiality is
  not impacted but operability and consistency are. Detected by reading
  `src/services/api/routers/search.py` ll. 48–116 against the contracts in
  `src/services/search/qdrant.py` ll. 114–142 and
  `src/services/search/elastic.py` ll. 150–202.
- **H2. `/expertise` admin bypass is broken** (same shape as H1). Detected
  by reading `src/services/api/routers/documents.py` ll. 349–387 against
  `src/services/related/service.py` ll. 93–156 and `qdrant.py` ll. 114–142.
- **H3. `/search` chunk_text leak via orphaned Qdrant vectors.** The DB-row-
  missing branch in `src/services/api/routers/search.py` ll. 205–225 emits a
  result whose `snippet = r.chunk_text or ""`. If the documents table is
  missing the row but Qdrant still has the chunk (deletion lag, partial
  rollback), unauthenticated-equivalent content surfaces. Group filter
  applies to the Qdrant search, so this is gated by group membership — but
  any user who shared a group with the original document at indexing time
  could still see the snippet after deletion. Severity: medium-to-high
  depending on deletion-lag reality. Treating as HIGH because cleanup is
  in-flight (see `feat/expertise-evidence` history around stale vectors).
- **H4. `/expertise` subscription user-discovery leak.** The subscription
  arm in `RelatedService.expertise` returns `user_id` + `display_name` for
  any user whose subscription matches the topic and who can access ≥1 doc
  the requester can also access. With single-document group overlaps, this
  becomes an oblique people-search surface: query a topic, learn that
  user X subscribes to it. Severity: HIGH for tenants with sensitive
  topic vocabularies.
- **H5. `/documents/{document_id}/related` uses narrower groups than
  `/search`** (`user.groups` only, no transitive expansion, no admin
  bypass). Severity HIGH for functionality consistency; not a
  confidentiality leak (it under-permits rather than over-permits).

### MEDIUM

- **M1. `/me/activity` and `/notifications` outlive group-revocation.**
  Documents the user has lost access to can still surface via these
  read-back endpoints.
- **M2. `/admin/config` returns raw values.** Defense-in-depth: any
  future secret-shaped config key (token, password, signing key) will be
  exposed to all admin viewers. The pattern exists in
  `routers/admin/sources.py` and should be lifted to `routers/admin/config.py`.
- **M3. Document version family ACL not enforced per-version.**
  `/documents/{document_id}/versions` checks the parent only.
- **M4. Effective-group expansion is inconsistent.** `/search`, `/qa`,
  `/expertise` use `get_effective_group_ids` for non-admins; `/related`
  does not. Pick a contract.

### LOW

- **L1. Admin-only single-document triggers** (`/admin/intelligence/...`,
  `/admin/alerts/...`) bypass `assert_doc_access`. Acceptable while admins
  have global source bypass; revisit when multi-tenant scoping lands.
- **L2. `/admin/users` and `/admin/groups` ACL is well-scoped** but the
  cycle check (`_group_would_create_cycle`) is a private method — add a
  type-checked public alias for the next round of refactor.
- **L3. `/download/{document_id}` is currently safe** (`resolve()` +
  `is_relative_to(files_root)`), but the audit recommends keeping a
  regression test that exercises symlink traversal at the integration
  layer.
- **L4. Planned B2/E1 surfaces** (key points, intelligence projection,
  vault export) must adopt the `assert_doc_access`-first pattern from the
  start.

## Handoff

- Files read: `AGENTS.md`, `docs/agents/token-efficiency.md`,
  `src/services/permissions/enforcer.py`,
  `src/services/api/main.py`,
  `src/services/api/routers/documents.py`,
  `src/services/api/routers/qa.py`,
  `src/services/api/routers/search.py`,
  `src/services/api/routers/comments.py`,
  `src/services/api/routers/annotations.py`,
  `src/services/api/routers/alerts.py`,
  `src/services/api/routers/admin/{config,intelligence,sources,users}.py`,
  `src/services/rag/service.py`,
  `src/services/related/service.py`,
  `src/services/intelligence/repository.py` (top portion only),
  `src/services/search/qdrant.py` (search method),
  `src/services/search/elastic.py` (search method).
- Files skipped: `spec.md`, `spec-v4.pdf`, all frontend, all migrations,
  full `intelligence/repository.py` body, `auth/{jwt,ldap,passwords,
  repository,service}.py` (only `current_user` and the enforcer were needed
  for the matrix), `routers/admin/{dlq,ingestion}.py` (admin-only, same
  pattern as the others audited), `routers/auth.py` and `routers/system.py`
  (not document-derived). Reason: token-efficiency rules and the matrix
  required only the routing layer + the two ACL primitives.
- No source files were modified. Audit is docs-only.
