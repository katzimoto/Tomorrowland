# Document Versioning — Implementation Plan

Related issues: #201 #202 #203 #204 #205 #236
Feature branch: `feature/document-versioning`
Status: planning — no schema or runtime code implemented yet

---

## 1. Chosen Data Model

### Decision: Option B — separate `document_version_families` table

Two options were evaluated for #203:

**Option A — version fields on `documents`**
Add `logical_document_id`, `version_number`, `is_latest`, `previous_version_id`,
and `content_sha256` directly to `documents`. No new table; lighter migration.
Downside: `documents` is already wide and shared across many services; self-referential
grouping keys are harder to query cleanly; no natural owner for "latest" metadata.

**Option B — separate `document_version_families` table** ← recommended
A new table owns the stable source identity and the pointer to the current version.
`documents` rows gain a FK into the family table plus version metadata.
This gives clean semantics, a first-class entity for retention policy, and an
unambiguous place for "latest_document_id".

### Recommended schema additions

```sql
-- New table (added in #203 migration)
CREATE TABLE document_version_families (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id           UUID        NOT NULL REFERENCES sources(id),
    external_id         TEXT        NOT NULL,
    current_document_id UUID        REFERENCES documents(id) ON DELETE SET NULL,
    created_at          TIMESTAMP   NOT NULL DEFAULT now(),
    updated_at          TIMESTAMP   NOT NULL DEFAULT now(),
    UNIQUE (source_id, external_id)
);

-- Additions to documents (added in #203 migration)
ALTER TABLE documents
    ADD COLUMN version_family_id UUID REFERENCES document_version_families(id),
    ADD COLUMN version_number    INTEGER,
    ADD COLUMN is_latest         BOOLEAN NOT NULL DEFAULT TRUE;
```

`content_sha256` is already added to `documents` by #202.

### Identity mapping

| Concept | Maps to |
|---|---|
| Logical document (source item) | One `document_version_families` row, keyed by `source_id + external_id` |
| Physical version | One `documents` row with `version_family_id` FK |
| Version number | `documents.version_number` — starts at 1, increments per new SHA |
| Current/latest flag | `documents.is_latest = TRUE` (only one row per family at a time) |
| Latest pointer | `document_version_families.current_document_id` |
| Content dedup key | `documents.content_sha256` (unique per `source_id + external_id + sha256`) |

### Why not Option A

Option A is a valid minimal-churn path for small teams. Choose Option A only if
the extra join from Option B is a measured performance problem. Option B is
recommended here because:

- Retention policy can target the family table cleanly.
- `unique(source_id, external_id)` sits on its natural owner.
- `current_document_id` is an explicit FK, not a derived max/filter.
- Comments and annotations can optionally reference the family ID in the future
  without requiring a virtual grouping key.

---

## 2. Migration Strategy

### Issue responsibility

| Issue | Migration content |
|---|---|
| #202 (done) | Add `content_sha256` to `documents`; relax `uq_documents_source_external` to `uq_documents_source_external_sha` on `(source_id, external_id, content_sha256)` |
| #203 | Create `document_version_families`; add `version_family_id`, `version_number`, `is_latest` to `documents`; backfill existing rows |

### Tables / columns to add (#203)

```text
CREATE TABLE document_version_families (...)
ALTER TABLE documents ADD COLUMN version_family_id UUID REFERENCES ...
ALTER TABLE documents ADD COLUMN version_number INTEGER
ALTER TABLE documents ADD COLUMN is_latest BOOLEAN NOT NULL DEFAULT TRUE
```

### Unique constraints

After #202: `UNIQUE(source_id, external_id, content_sha256)` on `documents`.
After #203: `UNIQUE(source_id, external_id)` on `document_version_families`.
The old `UNIQUE(source_id, external_id)` on `documents` was removed in #202.

### Backfill for existing documents

The #203 upgrade migration must:

1. For each distinct `(source_id, external_id)` group in `documents`,
   insert one row into `document_version_families`.
2. Set `version_number = 1` and `is_latest = TRUE` on those documents.
3. Set `version_family_id` FK on those documents.
4. Set `current_document_id` in the family row to that document's `id`.

All existing documents become version 1 of their own family. Existing behavior
is fully preserved — every document continues to appear as "latest".

### Zero-downtime approach

1. Add new columns as `NULLABLE` first (no constraint violations on existing rows).
2. Run backfill in the same migration (existing data is small enough; if volume
   is a concern, batch with `LIMIT/OFFSET`).
3. Add `NOT NULL` constraints after backfill if required (Alembic supports
   `server_default` approach for zero-downtime on large tables).
4. Do not lock `documents` with a full-table exclusive lock if table is large;
   prefer `ADD COLUMN ... DEFAULT` (PostgreSQL 11+ avoids full rewrite for
   non-volatile defaults).

### Downgrade strategy

The `downgrade()` function must:

1. Drop `version_family_id`, `version_number`, `is_latest` from `documents`.
2. Drop `document_version_families` table.

**Destructive limitation**: downgrade is only safe if each `(source_id, external_id)`
has exactly one `documents` row. After versioning is active and a file has been
re-synced, multiple rows exist per source item. Downgrading at that point will
leave orphaned rows and cannot restore the old `UNIQUE(source_id, external_id)`
constraint on `documents`. Document this in the migration header comment.

Rollback strategy for production: restore from a PostgreSQL backup taken before
the upgrade migration ran. Do not rely solely on Alembic downgrade after
versioning is actively used.

### Compatibility with existing documents

All existing documents get `version_number = 1` and `is_latest = TRUE`.
Search, preview, permissions, comments, and related-document surfaces continue
to work unchanged — every document is "latest" until a new version is created.

---

## 3. Ingestion Behavior

### Scenario A — First sync of a source item

1. No family exists for `(source_id, external_id)`.
2. Insert a new `document_version_families` row.
3. Insert a `documents` row: `version_number = 1`, `is_latest = TRUE`,
   `content_sha256 = <hash>`, `version_family_id = <new family id>`.
4. Set `current_document_id` on the family to the new document's `id`.
5. Index in Elasticsearch and Qdrant with version metadata.

### Scenario B — Re-sync, same SHA (unchanged file)

1. Lookup `(source_id, external_id, content_sha256)` → row exists.
2. Skip. Do not create a new document row, version number, or index entry.
3. Log as "skipped (already current)".

### Scenario C — Re-sync, different SHA (changed file)

1. Lookup family via `(source_id, external_id)` → family found.
2. Find the current latest document in that family.
3. Set `is_latest = FALSE` on the old latest document.
4. Insert a new `documents` row:
   - `version_number = old_latest.version_number + 1`
   - `is_latest = TRUE`
   - `content_sha256 = <new hash>`
   - `version_family_id = <existing family id>`
5. Update `current_document_id` on the family to the new document's `id`.
6. Index the new version in Elasticsearch and Qdrant.
7. Do NOT delete the old version's stored document row or index entries.
8. Log as "created version N for <source_id>/<external_id>".

### Scenario D — Deleted source file / tombstones

Out of scope for this feature track. The system currently does not track
source-side deletions. If a file disappears from the source, existing document
rows and index entries remain. A tombstone/soft-delete mechanism should be
addressed in a follow-up issue.

---

## 4. Search / Indexing Impact

### Elasticsearch payload additions

Add these fields to every indexed document:

```json
{
  "version_family_id":  "<uuid>",
  "version_number":     1,
  "is_latest":          true,
  "has_newer_version":  false,
  "latest_document_id": null
}
```

`has_newer_version = true` and `latest_document_id = <uuid>` when `is_latest = false`.

### Qdrant payload additions

Add the same fields to the Qdrant point payload so vector search can apply
the same filter:

```json
{
  "version_family_id":  "<uuid>",
  "version_number":     1,
  "is_latest":          true,
  "has_newer_version":  false
}
```

### Default behavior — latest-only

Unless the caller explicitly requests older versions, both Elasticsearch and
Qdrant queries must include an `is_latest = true` filter:

```json
// Elasticsearch
{ "filter": { "term": { "is_latest": true } } }

// Qdrant
{ "must": [{ "key": "is_latest", "match": { "value": true } }] }
```

This is the default for all search surfaces (keyword, vector, hybrid).

### Include older versions (`include_older_versions = true`)

Remove the `is_latest` filter from both ES and Qdrant queries.
Result payloads must include `version_number`, `is_latest`, `has_newer_version`,
and `latest_document_id` so the UI (#204) can label older results.

Permission filtering is applied before the version filter. Older versions of
inaccessible documents must not appear even when `include_older_versions = true`.

### Stale chunk / vector isolation

Each `documents` row has a unique `id`. Elasticsearch and Qdrant entries are
keyed by `document_id`. When a new version is indexed:

- New version chunks are stored under the new `document_id`.
- Old version chunks remain under the old `document_id`.
- The `is_latest = false` filter excludes old chunks from default search.
- No cross-contamination: version isolation is by `document_id`, not by
  document name or path.

When `include_older_versions = false` (default), old chunks are invisible.
There is no need to delete them for search correctness. Retention/deletion
of old chunks is a future operational concern.

**Reindexing caveat**: if a full reindex is triggered, all document rows
(including older versions with `is_latest = false`) will be reindexed with
the correct `is_latest` values. Operators must ensure that the version metadata
columns are populated before a reindex, or older versions may reappear as
`is_latest = true`. See §10 (validation checklist) and the operations docs.

---

## 5. Preview / Download Behavior

### Default — resolve to latest

When a user opens a document URL without an explicit version, resolve through
the version family:

1. Look up `version_family_id` from the document ID.
2. Follow `document_version_families.current_document_id` → latest document.
3. Serve the latest version's content.

If the document ID in the URL already points to the latest version, serve
directly with no redirect.

### Older version view

When the requested document ID is not the current `current_document_id`:

- Serve the requested older version's content normally.
- Display a warning banner:
  > _You are viewing an older version of this document. A newer version is available._
- Provide a link/action to open `latest_document_id`.
- Provide a link/action to the version history panel.

### Preview metadata payload

```json
{
  "id":                 "<doc uuid>",
  "version_number":     1,
  "is_latest":          false,
  "has_newer_version":  true,
  "latest_document_id": "<uuid>",
  "version_family_id":  "<uuid>",
  "indexed_at":         "2026-05-14T..."
}
```

### Version history panel

A compact list of all versions in the family, ordered by `version_number`:

```json
[
  { "id": "<uuid>", "version_number": 1, "is_latest": false, "indexed_at": "..." },
  { "id": "<uuid>", "version_number": 2, "is_latest": true,  "indexed_at": "..." }
]
```

Accessed via `GET /api/documents/{document_id}/versions`.
Requires the same source-access permission check as direct document access.

### Download

Safe download routes resolve to the file path stored on the specific `documents`
row being requested. Do not serve `document.path` directly; use the existing
validated download helper. Older-version downloads are allowed with the same
permission model as preview.

---

## 6. Permissions

### Inheritance model

All versions of a logical document share the same `source_id`. Access control
is evaluated against source-level permissions using the existing
`assert_doc_access` / source-permission path. No per-version permission
overrides.

### Version history endpoint

`GET /api/documents/{document_id}/versions` must:

1. Resolve the version family for the given document.
2. Assert source access for that document's `source_id`.
3. Return only versions within that family.
4. Never return versions from families the caller cannot access.

### Search result isolation

The `is_latest` filter does not bypass permission filtering. Permission checks
run before the version filter. An older version of an inaccessible document
must not appear in `include_older_versions = true` results.

### No inaccessible version leakage

The `latest_document_id` field returned in search results and preview payloads
must point to a document the requesting user can access. Because all versions
share the same `source_id`, this is guaranteed by the source-access model:
if the user can see any version, they can access all versions.

---

## 7. Comments / Annotations

### Decision: attach to the physical version (`documents` row)

Comments and annotations reference specific document content. Because content
differs between versions, attaching to the logical family ID would create
stale semantic references when the underlying text changes.

**Adopted rule**: comments and annotations are scoped to the specific
`documents.id` (physical version) they were created on. They travel with that
version row and are visible when that version is viewed.

### What this means in practice

- A comment left on version 1 does not appear on version 2 by default.
- Version history can show a count of comments per version.
- When viewing an older version, existing comments are visible; the user is
  already warned they are viewing an older version.

### Explicitly deferred: comment promotion / migration

Whether comments should be "promoted" (copied or re-linked) from an older
version to the newest version when a new version is created is **not decided
here**. This question is deferred to a follow-up issue and must not be
implemented silently during ingestion.

**Guardrail**: the ingest path for creating a new version must NOT touch
existing comment/annotation rows. Comments on old versions must remain
attached to those old version `document_id` values unchanged.

### Silent semantic change prevention

Do not reattach or move comments during migration or reindex. If this behavior
changes in the future, it must go through a reviewed design and a dedicated
migration, not be bundled into a version-creation or reindex operation.

---

## 8. API / UI Payload Changes

### Search result payload additions

Every search result object gains:

```jsonc
{
  // existing fields ...
  "version_family_id":  "<uuid>",
  "version_number":     2,
  "is_latest":          true,
  "has_newer_version":  false,
  "latest_document_id": null
}
```

When `is_latest = false`: `has_newer_version = true`, `latest_document_id = <uuid>`.

### Preview / document-detail payload additions

Same version fields as search results, plus `indexed_at` for the version timestamp.

### Version history endpoint

```
GET /api/documents/{document_id}/versions
```

Response:

```json
[
  {
    "id":             "<uuid>",
    "version_number": 1,
    "is_latest":      false,
    "indexed_at":     "2026-05-01T10:00:00Z"
  },
  {
    "id":             "<uuid>",
    "version_number": 2,
    "is_latest":      true,
    "indexed_at":     "2026-05-14T10:00:00Z"
  }
]
```

Ordered by `version_number` ascending. Requires source-access check (see §6).

### Search request extension (#205)

```jsonc
{
  "query":                "...",
  "page":                 1,
  "page_size":            10,
  "include_older_versions": false   // new field; default false
}
```

### Admin sync result wording

When sync creates a new version for an existing source item, the sync result
summary should reflect it clearly:

```
Indexed 3 new documents. Created 1 new version for an existing document.
Skipped 5 unchanged files.
```

Do not use language like "duplicate" or "conflict". "New version" and "changed
file" are the correct framings.

---

## 9. Merge Order Inside `feature/document-versioning`

All sub-issue PRs target `feature/document-versioning`, not `main`.
The final integration PR targets `main`.

| Order | Issue | Scope | Depends on |
|---|---|---|---|
| 1 | **#202** | `content_sha256` column; relaxed unique constraint; SHA-based dedup | — (already merged) |
| 2 | **#203** | `document_version_families` table; `version_family_id`, `version_number`, `is_latest` on `documents`; backfill migration; ingest logic for family linking | #202 |
| 3 | **#204** | Version badges in search results; older-version warning in preview; version history panel | #203 |
| 4 | **#205** | `include_older_versions` search flag; ES/Qdrant latest-only filter; search UI checkbox | #203, coordinates with #204 |
| 5 | **Integration PR** | `feature/document-versioning → main`; full CI pass; integration validation summary | #202 #203 #204 #205 |

### Notes on ordering

- #204 and #205 can be developed in parallel against the #203 backend contracts
  if the API payload shape is agreed on before #203 merges.
- The integration PR to `main` must not be opened until all four sub-issues
  pass CI on `feature/document-versioning`.
- Before the integration PR, rebase/merge latest `main` into
  `feature/document-versioning` and rerun CI.

---

## 10. Final Validation Checklist

Run all checks against `feature/document-versioning` before opening the
integration PR to `main`.

### Backend

- [ ] Alembic `upgrade` runs cleanly on a fresh PostgreSQL database.
- [ ] Alembic `upgrade` runs cleanly on an existing database with pre-existing
      `documents` rows (backfill path).
- [ ] Backfilled rows have `version_number = 1`, `is_latest = TRUE`, and a
      valid `version_family_id`.
- [ ] Alembic `downgrade` runs without error on a database that has only
      version-1 documents (no multi-version rows yet).
- [ ] Alembic `downgrade` includes a header comment warning that it is
      destructive when multiple versions exist.
- [ ] First sync of a new source item creates a family and version 1.
- [ ] Re-sync of unchanged SHA is idempotent: no new document row, no new
      index entry.
- [ ] Re-sync of changed SHA creates version N+1, sets old `is_latest = FALSE`,
      updates `current_document_id` in the family.
- [ ] Old version document row is preserved after a new version is created.
- [ ] Version history endpoint returns versions in order, with correct
      `is_latest` flags.
- [ ] Version history endpoint enforces source-access permission check.
- [ ] DLQ / failure records identify the source item and version attempt.

### Frontend

- [ ] "Latest version" badge renders on latest-version search results.
- [ ] "Older version — newer version available" badge renders on non-latest results.
- [ ] Preview page shows older-version warning banner with link to latest.
- [ ] Preview page shows version history panel with correct version list.
- [ ] No raw backend exception text or internal paths are rendered to users.
- [ ] `include_older_versions` checkbox defaults to unchecked.
- [ ] Checking the box sends `include_older_versions: true` to the search API.
- [ ] Older-version results are visibly labeled when the flag is enabled.

### Search (Elasticsearch)

- [ ] Default search (`include_older_versions = false`) returns only
      `is_latest = true` documents.
- [ ] `include_older_versions = true` returns all versions including
      `is_latest = false`.
- [ ] ES indexed documents include `version_family_id`, `version_number`,
      `is_latest`, `has_newer_version`, `latest_document_id`.
- [ ] Permission filter is applied before version filter in all query paths.

### Vector (Qdrant)

- [ ] Qdrant points include `is_latest` in payload.
- [ ] Default vector search excludes `is_latest = false` points.
- [ ] Old version chunks do not appear in latest-only vector results.
- [ ] New version's chunks are indexed under the new `document_id` and do not
      contaminate old version point groups.

### Permissions

- [ ] Version history endpoint refuses requests from users without source access.
- [ ] Search with `include_older_versions = true` does not return versions from
      inaccessible sources.
- [ ] `latest_document_id` in payloads always points to a document the
      requesting user can access (guaranteed by shared `source_id`).

### Migration

- [ ] `pytest` integration suite passes with SQLite migrated DB via
      `migrated_engine` fixture after the new migrations.
- [ ] Confirmed: downgrade is documented as destructive when multi-version rows
      exist.
- [ ] No `source_id + external_id` uniqueness violation on existing single-version
      rows after upgrade.

### Manual QA

- [ ] Sync a new file → admin sees version 1 created, search returns it.
- [ ] Modify the file, re-sync → admin sees "Created 1 new version" in sync
      result; search (default) returns only version 2.
- [ ] Re-sync the unmodified file again → no new version created; sync result
      says "skipped (already current)".
- [ ] Search with `include_older_versions` unchecked → only version 2 appears.
- [ ] Search with `include_older_versions` checked → both versions appear with
      correct labels.
- [ ] Open version 1 preview → older-version warning shown with link to version 2.
- [ ] Open version history → both versions listed with correct `is_latest` markers.
- [ ] Post a comment on version 1 → comment appears on version 1 only.
- [ ] Open version 2 preview → version 1's comment is not shown.

---

## User / Operator Documentation Scope

The following docs must be created or updated before `feature/document-versioning`
merges to `main`. These are the canonical locations for each audience.

### `docs/context/search.md` — agent / developer reference

Add a "Document versioning" subsection covering:

- `is_latest` filter behavior in Elasticsearch and Qdrant queries.
- `include_older_versions` search flag and how to test it.
- Version metadata fields in search result payloads.
- Stale chunk isolation rules.
- Discovery commands for version-related search symbols.

### `docs/context/frontend.md` — agent / developer reference

Add a "Document versioning UI" subsection covering:

- Which components render version badges and the older-version warning.
- The version history panel location.
- The `include_older_versions` checkbox component and the API flag it sends.
- Test commands for version-related frontend components.

### `docs/operations/production-compose.md` — operator reference

Add an "Upgrade notes — Document versioning" section covering:

- The migration adds `document_version_families` and version columns to
  `documents`; existing documents are backfilled as version 1.
- After the upgrade, re-syncing a changed file creates a new version instead
  of failing with a duplicate-key error.
- Reindex caution: version metadata must be populated before a full reindex
  to avoid older versions re-appearing as latest.
- Downgrade is destructive when multiple versions exist; take a database backup
  before upgrading.
- Admin sync result interpretation: "Created N new version(s)" indicates
  changed files; "Skipped N unchanged files" indicates idempotent re-syncs.

### `README.md` — user / admin overview

The README is a developer quick-start guide, not a user-facing behavior reference.
Version-specific user behavior does not belong there. The README should be updated
only to add a one-line note in "Key capabilities" once the feature lands in
`main`:

> - Document versioning: changed files are indexed as new versions; users can
>   view version history and filter search to latest-only.

Do not touch `README.md` in the planning or sub-issue PRs. Add this line in the
final integration PR to `main`.

---

## Context Loaded

- `AGENTS.md`
- `docs/agents/token-efficiency.md`
- `docs/context/search.md`
- `docs/context/frontend.md`
- `docs/operations/production-compose.md` (first 60 lines)
- GitHub Issues #201, #202, #203, #204, #205, #236

## Context Skipped

- `spec.md`, `spec-v4.pdf` (not authorized)
- Product source files (docs-only mission; source inspection not required)
- All other implementation plans

## Token Efficiency Notes

- Used `rg`/`find` before opening files: yes (directory listing via `ls`)
- Read more than one plan: no
- Read broad source areas: no — docs-only mission; no runtime code read
