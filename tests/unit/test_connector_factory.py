"""Connector factory registry tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.engine import RowMapping

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.connectors.factory import build_connector, connector_types
from services.connectors.smb import SmbConnector
from shared.config import Settings

TEST_JWT_SECRET = "x" * 32


def _make_row(**kwargs: object) -> RowMapping:
    mock = MagicMock(spec=RowMapping)
    mock.__getitem__ = lambda self, key: kwargs[key]
    mock.get = lambda key, default=None: kwargs.get(key, default)
    return mock


def _setup_admin(engine: Engine) -> None:
    with engine.begin() as connection:
        AuthRepository(connection).create_local_user(
            email="admin@example.com",
            password_hash=hash_password("secret"),
            display_name="Admin",
            is_admin=True,
            group_names=["admins"],
        )


def _admin_token(client: TestClient) -> str:
    login = client.post("/auth/login", json={"email": "admin@example.com", "password": "secret"})
    assert login.status_code == 200
    return str(login.json()["access_token"])


def test_factory_builds_smb_connector() -> None:
    row = _make_row(
        type="smb",
        config=json.dumps(
            {
                "server": "fileserver.local",
                "share": "department",
                "username": "svc-tomorrowland",
                "password": "secret",
            }
        ),
    )

    assert isinstance(build_connector(row), SmbConnector)


def test_connector_types_includes_smb() -> None:
    types = {item["type"]: item for item in connector_types()}

    assert "smb" in types
    assert types["smb"]["label"] == "SMB"
    assert any(
        field["key"] == "password" and field["sensitive"] for field in types["smb"]["fields"]
    )


def test_admin_connector_types_endpoint_includes_smb(migrated_engine: Engine) -> None:
    _setup_admin(migrated_engine)
    client = TestClient(
        create_app(migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET))
    )
    token = _admin_token(client)

    response = client.get("/admin/connector-types", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert "smb" in {item["type"] for item in response.json()}


def test_admin_source_creation_accepts_smb(migrated_engine: Engine) -> None:
    _setup_admin(migrated_engine)
    client = TestClient(
        create_app(migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET))
    )
    token = _admin_token(client)

    response = client.post(
        "/admin/sources",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Windows Share",
            "type": "smb",
            "source_language": "en",
            "config": {
                "server": "fileserver.local",
                "share": "department",
                "username": "svc-tomorrowland",
                "password": "secret",
            },
        },
    )

    assert response.status_code == 201
    assert response.json()["type"] == "smb"

    with migrated_engine.connect() as connection:
        source_type = connection.execute(
            sa.text("SELECT type FROM ingestion_sources WHERE name = 'Windows Share'")
        ).scalar_one()
    assert source_type == "smb"


def test_admin_source_languages_endpoint_returns_configured_languages(migrated_engine: Engine) -> None:
    _setup_admin(migrated_engine)
    settings = Settings(
        auth_provider="local",
        jwt_secret=TEST_JWT_SECRET,
        supported_translation_source_languages="en,he,fr",
    )
    client = TestClient(create_app(migrated_engine, settings))
    token = _admin_token(client)

    response = client.get("/admin/source-languages", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == ["en", "he", "fr"]


def test_admin_source_languages_endpoint_default_includes_major_languages(migrated_engine: Engine) -> None:
    _setup_admin(migrated_engine)
    client = TestClient(
        create_app(migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET))
    )
    token = _admin_token(client)

    response = client.get("/admin/source-languages", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    assert "en" in data
    assert "he" in data
    assert "ar" in data


def test_db_constraints_allow_smb_source_and_document(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        source_id = "00112233445566778899aabbccddeeff"
        doc_id = "11112233445566778899aabbccddeeff"
        connection.execute(
            sa.text(
                """
                INSERT INTO ingestion_sources (id, name, type, source_language)
                VALUES (:id, 'SMB', 'smb', 'en')
                """
            ),
            {"id": source_id},
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO documents (id, source_id, external_id, source, mime_type)
                VALUES (:id, :source_id, 'smb://fileserver/share/a.txt', 'smb', 'text/plain')
                """
            ),
            {"id": doc_id, "source_id": source_id},
        )

        row = connection.execute(
            sa.text("SELECT source FROM documents WHERE id = :id"), {"id": doc_id}
        ).scalar_one()

    assert row == "smb"
