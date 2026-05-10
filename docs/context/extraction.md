# Extraction Context

Use this map for document extraction, file-type handlers, registry behavior, and extraction tests.

## Main files

- `src/services/extraction/` — extraction registry and file-type handlers.
- `src/services/pipeline/` — ingestion and slow translation hooks that may call extraction.
- `src/services/documents/` — document metadata affected by extraction output.
- Extraction-related tests under `tests/unit/` and `tests/integration/`.

## Common tests

```bash
pytest tests/unit/test_*extraction*.py -q
pytest tests/integration/test_*extraction*.py -q
```

If exact test names are unknown, use `rg --files tests | rg 'extract|office|pdf|document'` before opening files.

## Patterns to preserve

- Use the existing registry pattern before adding a new handler path.
- Add tests per file type when extraction behavior changes.
- Keep external service calls mocked or stubbed in unit tests.
- Preserve feature flags and optional capability boundaries.
- Do not expose raw document paths directly.

## Do not touch unless required

- frontend UI files
- search ranking code
- migrations unless extraction metadata schema changes
- `spec.md`
- `spec-v4.pdf`

## Discovery commands

```bash
rg "<extension-or-handler>" src/services/extraction src/services/pipeline tests
rg --files src/services/extraction tests | rg 'extract|office|pdf|document'
```
