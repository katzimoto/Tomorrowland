from __future__ import annotations

from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.documents.repository import DocumentRepository
from services.intelligence.repository import IntelligenceRepository
from shared.config import Settings
from shared.db import db_uuid

TEST_JWT_SECRET = "x" * 32


def _admin_token(client: TestClient) -> str:
    login = client.post("/auth/login", json={"email": "admin@example.com", "password": "secret"})
    assert login.status_code == 200
    return login.json()["access_token"]


def _user_token(client: TestClient) -> str:
    login = client.post("/auth/login", json={"email": "user@example.com", "password": "secret"})
    assert login.status_code == 200
    return login.json()["access_token"]


def _setup_users(engine: Engine) -> None:
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        auth_repo.create_local_user(
            email="admin@example.com",
            password_hash=hash_password("secret"),
            display_name="Admin",
            is_admin=True,
            group_names=["admins"],
        )
        auth_repo.create_local_user(
            email="user@example.com",
            password_hash=hash_password("secret"),
            display_name="User",
            is_admin=False,
            group_names=["users"],
        )


def _create_source_with_doc(
    engine: Engine,
    group_name: str,
    doc_title: str = "Test Doc",
    mime_type: str = "text/plain",
    path: str = "/data/test.txt",
    translation_quality: str | None = None,
) -> tuple[str, str]:
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group(group_name)
        source_id = auth_repo.create_ingestion_source("Test Source")
        auth_repo.grant_source_to_group(source_id, group_id)

        doc_repo = DocumentRepository(connection)
        doc = doc_repo.create(
            source_id=source_id,
            external_id="file:/data/test.txt",
            source="folder",
            mime_type=mime_type,
            title=doc_title,
            path=path,
        )
        assert doc is not None
        if translation_quality is not None:
            connection.execute(
                sa.text("UPDATE documents SET translation_quality = :quality WHERE id = :id"),
                {"quality": translation_quality, "id": db_uuid(doc.id)},
            )
        return str(source_id), str(doc.id)


def test_get_summary_returns_data(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Content")

    _source_id, document_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

    with migrated_engine.begin() as connection:
        repo = IntelligenceRepository(connection)
        repo.upsert_summary(UUID(document_id), "A test summary", "mistral")

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    response = client.get(
        f"/documents/{document_id}/summary",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == document_id
    assert data["summary"] == "A test summary"
    assert data["model"] == "mistral"


def test_get_summary_404_when_missing(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Content")

    _source_id, document_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    response = client.get(
        f"/documents/{document_id}/summary",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_get_entities_returns_data(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Content")

    _source_id, document_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

    with migrated_engine.begin() as connection:
        repo = IntelligenceRepository(connection)
        entity_id = repo.upsert_entity("Acme Corp", "organization")
        repo.link_document_entity(UUID(document_id), entity_id, frequency=3)

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    response = client.get(
        f"/documents/{document_id}/entities",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Acme Corp"
    assert data[0]["type"] == "organization"
    assert data[0]["frequency"] == 3


def test_get_tags_returns_data(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Content")

    _source_id, document_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

    with migrated_engine.begin() as connection:
        repo = IntelligenceRepository(connection)
        repo.replace_tags(UUID(document_id), ["finance", "Q3"])

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    response = client.get(
        f"/documents/{document_id}/tags",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == document_id
    assert set(data["tags"]) == {"finance", "Q3"}


def test_intelligence_endpoints_require_doc_access(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Content")

    # Create doc for admins only
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        admin_group = auth_repo.ensure_group("admins")
        source_id = auth_repo.create_ingestion_source("Admin Source")
        auth_repo.grant_source_to_group(source_id, admin_group)

        doc_repo = DocumentRepository(connection)
        doc = doc_repo.create(
            source_id=source_id,
            external_id="file:/data/admin.txt",
            source="folder",
            mime_type="text/plain",
            title="Admin Doc",
            path=str(test_file),
        )
        assert doc is not None
        document_id = str(doc.id)

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    for endpoint in ["summary", "entities", "tags"]:
        response = client.get(
            f"/documents/{document_id}/{endpoint}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403


def test_admin_trigger_intelligence(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("This is a document about AI and finance.")

    _source_id, document_id = _create_source_with_doc(
        migrated_engine, "users", path=str(test_file), translation_quality="fast"
    )

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    admin_token = _admin_token(client)

    response = client.post(
        f"/admin/intelligence/{document_id}/trigger",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Should succeed (200) even if Ollama is not available in tests,
    # because the endpoint catches errors from the worker
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == document_id
    assert data["triggered"] is True


def test_admin_trigger_requires_admin(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Content")

    _source_id, document_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    response = client.post(
        f"/admin/intelligence/{document_id}/trigger",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
