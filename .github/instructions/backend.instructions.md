---
applyTo: "src/**/*.py,tests/**/*.py,migrations/**/*.py"
---

# Backend instructions

Follow `AGENTS.md` first. These rules apply to backend Python, tests, and
migrations.

## Python conventions

- Start Python files with `from __future__ import annotations`.
- Use Python 3.11+ typing: `str | None`, `dict[str, Any]`, and modern generic
  syntax.
- Keep Ruff's 100-character line length.
- Public functions and classes should have Google-style docstrings.
- Prefer small explicit helpers over broad framework rewrites.

## FastAPI and authorization patterns

- Use `Depends(current_user)` for authenticated API routes.
- Use `require_admin(user)` for admin-only operations.
- Call existing document-access guards such as `assert_doc_access(...)` before
  reading or mutating protected document data.
- Keep API routes in `src/services/api/main.py` unless an issue explicitly
  authorizes a route refactor.

## Persistence patterns

- Use SQLAlchemy Core repository patterns already present in the relevant module.
- Use `with app.state.engine.begin() as connection:` for transaction scopes that
  follow current API patterns.
- Use `shared.db.db_uuid(value)` for SQL UUID parameter binding.
- Always use SQLAlchemy bound parameters. Do not build SQL with f-strings or
  interpolated user input.
- Every Alembic migration must include a downgrade path.
- Do not introduce SQLModel or change the data-layer style unless the issue
  explicitly asks for that architectural change.

## Tests

- Unit tests should mock external services and use existing fixtures.
- Integration tests should use fixtures from `tests/conftest.py`, especially
  `migrated_engine` where applicable.
- Add or update the narrowest tests that prove the changed behavior.

Useful commands:

```bash
ruff check src/ tests/ migrations/
ruff format src/ tests/ migrations/
mypy src --strict
pytest tests/unit/test_<area>.py -q
pytest tests/integration/test_<area>.py -q
```
