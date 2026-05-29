# Testing

Prefer the narrowest check that proves your change, then run broader checks when
scope or risk requires it.

## Backend checks

Run these from the repository root:

```bash
ruff check --fix src/ tests/ migrations/
ruff format src/ tests/ migrations/
mypy src --strict
pytest tests/unit/test_<area>.py -q
pytest tests/integration/test_<area>.py -q
pytest
```

## Frontend checks

Run these from the repository root:

```bash
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
npm --prefix frontend run test:e2e
```

## Document-flow smoke test

Run against a running Compose stack (see `local-demo.md`):

```bash
# Minimal check (no auth, no frontend URL)
bash scripts/dev/smoke_document_flow.sh

# Full CI-mode check with credentials
SMOKE_MODE=ci FRONTEND_URL=http://localhost:8080 \
  SMOKE_ADMIN_EMAIL=admin@example.com SMOKE_ADMIN_PASSWORD=changeme \
  bash scripts/dev/smoke_document_flow.sh
```

Results are written to `tmp/smoke-document-flow-result.json`.

## Documentation checks

For docs-only changes, run targeted searches requested by the issue or PR plus:

```bash
git diff --check
```

If markdown linting is available in the environment, run it and include the
exact command in the PR validation section.
