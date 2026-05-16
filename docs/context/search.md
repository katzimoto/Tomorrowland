# Search Context

Use this map for Elasticsearch, Qdrant, hybrid search, ranking, query behavior, and search-related tests.

## Main files

- `src/services/search/` — Elasticsearch, Qdrant, hybrid merge, search orchestration.
- `src/services/documents/` — document metadata that search may depend on.
- `src/services/api/main.py` — search routes if API behavior changes.
- Search-related tests under `tests/unit/` and `tests/integration/`.

## Common tests

```bash
pytest tests/unit/test_*search*.py -q
pytest tests/integration/test_*search*.py -q
```

If exact test names are unknown, use `rg --files tests | rg search` before opening files.

## Patterns to preserve

- Keep Elasticsearch/Qdrant boundaries explicit.
- Avoid changing ranking semantics unless the mission says so.
- Preserve permission filtering before returning protected document results.
- Mock or stub external services in unit tests.
- Use integration fixtures for real persistence/search boundary checks.

## Do not touch unless required

- extraction handlers
- frontend UI files
- migrations unless search schema/index metadata changes require them
- `spec.md`
- `spec-v4.pdf`

## Discovery commands

```bash
rg "<query-or-symbol>" src/services/search src/services/api tests
rg --files src/services/search tests | rg search
```

## Document versioning

Added in `feature/document-versioning` (#201 / #203 / #205).
Plan: `docs/implementation/document-versioning.md`.

### Default behavior — latest-only filter

Both Elasticsearch and Qdrant queries must include an `is_latest = true` filter
by default. Remove it only when the caller sends `include_older_versions: true`.

```python
# Elasticsearch
{"filter": {"term": {"is_latest": True}}}

# Qdrant
{"must": [{"key": "is_latest", "match": {"value": True}}]}
```

### `include_older_versions` flag

The `/search` request accepts `include_older_versions: bool = False`.
When `True`, omit the `is_latest` filter from both ES and Qdrant queries.
All result objects must include `version_number`, `is_latest`,
`has_newer_version`, and `latest_document_id` so the UI can label results.

### Version payload fields (ES and Qdrant)

```json
{
  "version_family_id":  "<uuid>",
  "version_number":     1,
  "is_latest":          true,
  "has_newer_version":  false,
  "latest_document_id": null
}
```

### Stale chunk / vector isolation

Old version chunks are stored under the old `document_id`; new version chunks
under the new `document_id`. The `is_latest = false` filter excludes old chunks
at query time — no deletion required for search correctness.

**Reindex caution**: version metadata columns (`is_latest`, `version_number`,
`version_family_id`) must be populated in the database before a full reindex.
If a reindex runs against a partially migrated state, older versions may
re-appear as `is_latest = true`.

### Permission ordering

Permission filters are applied before the version filter.
Older versions of inaccessible documents must not appear even when
`include_older_versions = true`.

### Discovery commands

```bash
rg "is_latest\|include_older_versions\|version_family" src/services/search src/services/api tests
pytest tests/unit/test_*search*.py tests/integration/test_*search*.py -q -k version
```
