from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

from services.auth.repository import AuthRepository
from services.ops.smoke_bootstrap import (
    SmokeBootstrapConfig,
    SmokeBootstrapResult,
    bootstrap_smoke_fixture,
    config_from_env,
)
from shared.config import Settings
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
        fixture_name="tomorrowland-smoke-document.txt",
        query_token="tomorrowland-smoke-unique-token",
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
        fixture_name="tomorrowland-smoke-document.txt",
        query_token="tomorrowland-smoke-unique-token",
        files_root=tmp_path / "data",
    )

    with migrated_engine.begin() as connection, pytest.raises(ValueError, match="FILES_ROOT"):
        bootstrap_smoke_fixture(connection, config)


def test_config_from_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without SMOKE_* env vars the config falls back to documented defaults."""
    for key in (
        "SMOKE_ADMIN_EMAIL",
        "SMOKE_ADMIN_PASSWORD",
        "SMOKE_GROUP_NAME",
        "SMOKE_SOURCE_NAME",
        "SMOKE_FIXTURE_DIR",
        "SMOKE_FIXTURE_NAME",
        "SMOKE_QUERY",
    ):
        monkeypatch.delenv(key, raising=False)

    config = config_from_env(Settings(files_root=Path("/data")))

    assert config.admin_email == "smoke-admin@example.com"
    assert config.group_name == "smoke-operators"
    assert config.source_name == "smoke-folder-source"
    assert config.fixture_dir == Path("/data/smoke-fixtures")
    assert config.fixture_name == "tomorrowland-smoke-document.txt"
    assert config.query_token == "tomorrowland-smoke-unique-token"
    assert config.files_root == Path("/data")


def test_config_from_env_reads_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMOKE_ADMIN_EMAIL", "ops@example.org")
    monkeypatch.setenv("SMOKE_GROUP_NAME", "custom-group")
    monkeypatch.setenv("SMOKE_FIXTURE_DIR", "/data/custom-fixtures")
    monkeypatch.setenv("SMOKE_QUERY", "custom-token")

    config = config_from_env(Settings(files_root=Path("/data")))

    assert config.admin_email == "ops@example.org"
    assert config.group_name == "custom-group"
    assert config.fixture_dir == Path("/data/custom-fixtures")
    assert config.query_token == "custom-token"


def test_fixture_path_joins_dir_and_name() -> None:
    config = SmokeBootstrapConfig(
        admin_email="a@b.c",
        admin_password="pw",
        group_name="g",
        source_name="s",
        fixture_dir=Path("/data/fixtures"),
        fixture_name="doc.txt",
        query_token="tok",
        files_root=Path("/data"),
    )
    assert config.fixture_path == Path("/data/fixtures/doc.txt")


def test_result_to_json_excludes_credentials() -> None:
    """to_json exposes only ids and fixture path — never passwords."""
    result = SmokeBootstrapResult(
        group_id=uuid4(),
        source_id=uuid4(),
        fixture_path=Path("/data/smoke-fixtures/doc.txt"),
    )
    payload = json.loads(result.to_json())

    assert set(payload) == {"group_id", "source_id", "fixture_path"}
    assert payload["group_id"] == str(result.group_id)
    assert payload["source_id"] == str(result.source_id)
    assert payload["fixture_path"] == "/data/smoke-fixtures/doc.txt"
