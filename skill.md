# skill.md — Tomorrowland Project Skills

> Shared skill definitions for Developer and Reviewer agents working on Tomorrowland.
> This is a Python/FastAPI project. All commands and thresholds below are exact.

---

## 1. Test-Driven Development (TDD)

### Cycle

```
Red  → write a failing test that describes the desired behaviour
Green → write the minimal code to pass the test
Refactor → clean up without changing observable behaviour
```

### Test runner

**pytest** with coverage.

```bash
# Full suite (CI)
pytest

# Fast subset (unit only)
pytest tests/unit/ -q

# Single test file
pytest tests/unit/test_translation.py -q

# With coverage report
pytest --cov=src --cov-branch --cov-report=term-missing tests/
```

### Coverage thresholds (enforced)

```
lines:    ≥ 90%
branches: ≥ 90%
```

Configured in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
addopts = "--cov=src --cov-branch --cov-report=term-missing --cov-fail-under=90"
```

### File locations

| Test type | Directory | Pattern |
|-----------|-----------|---------|
| Unit | `tests/unit/` | `test_*.py` |
| Integration | `tests/integration/` | `test_*.py` |

### What to test

- **Happy path** — expected inputs produce expected outputs.
- **Edge cases** — empty input, boundary values, max values, missing files.
- **Error paths** — invalid input throws correct HTTPException or sets status='failed'.
- **Side effects** — DB writes, ES/Qdrant calls (use mocks/stubs).
- **Permission filtering** — unauthorized access returns 403.

### What not to test

- Third-party library internals (e.g., pypdf, elasticsearch-py).
- Trivial getters/setters unless they contain logic.
- Implementation details that are not observable behavior.

---

## 2. Linting & Type Checking

### Tools

- **Ruff** — lint + format (replaces flake8, black, isort)
- **mypy** — strict type checking

### Commands

```bash
# Fix locally (pre-commit runs this)
ruff check --fix src/ tests/ migrations/
ruff format src/ tests/ migrations/

# Type check
mypy src --strict

# CI (strict — no auto-fix)
ruff check .
ruff format --check .
mypy src --strict
```

### Configuration (from pyproject.toml)

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "C4", "SIM", "TCH"]
ignore = ["TC001", "TC002", "TC003"]

[tool.mypy]
strict = true
python_version = "3.11"
mypy_path = "src"
files = ["src", "tests"]
```

### Code style rules

1. Every `.py` file starts with `from __future__ import annotations`
2. Every public function/class has a Google-style docstring
3. Type hints on all function signatures
4. Use `|` union syntax (`str | None`, not `Optional[str]`)
5. Use `dict[str, Any]` not `Dict[str, Any]`
6. Import order: stdlib → third-party → local (`services.*`, `shared.*`)
7. UUID SQL params: use `shared.db.db_uuid(value)` to handle UUID→string binding

---

## 3. Documentation

### Required per PR

| Item | Required when |
|------|---------------|
| Inline docstring | Every new or modified public symbol |
| Phase plan update | If scope changes |
| `CHANGELOG.md` entry | Every merged PR |
| `review/<pr>.md` | Every reviewed PR |

### Docstring template (Google style)

```python
def my_function(param: str) -> int:
    """Short one-line summary.

    Longer description if needed. Mention side effects or preconditions.

    Args:
        param: Description of parameter.

    Returns:
        Description of return value.

    Raises:
        ValueError: When param is invalid.

    Example:
        >>> my_function("hello")
        5
    """
```

### Changelog format

```markdown
## [Unreleased]

### Added
- Phase 05b: Translation enrichment — manual request, auto-enrich threshold,
  slow worker reindex. (#12)

### Fixed
- ...
```

---

## 4. Security

### Hard rules

- No hardcoded credentials, tokens, or keys — use `Settings` from `shared.config`.
- Sanitize external input (HTML previews use regex sanitization in `_sanitize_html`).
- Use parameterized queries (SQLAlchemy `sa.text()` with bound params).
- `document.path` is never served directly — use `send_file` with path validation.

### Audit commands

```bash
# Dependency audit (runs in CI)
pip-audit

# Secret scan (runs in CI)
rg -n --hidden --glob '!.git/' --glob '!.env.example' \
  '(JWT_SECRET|PASSWORD|API_TOKEN|PRIVATE_KEY)=([^c]|c[^h]|ch[^a]|cha[^n]|chan[^g]|chang[^e]|change[^m]|changem[^e])' .
```

---

## 5. FastAPI Patterns

### Route structure

All routes are in `src/services/api/main.py`. Group by feature area:

```python
# Auth routes
@app.post("/auth/login")
@app.post("/auth/logout")

# Search routes
@app.post("/search")

# Preview routes
@app.get("/preview/{doc_id}")
@app.get("/me/activity")

# Admin routes
@app.get("/admin/activity")
@app.get("/admin/enrichment-queue")
```

### Common patterns

```python
# Auth dependency
from services.auth.models import TokenPayload
from services.auth.jwt import current_user

@app.get("/protected")
def protected(user: Annotated[TokenPayload, Depends(current_user)]):
    ...

# Admin guard
from services.permissions.enforcer import require_admin

@app.get("/admin/only")
def admin_only(user: Annotated[TokenPayload, Depends(current_user)]):
    require_admin(user)
    ...

# Document access check
from services.permissions.enforcer import assert_doc_access

@app.get("/documents/{doc_id}")
def get_doc(doc_id: UUID, user: Annotated[TokenPayload, Depends(current_user)]):
    with app.state.engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        assert_doc_access(doc_id, user, auth_repo)
        ...

# DB transaction
with app.state.engine.begin() as connection:
    repo = SomeRepository(connection)
    repo.do_work()
    # committed automatically on exit
```

---

## 6. Database & Migrations

### Alembic

```bash
# Generate migration
alembic revision --autogenerate -m "description"

# Run migrations
alembic upgrade head

# Downgrade one
alembic downgrade -1
```

### Migration rules

1. Every migration must have a `downgrade()` path.
2. FK constraints must use `ON DELETE CASCADE` or `ON DELETE SET NULL` explicitly.
3. Check constraints must be dropped and recreated (not altered in-place).
4. Test migrations in `tests/test_migrations.py`.

---

## 7. CI Pipeline

Defined in `.github/workflows/ci.yml`.

Jobs run on every push to:
- `main`
- `developer/**`
- `docs/**`
- `feature/**`
- `fix/**`

And on every pull request.

### Steps (in order)

1. Install dependencies (`pip install -e ".[dev]"`)
2. Check required bootstrap files exist
3. Check markdown structure (every `.md` starts with `#` or `---`)
4. Lint & Format (`ruff check`, `ruff format --check`)
5. Type check (`mypy src --strict`)
6. Test with coverage (`pytest`)
7. Docker Compose config validation
8. Secret scan
9. Dependency audit (`pip-audit`)

---

## 8. Token Budget Guidelines

| Operation | Max tokens |
|-----------|-----------|
| Context summarisation (per file) | 300 |
| Single agent turn | 4 096 |
| Review output | 2 048 |
| Total per PR (Developer) | 16 000 |
| Total per PR (Reviewer) | 8 000 |

**Strategies:**
- Start from `AGENTS.md`; use the scoped `frontend/AGENTS.md` when editing the UI.
- Load only the relevant diff (`git diff -- <path>` or `git diff origin/main...HEAD -- <path>`), never the full repo.
- Use `rg` and `rg --files` for discovery instead of recursive file dumps.
- Summarise long files to their public API surface.
- Chunk large features into multiple smaller PRs.
- Prefer structured output over verbose prose.
