from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.documents.repository import DocumentRepository, TranslationVersionRepository
from services.search.elastic import ElasticsearchSearchClient
from services.search.qdrant import QdrantSearchClient
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


def test_list_translation_versions(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Content")

    _source_id, doc_id = _create_source_with_doc(
        migrated_engine, "users", path=str(test_file), translation_quality="fast"
    )

    # Create two versions
    with migrated_engine.begin() as connection:
        version_repo = TranslationVersionRepository(connection)
        version_repo.create_version(
            doc_id=UUID(doc_id),
            label="Manual en",
            quality="high",
            request_type="manual",
            target_language="en",
        )
        version_repo.create_version(
            doc_id=UUID(doc_id),
            label="Auto-enrich",
            quality="high",
            request_type="auto_enrich",
            target_language="en",
        )

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    response = client.get(
        f"/documents/{doc_id}/translation-versions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["version_number"] == 2
    assert data[1]["version_number"] == 1


def test_list_versions_requires_doc_access(
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
        doc_id = str(doc.id)

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    response = client.get(
        f"/documents/{doc_id}/translation-versions",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_preview_with_translation_version(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Original content here.")

    _source_id, doc_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

    # Create an available version with translated text
    with migrated_engine.begin() as connection:
        version_repo = TranslationVersionRepository(connection)
        version = version_repo.create_version(
            doc_id=UUID(doc_id),
            label="Manual en",
            quality="high",
            request_type="manual",
            target_language="en",
        )
        version_id = version["id"]
        version_repo.update_version_status(
            UUID(version_id), "available", translated_text="Translated content here."
        )

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    # Preview with version should return translated text
    response = client.get(
        f"/preview/{doc_id}?translation_version_id={version_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["snippet"] == "Translated content here."


def test_preview_with_unavailable_version_falls_back(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Original content here.")

    _source_id, doc_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

    # Create a pending version (not available)
    with migrated_engine.begin() as connection:
        version_repo = TranslationVersionRepository(connection)
        version = version_repo.create_version(
            doc_id=UUID(doc_id),
            label="Manual en",
            quality="high",
            request_type="manual",
            target_language="en",
        )
        version_id = version["id"]

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    # Preview with pending version should fall back to original
    response = client.get(
        f"/preview/{doc_id}?translation_version_id={version_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["snippet"] == "Original content here."


def test_duplicate_pending_request_returns_existing(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Content")

    _source_id, doc_id = _create_source_with_doc(
        migrated_engine, "users", path=str(test_file), translation_quality="fast"
    )

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    # First request
    response1 = client.post(
        f"/documents/{doc_id}/translate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response1.status_code == 200
    version_id_1 = response1.json()["translation_version_id"]

    # Second request should return the same pending version
    response2 = client.post(
        f"/documents/{doc_id}/translate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response2.status_code == 200
    version_id_2 = response2.json()["translation_version_id"]

    assert version_id_1 == version_id_2


def test_slow_worker_with_version_repository(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Hello world document content.")

    _source_id, doc_id = _create_source_with_doc(
        migrated_engine, "users", path=str(test_file), translation_quality="fast"
    )

    # Create a pending version
    with migrated_engine.begin() as connection:
        version_repo = TranslationVersionRepository(connection)
        version = version_repo.create_version(
            doc_id=UUID(doc_id),
            label="Manual en",
            quality="high",
            request_type="manual",
            target_language="en",
        )
        version_id = version["id"]
        doc_repo = DocumentRepository(connection)
        doc_repo.update_translation_quality(UUID(doc_id), "pending_high")

    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_translator = MagicMock()
    mock_translator.translate.return_value = "Translated hello world document content."

    from services.pipeline.slow_worker import SlowWorker
    from services.search.encoder import MockEncoder

    with migrated_engine.begin() as connection:
        doc_repo = DocumentRepository(connection)
        version_repo = TranslationVersionRepository(connection)
        worker = SlowWorker(
            document_repository=doc_repo,
            extractor_registry=None,
            translator=mock_translator,
            encoder=MockEncoder(),
            es_client=mock_es,
            qdrant_client=mock_qdrant,
            version_repository=version_repo,
        )
        worker.process_document(UUID(doc_id))

    # Verify version updated to available
    with migrated_engine.begin() as connection:
        row = connection.execute(
            sa.text(
                """
                SELECT status, translated_text
                FROM document_translation_versions
                WHERE id = :id
                """
            ),
            {"id": db_uuid(UUID(version_id))},
        ).fetchone()
        assert row[0] == "available"
        assert row[1] == "Translated hello world document content."

    # Verify document quality updated to high
    with migrated_engine.begin() as connection:
        row = connection.execute(
            sa.text("SELECT translation_quality FROM documents WHERE id = :id"),
            {"id": db_uuid(UUID(doc_id))},
        ).fetchone()
        assert row[0] == "high"

    mock_es.index_document.assert_called_once()
    mock_qdrant.upsert_chunks.assert_called_once()


def test_slow_worker_version_failure_marks_version_failed(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Content")

    _source_id, doc_id = _create_source_with_doc(
        migrated_engine, "users", path=str(test_file), translation_quality="fast"
    )

    # Create a pending version
    with migrated_engine.begin() as connection:
        version_repo = TranslationVersionRepository(connection)
        version = version_repo.create_version(
            doc_id=UUID(doc_id),
            label="Manual en",
            quality="high",
            request_type="manual",
            target_language="en",
        )
        version_id = version["id"]
        doc_repo = DocumentRepository(connection)
        doc_repo.update_translation_quality(UUID(doc_id), "pending_high")

    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_translator = MagicMock()
    mock_translator.translate.side_effect = RuntimeError("Translation failed")

    from services.pipeline.slow_worker import SlowWorker
    from services.search.encoder import MockEncoder

    with migrated_engine.begin() as connection:
        doc_repo = DocumentRepository(connection)
        version_repo = TranslationVersionRepository(connection)
        worker = SlowWorker(
            document_repository=doc_repo,
            extractor_registry=None,
            translator=mock_translator,
            encoder=MockEncoder(),
            es_client=mock_es,
            qdrant_client=mock_qdrant,
            version_repository=version_repo,
        )
        worker.process_document(UUID(doc_id))

    # Verify version is failed, document status is not failed
    with migrated_engine.begin() as connection:
        version_row = connection.execute(
            sa.text(
                """
                SELECT status, error_summary
                FROM document_translation_versions
                WHERE id = :id
                """
            ),
            {"id": db_uuid(UUID(version_id))},
        ).fetchone()
        assert version_row[0] == "failed"

        doc_row = connection.execute(
            sa.text("SELECT status FROM documents WHERE id = :id"),
            {"id": db_uuid(UUID(doc_id))},
        ).fetchone()
        assert doc_row[0] != "failed"

    mock_es.index_document.assert_not_called()
    mock_qdrant.upsert_chunks.assert_not_called()
