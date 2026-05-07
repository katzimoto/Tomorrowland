from __future__ import annotations

from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine


@pytest.fixture()
def migrated_engine(tmp_path) -> Iterator[Engine]:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "neverland.db"
    url = f"sqlite:///{db_path}"
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)

    command.upgrade(cfg, "head")

    engine = sa.create_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()
