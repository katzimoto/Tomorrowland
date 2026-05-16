# Sources Permissions Model

**Status:** Design  
**Related issues:** #302 (Meilisearch ACL), #177 (nested groups), #175/#176 (admin UX)

---

## 1. Purpose

This document describes the complete permissions model for document access in
Tomorrowland. Access is always resolved through **ingestion sources** — a user
who can access a source can read every document that belongs to it. The model
applies uniformly across the REST API, search indexes, RAG retrieval, preview,
and download paths.

---

## 2. Core Data Model

```
users ──< user_groups >── groups ──< source_permissions >── ingestion_sources ──< documents
```

### Tables

| Table | Key columns | Notes |
|---|---|---|
| `users` | `id`, `email`, `auth_source`, `is_admin` | `is_admin` is a hard privilege bit |
| `groups` | `id`, `name` | Unique name; global registry |
| `user_groups` | `(user_id, group_id)` | Flat user→group membership (current) |
| `ingestion_sources` | `id`, `name`, `type`, `enabled` | The access boundary unit |
| `source_permissions` | `(source_id, group_id)` | Which groups may access a source |
| `documents` | `id`, `source_id` | Documents inherit their source's grants |

**Invariant:** Document access is always derived from `source_permissions`. There
are no per-document grants and no user-to-source direct grants.

---

## 3. Access Evaluation — Current (Flat Groups)

### Decision algorithm

```
1. user.is_admin == True  →  ALLOW  (global bypass; no group check needed)
2. user.groups ∩ source_permissions[source_id]  ≠ ∅  →  ALLOW
3. otherwise  →  DENY (403)
```

### Enforcement points (backend)

| Function | Location | Role |
|---|---|---|
| `require_admin(user)` | `permissions/enforcer.py` | Guards admin-only operations |
| `assert_source_access(source_id, user, repo)` | `permissions/enforcer.py` | Checks steps 1–3 above |
| `assert_doc_access(doc_id, user, repo)` | `permissions/enforcer.py` | Resolves doc→source then delegates |
| `AuthRepository.user_can_access_source()` | `auth/repository.py` | SQL implementation of group intersection |

All API routes that expose document content or metadata must call
`assert_doc_access` (or `assert_source_access` when operating at source
granularity). Routes must never pass raw source/document IDs from the request
body to the DB without running this check.

### Admin bypass detail

`is_admin=True` short-circuits every access check. The `admins` group exists as
a convenience for granting admins access inside search index filters (see §4),
but the authoritative bypass is the `is_admin` flag, not group membership.

`AuthRepository._is_admins_group_member()` also grants bypass access to the
`admin@local.com` bootstrap user and to users whose `groups` list contains the
`admins` group UUID, providing a secondary path for integration tests.

---

## 4. Search Index ACL Layer

Every document stored in a search index carries a field listing the group IDs
that may see it. The filter is enforced server-side at query time; the frontend
never sends a filter and never contacts the index directly.

### 4.1 Elasticsearch (current)

Index mapping:

```json
"allowed_group_ids": { "type": "keyword" }
```

Filter applied at query time (`elastic.py`):

```python
if group_ids:                                         # admin path: no filter
    es_query["bool"]["filter"] = {
        "terms": {"allowed_group_ids": group_ids}
    }
```

`group_ids` is derived from `get_allowed_groups(user)`. For `is_admin=True`
users the caller passes an empty list, triggering the no-filter branch.

**Edge case:** A non-admin user with no group memberships also produces an empty
`group_ids` list, which currently skips the filter and returns all results. This
is safe only because `assert_source_access` blocks those users before they reach
search. Any future refactor must preserve this guard ordering or explicitly
handle the empty-group case in the index query (see §4.2 for the correct
pattern).

### 4.2 Meilisearch (planned — issue #302)

The equivalent helper lives in `src/services/search/meili_acl.py`:

```python
def build_permission_filter(user: TokenPayload | UserIdentity) -> str:
    if user.is_admin:
        return ""                          # empty string = no filter in Meilisearch
    ids = [str(g) for g in user.groups]
    if not ids:
        return "allowedGroupIds IS EMPTY"  # explicit zero-result guard
    quoted = ", ".join(f'"{g}"' for g in ids)
    return f"allowedGroupIds IN [{quoted}]"
```

This differs from the Elasticsearch implementation in one important way: the
no-group case is **explicit** (`IS EMPTY` matches nothing) rather than
implicitly safe. This removes reliance on the route-level guard as a backstop.

### 4.3 Populating the ACL field at index time

When a document is indexed, the pipeline resolves which group IDs are granted
access to its source and writes them into `allowed_group_ids` /
`allowedGroupIds`. If source permissions change after indexing, a partial
re-index of affected documents is required to keep the field current.

---

## 5. Planned Extension — Nested Groups (issue #177)

### 5.1 Motivation

Flat groups cannot represent org-hierarchy access structures
(e.g. "All Technical Staff" contains "Engineering" and "Security Reviewers").
Nested groups let admins grant a parent group access to a source and have that
access cascade to all child groups and their users transitively.

### 5.2 Data model addition

Add a `group_memberships` table alongside the existing `user_groups` table:

```sql
CREATE TABLE group_memberships (
    parent_group_id  UUID  NOT NULL  REFERENCES groups(id)  ON DELETE CASCADE,
    child_group_id   UUID  NOT NULL  REFERENCES groups(id)  ON DELETE CASCADE,
    PRIMARY KEY (parent_group_id, child_group_id),
    CHECK (parent_group_id <> child_group_id)   -- no self-membership
);
```

`user_groups` is unchanged; it still records direct user→group membership.

### 5.3 Cycle prevention

Cycles must be rejected at write time. Before inserting `(parent, child)`:

1. Ensure `child ≠ parent` (CHECK constraint above handles the direct case).
2. Walk the existing graph from `child` upward (ancestors of `child`). If
   `parent` appears in any ancestor, the insert would create a cycle → reject
   with a descriptive error.

The ancestor walk must be bounded (maximum depth recommendation: 10 levels).
Exceeding the bound should also be rejected.

For Postgres the check is efficient via a recursive CTE:

```sql
WITH RECURSIVE ancestors AS (
    SELECT parent_group_id AS id FROM group_memberships WHERE child_group_id = :child
    UNION ALL
    SELECT gm.parent_group_id FROM group_memberships gm
    JOIN ancestors a ON gm.child_group_id = a.id
)
SELECT 1 FROM ancestors WHERE id = :parent LIMIT 1;
```

SQLite (used in integration tests) requires an iterative Python fallback since
CTEs with recursion are read-only in SQLAlchemy's test dialect — see
`AuthRepository._group_would_create_cycle()`.

### 5.4 Effective membership resolution

`user_can_access_source()` must change from a flat intersection to a transitive
resolution:

```
effective_group_ids(user) = user.groups  ∪  all_ancestors(user.groups)
```

`all_ancestors(seed_group_ids)` returns every group ID reachable by following
`child → parent` edges from the seed set.

The resolution is performed in SQL (recursive CTE on Postgres) or Python BFS/DFS
(SQLite fallback). The result is intersected with `source_permissions[source_id]`
exactly as before.

### 5.5 Search index impact

`allowed_group_ids` at index time must include **all group IDs that can reach
the source**, not just the directly-granted ones. Concretely, if source `S` is
granted to group `Parent`, and `Child` is a member of `Parent`, then the indexed
field for documents from `S` must include both `Parent.id` and `Child.id`.

Alternatively the field can contain only the directly-granted group IDs, and the
Meilisearch/Elasticsearch filter can be built from the **effective** (transitive)
group IDs of the current user. Both approaches are equivalent; the user-side
expansion is simpler to keep consistent when permissions change but requires
larger filter strings for deeply-nested hierarchies.

**Recommendation:** expand at query time (user's effective group IDs) rather
than at index time. This means permission updates never require re-indexing.

### 5.6 Admin API additions

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/admin/groups/{group_id}/users` | Direct user members |
| `POST` | `/admin/groups/{group_id}/users` | Add user to group |
| `DELETE` | `/admin/groups/{group_id}/users/{user_id}` | Remove user |
| `GET` | `/admin/groups/{group_id}/children` | Direct child groups |
| `POST` | `/admin/groups/{group_id}/children` | Add child group (cycle check) |
| `DELETE` | `/admin/groups/{group_id}/children/{child_id}` | Remove child group |
| `GET` | `/admin/groups/{group_id}/effective-users` | Transitive user membership (optional, for UI) |

All endpoints require `require_admin(user)`.

---

## 6. Security Invariants

These must hold across all current and future implementations:

1. **Backend enforcement is authoritative.** The frontend may show/hide UI
   elements but must never be the only access check.
2. **Admin bypass is via `is_admin` flag only.** Group membership in `admins`
   is a legacy shortcut; new code should read `user.is_admin`.
3. **No filter on the frontend.** Search index URLs and API keys never appear
   in frontend configuration or bundles.
4. **Non-admin user with no groups sees zero documents.** The search ACL must
   handle the empty-group case explicitly (see §4.2).
5. **Cycle prevention is enforced in the backend.** The UI may warn but the
   database layer is the final guard.
6. **Source-level granularity only.** There are no per-document or
   per-user-direct grants. Changes to the model that introduce finer-grained
   grants require a new design review.
7. **Audit.** Every permission grant and revocation must be written to the audit
   log via `_audit_log()` in the route handler.

---

## 7. Consistency Requirements Across Access Paths

Source permissions must be evaluated equivalently in all of:

| Path | Current hook | Notes |
|---|---|---|
| REST document read/preview | `assert_doc_access` | enforcer.py |
| REST search results | `get_allowed_groups` → ES filter | search route |
| Meilisearch search | `build_permission_filter` | meili_acl.py (#302) |
| Qdrant vector search | `group_ids` filter | qdrant.py |
| RAG / Q&A retrieval | inherits search filter | rag service |
| Related documents | `source_permissions` join | related service |
| Preview / download | `assert_doc_access` | preview service |

When nested groups (#177) are implemented, **all of these paths** must adopt the
transitive effective-group resolution. A phased rollout that updates only some
paths is unsafe and must not be merged without a cross-cutting integration test.

---

## 8. Migration Path

### Phase A — current (shipped)

Flat groups. `user_groups` + `source_permissions`. Elasticsearch `allowed_group_ids` filter.

### Phase B — Meilisearch ACL (issue #302)

Add `meili_acl.py` with explicit no-group and admin-bypass handling.
No schema change required.

### Phase C — Nested groups (issue #177)

1. Add `group_memberships` table (new migration, upgrade + downgrade).
2. Extend `AuthRepository` with cycle-check and ancestor-resolution helpers.
3. Update `user_can_access_source()` to use transitive resolution.
4. Update search filter construction to use effective group IDs.
5. Add admin API endpoints and UI for group-in-group management.
6. Integration tests: direct access, inherited access, cycle rejection, source
   permission via parent group, LDAP-sourced group compatibility.

### Backward compatibility

`user_groups` and `source_permissions` are unchanged by Phase C. Existing flat
memberships continue to work. The `group_memberships` table starts empty and
adds behaviour only when admin creates nested relationships.
