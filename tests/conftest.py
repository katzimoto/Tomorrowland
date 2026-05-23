from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

# Override .env values for test isolation — prevents tests from trying to
# connect to Docker-hosted services (meilisearch, elasticsearch, qdrant, etc.)
os.environ.setdefault("FEATURE_MEILISEARCH_SEARCH", "false")
os.environ.setdefault("APP_ENV", "test")

_USE_POSTGRES = os.environ.get("PGTEST", "").lower() in ("1", "true", "yes")


@pytest.fixture()
def migrated_engine(tmp_path) -> Iterator[Engine]:  # type: ignore[no-untyped-def]
    if _USE_POSTGRES:
        url = os.environ.get("POSTGRES_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/app")
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
