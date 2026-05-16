# Meilisearch Data Model — Implementation Plan

**Scope:** Index record shape, field decisions, and `SearchDocument` → Pydantic model.
**Does not cover:** Meilisearch settings, indexing pipeline, security, migration.
**Companion file:** `src/services/search/meili_types.py`

---

## Decisions

### 1. Single index, chunk-level records only

One index (`documents`) holds one record per document chunk. There is no separate
document-summary index at this stage. `distinctAttribute: "documentId"` (set in
Meilisearch config, not the data model) collapses results to one chunk per document
at query time.

### 2. Primary key format

`doc_{documentId}_chunk_{chunkIndex:04d}`

Example: `doc_abc123_chunk_0004`

Rationale: underscores are safe in Meilisearch primary keys and in HTTP path
segments. Zero-padded index preserves lexicographic sort order for debugging.

### 3. Remove `searchableText` and `translatedSearchableText`

These concatenated blobs duplicate signals that Meilisearch already scores via
`searchableAttributes`. Keeping them double-counts field matches and degrades
ranking precision. They are removed from the schema entirely.

### 4. Remove `entityType`

There is only one record type in this index. The field adds no value and is not
worth the schema noise. Re-add if a second record type (e.g. `document_summary`)
is introduced.

### 5. Flatten translations (no nested object)

The proposed `translations: { [lang]: { title, content, ... } }` cannot be
registered as searchable attributes in Meilisearch using wildcard paths.

Use flat, language-suffixed fields instead:

```
content_en, content_he, title_en, title_he,
summary_en, summary_he, heading_en, heading_he
```

Adding a new language requires adding new fields and updating index settings.
This is the same cost as the nested approach but is explicit and unambiguous.

Supported languages at this stage: English (`en`) and Hebrew (`he`).

### 6. `metadataText` — keep, but use an explicit allowlist

`metadataText` is a useful catch-all for metadata fields that benefit from
full-text search but don't need their own searchable attribute slot.

**Included:** `fileName`, `author`, `owner`, `tags`, `labels`, `topics`,
`project`, `workspace`, `collection`.

**Excluded:** `path`, `url`, `checksum`, `version`, `mimeType`, `fileExtension`.
Excluded fields are either sensitive (filesystem paths), internal (checksums,
versions), or better served as exact filters (mimeType, fileExtension).

### 7. `metadata.source` value set

The DB `DocumentSource` literal is `"folder" | "nifi" | "confluence" | "jira" | "smb"`.
The proposed index adds `"upload"`, `"local"`, `"generated"`, `"imported"`,
`"web"`, `"github"`.

Decision: keep the index `source` field loosely typed (`str`) so it can
accommodate connector expansion without a schema migration. The DB literal
remains the authoritative enum. The index value is copied from `DocumentRow.source`
at index time and is not validated against a fixed set.

### 8. Add `allowedGroupIds`

Every chunk record must carry `allowedGroupIds: list[str]` (group UUIDs as
strings). This mirrors the existing `allowed_group_ids` field in the Elasticsearch
index. It is the foundation for the permission filter applied on every query.

Details of how it is used belong in the Security plan, not here. The data model
simply requires the field to be present and non-null.

### 9. Add `contentChecksum`

SHA-256 of the `content` field (the chunk text). Used during reindex to skip
chunks whose content has not changed. This is distinct from `metadata.checksum`,
which is the document-level file hash stored in `DocumentRow.content_sha256`.

### 10. Add `indexedAt`

ISO 8601 timestamp set when the chunk is written to Meilisearch. Used for
staleness debugging and reindex validation. Not exposed to the frontend.

### 11. `metadata.checksum` and `metadata.version` — stored, not filtered

These fields are kept in the record for internal dedup and staleness checks.
They are excluded from `filterableAttributes` (not useful as user-facing filters)
and from `displayedAttributes` (not returned to callers).

### 12. `position` sub-object stays as-is

`chunkIndex`, `pageNumber`, `startOffset`, `endOffset` remain nested under
`position`. The top-level `chunkIndex` field (used for sorting) duplicates
`position.chunkIndex` — this redundancy is intentional because Meilisearch
sortable attributes must be top-level or exactly-pathed, not computed at query
time.

---

## What this plan does not decide

The following belong in separate planning sessions:

- Meilisearch index settings (searchable, filterable, sortable attributes;
  ranking rules; stop words; synonyms; distinctAttribute; faceting)
- Security model (ACL filter construction, what is never sent to Meilisearch,
  multi-workspace isolation)
- Indexing pipeline (write flow, retry/DLQ, stale-chunk detection, reindex strategy)
- Multilingual query routing
- Migration from Elasticsearch

---

## Acceptance criteria for the data model

- [ ] `SearchChunkRecord` Pydantic model exists at `src/services/search/meili_types.py`
- [ ] `allowedGroupIds` is a required field with no default
- [ ] `contentChecksum` is a required field with no default
- [ ] `indexedAt` is set by the builder function, not the caller
- [ ] `metadataText` is built by `build_metadata_text()`, not passed in by the caller
- [ ] No `searchableText`, `translatedSearchableText`, or `entityType` fields exist
- [ ] No nested `translations` object; only flat `content_en`, `content_he`, etc.
- [ ] `metadata.source` accepts any string (not a closed enum)
- [ ] Unit tests cover: `build_metadata_text` excludes sensitive fields,
  `chunk_record_id` is deterministic, model rejects missing `allowedGroupIds`
