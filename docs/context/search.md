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
