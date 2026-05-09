from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

from services.auth.repository import AuthRepository
from services.ops.smoke_bootstrap import SmokeBootstrapConfig, bootstrap_smoke_fixture
from shared.db import db_uuid


def test_bootstrap_smoke_fixture_is_idempotent(migrated_engine: Engine, tmp_path: Path) -> None:
    """Smoke bootstrap creates and updates reusable Compose fixtures."""
    fixture_dir = tmp_path / "data" / "smoke-fixtures"
    config = SmokeBootstrapConfig(
        admin_email="smoke-admin@example.com",
        admin_password="safe-smoke-password",
        group_name="smoke-operators",
        source_name="smoke-folder-source",
        fixture_dir=fixture_dir,
        fixture_name="neverland-smoke-document.txt",
        query_token="neverland-smoke-unique-token",
        files_root=tmp_path / "data",
    )

    with migrated_engine.begin() as connection:
        first = bootstrap_smoke_fixture(connection, config)
        second = bootstrap_smoke_fixture(connection, config)
        user = AuthRepository(connection).get_user_by_email(config.admin_email)
        grant_count = connection.execute(
            sa.text(
                """
                SELECT COUNT(*)
                FROM source_permissions
                WHERE source_id = :source_id AND group_id = :group_id
                """
            ),
            {"source_id": db_uuid(second.source_id), "group_id": db_uuid(second.group_id)},
        ).scalar_one()
        source_count = connection.execute(
            sa.text("SELECT COUNT(*) FROM ingestion_sources WHERE name = :name"),
            {"name": config.source_name},
        ).scalar_one()

    assert second.source_id == first.source_id
    assert second.group_id == first.group_id
    assert user is not None
    assert user.is_admin is True
    assert second.group_id in user.groups
    assert grant_count == 1
    assert source_count == 1
    assert second.fixture_path.read_text(encoding="utf-8").count(config.query_token) == 1


def test_bootstrap_rejects_fixture_outside_files_root(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    """Smoke bootstrap refuses to write fixture documents outside FILES_ROOT."""
    config = SmokeBootstrapConfig(
        admin_email="smoke-admin@example.com",
        admin_password="safe-smoke-password",
        group_name="smoke-operators",
        source_name="smoke-folder-source",
        fixture_dir=tmp_path / "outside",
        fixture_name="neverland-smoke-document.txt",
        query_token="neverland-smoke-unique-token",
        files_root=tmp_path / "data",
    )

    with migrated_engine.begin() as connection, pytest.raises(ValueError, match="FILES_ROOT"):
        bootstrap_smoke_fixture(connection, config)
