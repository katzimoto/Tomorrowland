"""Regression tests for connector metadata and content-version persistence."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

import services.api.main as api_main
import services.api.routers.admin.ingestion as ingestion_router
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.connectors.base import ConnectorDocument
from services.documents.repository import DocumentRepository
from services.search.elastic import ElasticsearchSearchClient
from services.search.qdrant import QdrantSearchClient
from services.translation.client import LibreTranslateClient
from shared.config import Settings


def test_create_persists_metadata(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        source_id = _create_source(connection)
        repo = DocumentRepository(connection)

        doc = repo.create(
            source_id=source_id,
            external_id="smb://fileserver/department/legal/report.txt",
            source="smb",
            mime_type="text/plain",
            title="report.txt",
            metadata={"server": "fileserver", "remote_path": "legal/report.txt", "size": 123},
        )

        assert doc is not None
        fetched = repo.get_by_id(doc.id)

    assert fetched is not None
    assert fetched.metadata == {
        "server": "fileserver",
        "remote_path": "legal/report.txt",
        "size": 123,
    }


def test_create_allows_same_source_file_with_different_sha(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        source_id = _create_source(connection)
        repo = DocumentRepository(connection)
        external_id = "file:/data/ingest/test1.txt"

        first = repo.create(
            source_id=source_id,
            external_id=external_id,
            source="folder",
            mime_type="text/plain",
            path="/data/ingest/test1.txt",
            title="test1.txt",
            sha256="a" * 64,
            metadata={"same": "metadata"},
        )
        duplicate = repo.create(
            source_id=source_id,
            external_id=external_id,
            source="folder",
            mime_type="text/plain",
            path="/data/ingest/test1.txt",
            title="test1.txt",
            sha256="a" * 64,
            metadata={"same": "metadata"},
        )
        changed = repo.create(
            source_id=source_id,
            external_id=external_id,
            source="folder",
            mime_type="text/plain",
            path="/data/ingest/test1.txt",
            title="test1.txt",
            sha256="b" * 64,
            metadata={"same": "metadata"},
        )

        rows = (
            connection.execute(
                sa.text(
                    """
                    SELECT external_id, path, title, content_sha256, metadata
                    FROM documents
                    WHERE source_id = :source_id AND external_id = :external_id
                    ORDER BY content_sha256
                    """
                ),
                {"source_id": source_id.hex, "external_id": external_id},
            )
            .mappings()
            .all()
        )

    assert first is not None
    assert duplicate is None
    assert changed is not None
    assert changed.id != first.id
    assert changed.external_id == first.external_id
    assert changed.path == first.path
    assert changed.title == first.title
    assert changed.metadata == first.metadata
    assert [row["content_sha256"] for row in rows] == ["a" * 64, "b" * 64]


def _create_source(connection: sa.Connection) -> UUID:
    source_id = uuid4()
    connection.execute(
        sa.text(
            """
            INSERT INTO ingestion_sources (id, name, type, source_language)
            VALUES (:id, :name, 'smb', 'en')
            """
        ),
        {"id": source_id.hex, "name": "test-smb-source"},
    )
    return source_id


TEST_JWT_SECRET = "x" * 32


class _MetadataConnector:
    def validate(self) -> None:
        return None

    def fetch_documents(self) -> list[ConnectorDocument]:
        return [
            ConnectorDocument(
                external_id="smb://fileserver/department/legal/report.txt",
                title="report.txt",
                mime_type="text/plain",
                sha256="b" * 64,
                source_language=None,
                text_content="hello from smb",
                metadata={"server": "fileserver", "remote_path": "legal/report.txt"},
            )
        ]


def test_sync_now_persists_connector_metadata(
    migrated_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        admin_group_id = auth_repo.ensure_group("admins")
        auth_repo.create_local_user(
            email="admin@example.com",
            password_hash=hash_password("secret"),
            display_name="Admin",
            is_admin=True,
            group_names=["admins"],
        )
        source_id = _create_source(connection)
        auth_repo.grant_source_to_group(source_id, admin_group_id)

    monkeypatch.setattr(
        ingestion_router, "build_connector", lambda _source_row: _MetadataConnector()
    )
    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_translator = MagicMock(spec=LibreTranslateClient)
    mock_translator.translate.return_value = "bonjour from smb"
    client = TestClient(
        api_main.create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            translator=mock_translator,
            es_client=mock_es,
            qdrant_client=mock_qdrant,
        )
    )
    login = client.post("/auth/login", json={"email": "admin@example.com", "password": "secret"})
    assert login.status_code == 200

    response = client.post(
        f"/admin/ingestion/{source_id}/sync-now",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )

    assert response.status_code == 200
    with migrated_engine.connect() as connection:
        metadata = connection.execute(
            sa.text("SELECT metadata FROM documents WHERE source_id = :source_id"),
            {"source_id": source_id.hex},
        ).scalar_one()

    assert metadata == '{"server": "fileserver", "remote_path": "legal/report.txt"}'
