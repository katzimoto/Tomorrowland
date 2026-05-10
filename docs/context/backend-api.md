# Backend API Context

Use this map for FastAPI route, auth, permissions, readiness, and API persistence work.

## Main files

- `src/services/api/main.py` — MVP keeps FastAPI routes here.
- `src/services/auth/` — JWT, password, LDAP boundary, repositories.
- `src/services/permissions/` — authorization guards and document access checks.
- `src/services/documents/` — document metadata repository and models.
- `src/shared/` — config, database helpers, logging, events.
- `tests/conftest.py` — integration fixtures, especially `migrated_engine`.

## Common tests

- `tests/unit/test_<area>.py -q`
- `tests/integration/test_<area>.py -q`
- Target route tests before full-suite tests.

## Patterns to preserve

- Auth dependency: `Depends(current_user)`.
- Admin-only operation: `require_admin(user)`.
- Document access: `assert_doc_access(doc_id, user, auth_repo)` before protected document reads/mutations.
- DB transaction pattern: `with app.state.engine.begin() as connection:`.
- SQL UUID binding: `shared.db.db_uuid(value)`.
- SQL should use SQLAlchemy bound parameters; do not interpolate SQL strings.

## Do not touch unless required

- `spec.md`
- `spec-v4.pdf`
- unrelated routes in `src/services/api/main.py`
- migrations unless schema changes are required
- frontend files unless UI behavior is part of the issue

## Discovery commands

```bash
rg "<route-or-function>" src/services tests
rg --files src/services/api src/services/auth src/services/permissions tests
```
