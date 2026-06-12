from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from testcontainers.rabbitmq import RabbitMqContainer

# Override .env values for test isolation — prevents tests from trying to
# connect to Docker-hosted services (meilisearch, elasticsearch, qdrant, etc.)
os.environ.setdefault("FEATURE_MEILISEARCH_SEARCH", "false")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("RABBITMQ_ENABLED", "false")

_USE_POSTGRES = os.environ.get("PGTEST", "").lower() in ("1", "true", "yes")


@pytest.fixture(autouse=True)
def _clear_config_cache() -> None:
    """Clear the module-level system_config TTL cache between tests.

    config_cache._system_config_cache is a process-level singleton shared
    across tests. Without this, a test that stores a "false" value for
    feature.document_chat will poison subsequent tests that use a fresh
    in-memory DB with the flag enabled.
    """
    from shared.config_cache import invalidate_config_cache

    invalidate_config_cache()


@pytest.fixture(autouse=True)
def _writable_files_root(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Point FILES_ROOT at a writable, per-test directory.

    The ``Settings.files_root`` default is ``/data`` (the production container
    mount), which is not writable in CI or local test runs. Connector tests that
    move ingested files into ``<files_root>/originals`` would otherwise fail with
    zero documents enqueued. We use ``tmp_path`` itself (not a subdir) so that
    folder-source fixtures created under ``tmp_path`` are seen as already inside
    ``files_root`` — mirroring production, where folder sources live under the
    files mount and are not moved. Tests that pass ``files_root=`` explicitly
    still win.
    """
    monkeypatch.setenv("FILES_ROOT", str(tmp_path))


def _postgres_url(database: str | None = None) -> str:
    url = os.environ.get(
        "POSTGRES_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/app"
    )
    if database is None:
        return url
    return sa.engine.make_url(url).set(database=database).render_as_string(hide_password=False)


def _migrate(url: str) -> None:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def _db_template(tmp_path_factory: pytest.TempPathFactory, worker_id: str) -> str | Path:
    """Run the full Alembic chain once per session and return a clonable template.

    Re-running ~46 migrations inside every test made the migration chain, not
    the test bodies, the dominant CI cost. Instead each session (per xdist
    worker) migrates one template — a Postgres template database or a SQLite
    file — and ``migrated_engine`` hands every test a cheap copy of it.
    """
    if _USE_POSTGRES:
        # Per-worker template name so xdist workers never share or lock the
        # same template database.
        template = f"tomorrowland_test_template_{worker_id}"
        admin = sa.create_engine(_postgres_url(), isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{template}" WITH (FORCE)'))
            conn.execute(sa.text(f'CREATE DATABASE "{template}"'))
        admin.dispose()
        _migrate(_postgres_url(template))
        return template
    path = tmp_path_factory.mktemp("db-template") / "template.db"
    _migrate(f"sqlite:///{path}")
    return path


@pytest.fixture()
def migrated_engine(tmp_path: Path, _db_template: str | Path) -> Iterator[Engine]:
    if _USE_POSTGRES:
        # CREATE DATABASE ... TEMPLATE requires zero connections to the
        # template, which holds because _db_template disposed its engine and
        # each xdist worker owns a distinct template.
        database = f"tomorrowland_test_{uuid.uuid4().hex}"
        admin = sa.create_engine(_postgres_url(), isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(sa.text(f'CREATE DATABASE "{database}" TEMPLATE "{_db_template}"'))
        engine = sa.create_engine(_postgres_url(database))
        try:
            yield engine
        finally:
            engine.dispose()
            with admin.connect() as conn:
                conn.execute(sa.text(f'DROP DATABASE "{database}" WITH (FORCE)'))
            admin.dispose()
    else:
        db_path = tmp_path / "tomorrowland.db"
        shutil.copy(_db_template, db_path)
        engine = sa.create_engine(f"sqlite:///{db_path}")
        try:
            yield engine
        finally:
            engine.dispose()


@pytest.fixture(scope="module")
def rabbitmq_container() -> Iterator[str]:
    """Start a RabbitMQ test container and return its connection URL.

    Module-scoped: started once per test module, stopped after all tests.
    Only used by tests marked ``@pytest.mark.e2e``.
    """
    with RabbitMqContainer("rabbitmq:3.13-management-alpine") as rabbit:
        yield rabbit.get_connection_url()
