"""Migration downgrade smoke tests.

For the 5 most recent Alembic revisions, verify the round-trip:

    upgrade (to revision) → downgrade -1 → upgrade head

This proves that every recently shipped migration has a working downgrade path
(Alembic requires a downgrade function, but nothing currently calls it in CI).

SQLite variant runs in the regular unit-test suite (no services required).
PostgreSQL variant is guarded by ``PGTEST=1`` and runs in the nightly job.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

_N_RECENT = 5
_USE_POSTGRES = os.environ.get("PGTEST", "").lower() in ("1", "true", "yes")


def _alembic_cfg(db_url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _recent_revision_ids(n: int = _N_RECENT) -> list[str]:
    """Return the revision IDs of the N most recent migrations (head first)."""
    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    revs: list[str] = []
    for rev in script.walk_revisions():
        revs.append(rev.revision)
        if len(revs) == n:
            break
    return revs


def _postgres_base_url() -> str:
    return os.environ.get(
        "POSTGRES_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/app",
    )


def _postgres_db_url(database: str) -> str:
    return str(sa.engine.make_url(_postgres_base_url()).set(database=database))


# Collected at module import time so parametrize IDs are stable across workers.
RECENT_REVISION_IDS = _recent_revision_ids()


# ---------------------------------------------------------------------------
# SQLite — runs in every CI job (no services required)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("revision_id", RECENT_REVISION_IDS)
def test_migration_downgrade_sqlite(revision_id: str, tmp_path: Path) -> None:
    """upgrade → revision → downgrade -1 → upgrade head (SQLite)."""
    cfg = _alembic_cfg(f"sqlite:///{tmp_path / 'smoke.db'}")
    command.upgrade(cfg, revision_id)
    command.downgrade(cfg, "-1")
    command.upgrade(cfg, "head")


# ---------------------------------------------------------------------------
# PostgreSQL — guarded by PGTEST=1 (nightly job only)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _USE_POSTGRES, reason="Postgres not available; set PGTEST=1")
@pytest.mark.parametrize("revision_id", RECENT_REVISION_IDS)
def test_migration_downgrade_postgres(revision_id: str) -> None:
    """upgrade → revision → downgrade -1 → upgrade head (PostgreSQL)."""
    database = f"tomorrowland_downgrade_{uuid.uuid4().hex[:12]}"
    admin_url = _postgres_base_url()
    db_url = _postgres_db_url(database)

    admin = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{database}"'))
    admin.dispose()

    try:
        cfg = _alembic_cfg(db_url)
        command.upgrade(cfg, revision_id)
        command.downgrade(cfg, "-1")
        command.upgrade(cfg, "head")
    finally:
        admin = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
        admin.dispose()
