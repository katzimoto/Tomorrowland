# Meilisearch Security — Decisions

**Scope:** ACL filter construction, admin bypass, empty-group handling, API key
model, fields never sent to Meilisearch.
**Does not cover:** Index settings (issue #301), indexing pipeline (issue #303).
**Companion file:** `src/services/search/meili_acl.py`

---

## Threat model

The primary risk is **result leakage**: a user receiving search results for
documents they have no permission to access. This can happen if:

1. The ACL filter is omitted from a query (coding error).
2. The ACL filter is constructed from user-supplied input (injection).
3. Security fields (`allowed_group_ids`) appear in displayed attributes and are
   used by a client to re-filter results (defence in depth gap only, not a leak
   on its own).
4. The Meilisearch master key or an overly-scoped API key is exposed to the
   frontend, allowing direct index queries without the ACL filter.

---

## ACL filter model

The existing Elasticsearch search uses `allowed_group_ids: list[str]` on every
indexed document and `{"terms": {"allowed_group_ids": group_ids}}` on every
query. The Meilisearch ACL model mirrors this exactly.

Every `SearchChunkRecord` carries `allowed_group_ids: list[str]` (group UUIDs
as strings). Every query adds a filter derived solely from the authenticated
user's token — never from request parameters.

### Filter cases

| User type | Filter applied |
|-----------|---------------|
| `is_admin = True` | None (empty string) — admin sees all documents |
| Non-admin, one or more groups | `allowed_group_ids IN ["id1", "id2", ...]` |
| Non-admin, no groups | Short-circuit: return empty result, no Meilisearch query |

The no-groups case short-circuits before querying Meilisearch. An empty `IN []`
list is syntactically ambiguous across Meilisearch versions; avoiding the query
entirely is simpler and cheaper.

### `is_admin_only` flag

Documents flagged `is_admin_only = True` are reserved for platform admins.
Non-admin queries always append `AND is_admin_only = false` regardless of group
membership. Admin queries have no filter at all, so they see these documents.

The combined non-admin filter is therefore:

```
allowed_group_ids IN ["id1", "id2"] AND is_admin_only = false
```

### Filter composition

The ACL filter is always composed in `AND` position with any user-supplied
filters:

```
<acl_filter> AND <user_filter>
```

`build_permission_filter` returns only the ACL portion. The caller
(`MeilisearchSearchProvider.search`) is responsible for composition. The ACL
filter is never optional — if the caller omits it, the result is incorrect.

To make omission impossible by construction, `search()` on the provider
accepts the authenticated user object, not a pre-built filter string.

---

## Filter injection prevention

Meilisearch filter strings are constructed from UUIDs only. UUIDs are validated
by the auth layer before reaching the search layer (they come from the JWT
payload, which is signed). No user-supplied string is interpolated into the
filter expression.

Group ID strings are quoted individually:
```python
quoted = ", ".join(f'"{gid}"' for gid in group_ids)
filter_str = f"allowed_group_ids IN [{quoted}]"
```

The quotes prevent any embedded characters (`:`, `[`, `]`, `AND`, `OR`) in a
malformed ID from being interpreted as filter operators.

---

## API key model

| Key | Holder | Scope |
|-----|--------|-------|
| Master key | Backend service only | All operations |
| Search-only key | Backend service (for search requests) | `actions: ["search"], indexes: ["documents"]` |

The master key is used at startup to create the search-only key, then stored
only in the backend settings (`MEILISEARCH_MASTER_KEY`). The search-only key
(`MEILISEARCH_SEARCH_KEY`) is used for all query operations.

**The frontend never receives either key.** All search traffic flows through
the app API, which constructs the ACL filter server-side.

Add to `shared/config.py` Settings:
- `MEILISEARCH_URL` — base URL of the Meilisearch instance
- `MEILISEARCH_MASTER_KEY` — used only at startup for index management
- `MEILISEARCH_SEARCH_KEY` — scoped search-only key for query operations

---

## Fields never sent to Meilisearch

| Field / category | Reason |
|-----------------|--------|
| JWT tokens, API keys | Credentials |
| User passwords or hashes | Credentials |
| Internal service credentials | Credentials |
| `metadata.path` in `metadata_text` | May reveal filesystem layout |
| `metadata.checksum` in `filterableAttributes` or `displayedAttributes` | Internal file hash |
| `metadata.version` in `filterableAttributes` or `displayedAttributes` | Internal versioning |

These exclusions are enforced in `build_metadata_text` (data model) and in
`displayedAttributes` / `filterableAttributes` (index settings). They are
documented here for completeness.

---

## Acceptance criteria

- [ ] `build_permission_filter` returns `""` for admin users
- [ ] `build_permission_filter` returns `allowed_group_ids IN [...] AND is_admin_only = false` for non-admin with groups
- [ ] `needs_acl_short_circuit` returns `True` for non-admin with no groups
- [ ] `compose_filters` always places the ACL filter first in AND position
- [ ] No user-supplied string is interpolated into the filter — only UUID values from the token
- [ ] `MEILISEARCH_URL`, `MEILISEARCH_MASTER_KEY`, `MEILISEARCH_SEARCH_KEY` added to `Settings` and `.env.example`
- [ ] Unit tests cover all four filter cases (admin, single group, multiple groups, no groups)
- [ ] `mypy src --strict` passes
