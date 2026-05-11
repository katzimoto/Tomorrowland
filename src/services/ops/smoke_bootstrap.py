from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from shared.config import Settings
from shared.db import db_uuid, to_uuid


@dataclass(frozen=True)
class SmokeBootstrapConfig:
    """Configuration for the production Compose smoke-test fixture."""

    admin_email: str
    admin_password: str
    group_name: str
    source_name: str
    fixture_dir: Path
    fixture_name: str
    query_token: str
    files_root: Path

    @property
    def fixture_path(self) -> Path:
        """Return the absolute fixture document path inside the runtime container."""
        return self.fixture_dir / self.fixture_name


@dataclass(frozen=True)
class SmokeBootstrapResult:
    """Identifiers and paths created or reused for the smoke fixture."""

    group_id: UUID
    source_id: UUID
    fixture_path: Path

    def to_json(self) -> str:
        """Serialize the bootstrap result without exposing credentials."""
        return json.dumps(
            {
                "group_id": str(self.group_id),
                "source_id": str(self.source_id),
                "fixture_path": str(self.fixture_path),
            },
            sort_keys=True,
        )


def config_from_env(settings: Settings | None = None) -> SmokeBootstrapConfig:
    """Build smoke bootstrap configuration from environment variables."""
    current_settings = settings or Settings()
    return SmokeBootstrapConfig(
        admin_email=os.environ.get("SMOKE_ADMIN_EMAIL", "smoke-admin@example.com"),
        admin_password=os.environ.get("SMOKE_ADMIN_PASSWORD", "tomorrowland-smoke-password"),
        group_name=os.environ.get("SMOKE_GROUP_NAME", "smoke-operators"),
        source_name=os.environ.get("SMOKE_SOURCE_NAME", "smoke-folder-source"),
        fixture_dir=Path(os.environ.get("SMOKE_FIXTURE_DIR", "/data/smoke-fixtures")),
        fixture_name=os.environ.get("SMOKE_FIXTURE_NAME", "tomorrowland-smoke-document.txt"),
        query_token=os.environ.get("SMOKE_QUERY", "tomorrowland-smoke-unique-token"),
        files_root=current_settings.files_root,
    )


def bootstrap_smoke_fixture(
    connection: Connection,
    config: SmokeBootstrapConfig,
) -> SmokeBootstrapResult:
    """Create or update the admin, group, source grant, and fixture document."""
    fixture_path = _safe_fixture_path(config)
    auth_repo = AuthRepository(connection)
    group_id = auth_repo.ensure_group(config.group_name)
    _upsert_admin(auth_repo, connection, config)
    source_id = _upsert_folder_source(connection, config.source_name, config.fixture_dir)
    _grant_source_to_group(connection, source_id, group_id)
    _write_fixture(fixture_path, config.query_token)
    return SmokeBootstrapResult(group_id=group_id, source_id=source_id, fixture_path=fixture_path)


def main() -> None:
    """Run the smoke bootstrap helper against the configured database."""
    settings = Settings()
    engine = sa.create_engine(settings.postgres_url)
    try:
        with engine.begin() as connection:
            result = bootstrap_smoke_fixture(connection, config_from_env(settings))
    finally:
        engine.dispose()
    print(result.to_json())


def _upsert_admin(
    auth_repo: AuthRepository,
    connection: Connection,
    config: SmokeBootstrapConfig,
) -> None:
    existing = auth_repo.get_user_by_email(config.admin_email)
    password_hash = hash_password(config.admin_password)
    if existing is None:
        auth_repo.create_local_user(
            email=config.admin_email,
            password_hash=password_hash,
            display_name="Smoke Admin",
            is_admin=True,
            group_names=[config.group_name],
        )
        return

    connection.execute(
        sa.text(
            """
            UPDATE users
            SET display_name = :display_name,
                auth_source = 'local',
                password_hash = :password_hash,
                is_admin = true
            WHERE id = :id
            """
        ),
        {
            "display_name": "Smoke Admin",
            "password_hash": password_hash,
            "id": db_uuid(existing.id),
        },
    )
    auth_repo.set_user_groups(existing.id, [config.group_name])


def _upsert_folder_source(connection: Connection, source_name: str, fixture_dir: Path) -> UUID:
    row = (
        connection.execute(
            sa.text(
                """
                SELECT id
                FROM ingestion_sources
                WHERE name = :name AND type = 'folder'
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"name": source_name},
        )
        .mappings()
        .first()
    )
    if row is None:
        source_id = uuid4()
        connection.execute(
            sa.text(
                """
                INSERT INTO ingestion_sources
                    (id, name, type, path, source_language, enabled, config)
                VALUES
                    (:id, :name, 'folder', :path, 'en', true, :config)
                """
            ),
            {
                "id": db_uuid(source_id),
                "name": source_name,
                "path": str(fixture_dir),
                "config": json.dumps({}),
            },
        )
        return source_id

    source_id = to_uuid(row["id"])
    connection.execute(
        sa.text(
            """
            UPDATE ingestion_sources
            SET path = :path,
                source_language = 'en',
                enabled = true,
                config = :config
            WHERE id = :id
            """
        ),
        {"id": db_uuid(source_id), "path": str(fixture_dir), "config": json.dumps({})},
    )
    return source_id


def _grant_source_to_group(connection: Connection, source_id: UUID, group_id: UUID) -> None:
    try:
        with connection.begin_nested():
            AuthRepository(connection).grant_source_to_group(source_id, group_id)
    except sa.exc.IntegrityError:
        return


def _safe_fixture_path(config: SmokeBootstrapConfig) -> Path:
    files_root = config.files_root.resolve(strict=False)
    fixture_dir = config.fixture_dir.resolve(strict=False)
    fixture_path = config.fixture_path.resolve(strict=False)
    if not fixture_path.is_relative_to(files_root):
        raise ValueError(
            f"Smoke fixture path {fixture_path} must stay under FILES_ROOT {files_root}."
        )
    if not fixture_path.is_relative_to(fixture_dir):
        raise ValueError(
            f"Smoke fixture path {fixture_path} must stay under SMOKE_FIXTURE_DIR {fixture_dir}."
        )
    return fixture_path


def _write_fixture(fixture_path: Path, query_token: str) -> None:
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(
        "\n".join(
            [
                "Tomorrowland smoke fixture.",
                "This deterministic document verifies ingestion, search, preview, and download.",
                f"Unique query token: {query_token}.",
                "",
            ]
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
