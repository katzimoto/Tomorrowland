# Phase 09b: Legacy Office Format Extraction

## Goal

Add text extraction for legacy Microsoft Office binary formats (`.doc`, `.xls`, `.ppt`) using
the existing extractor registry pattern.

## Phase Placement

Branch: `developer/phase-09b-legacy-office-extraction`

Status: Planned (independent of Phase 09a; can be developed in parallel).

## Current Baseline

- Modern Office formats are supported: `.docx` via `python-docx`, `.xlsx` via `openpyxl`,
  `.pptx` via `python-pptx`.
- The extractor registry in `src/services/extraction/` uses a protocol-based pattern where
  each extractor declares supported MIME types and returns extracted text or `""` on failure.
- Legacy binary formats (`.doc`, `.xls`, `.ppt`) are not handled; they fall through to the
  default empty-extraction path.

## Dependencies

- Phase 03a extraction persistence and extractor registry.
- Acceptable system dependency for legacy format parsing (see Decision Gates).

## Decision Gates

Confirm the acceptable system dependency before implementing:

- Option A: `python-docx2txt` (pure Python, limited fidelity for complex `.doc` files).
- Option B: `python-oletools` + `antiword`/`catdoc` system binaries (higher fidelity,
  requires system packages in the Docker image).
- Option C: LibreOffice headless conversion (highest fidelity, heaviest dependency).

Document the chosen option in `docs/review/spec-gaps.md` before coding.

## Scope

### Three New Extractors

Add to `src/services/extraction/`:

- `DocExtractor` — handles `application/msword` and `.doc` files.
- `XlsExtractor` — handles `application/vnd.ms-excel` and `.xls` files.
- `PptExtractor` — handles `application/vnd.ms-powerpoint` and `.ppt` files.

Each extractor must:

- Implement the existing `ExtractorProtocol`.
- Return `""` on any parsing failure without raising.
- Register itself in the extractor registry.
- Not affect modern format extractors.

### Docker Image Update

- Add the chosen system dependency to the API service `Dockerfile` if required.
- Document the dependency in `docs/operations/production-compose.md`.

## Implementation Notes

- Use fixture `.doc`, `.xls`, and `.ppt` files for deterministic tests; do not depend on
  live Microsoft Office or conversion services.
- Keep failure behavior consistent with existing extractors: silent empty string, no DLQ.
- Modern format extraction behavior must be verified unchanged after adding legacy extractors.

## Validation

```bash
ruff check src/ tests/
ruff format --check src/ tests/
mypy src --strict
pytest tests/unit/test_extraction_legacy_office.py -q
pytest tests/integration/test_extraction.py -q
docker compose build api
```

## Acceptance Criteria

- `.doc`, `.xls`, and `.ppt` files produce non-empty extracted text for valid fixtures.
- Corrupt or unreadable legacy files return `""` without raising.
- Modern format extractor tests remain green.
- No regression in extraction coverage metric.
- Docker image builds successfully with the new dependency.
