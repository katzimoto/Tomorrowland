from __future__ import annotations

import os
from collections.abc import Iterator

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


@pytest.fixture()
def migrated_engine(tmp_path) -> Iterator[Engine]:  # type: ignore[no-untyped-def]
    if _USE_POSTGRES:
        url = os.environ.get(
            "POSTGRES_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/app"
        )
        # This fixture is function-scoped but the same Postgres database is
        # reused across tests, so rows from a prior test persist. Reset the
        # schema before migrating so each test starts clean — otherwise setup
        # helpers that insert fixed-email users collide on uq_users_email.
        # (SQLite gets this isolation for free via a fresh tmp_path file.)
        reset_engine = sa.create_engine(url)
        with reset_engine.begin() as conn:
            conn.execute(sa.text("DROP SCHEMA public CASCADE"))
            conn.execute(sa.text("CREATE SCHEMA public"))
        reset_engine.dispose()
    else:
        db_path = tmp_path / "tomorrowland.db"
        url = f"sqlite:///{db_path}"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)

    command.upgrade(cfg, "head")

    engine = sa.create_engine(url)
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
