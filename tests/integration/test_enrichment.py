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
from services.documents.repository import DocumentRepository
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


def test_manual_translate_creates_version(
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

    response = client.post(
        f"/documents/{doc_id}/translate",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["doc_id"] == doc_id
    assert "translation_version_id" in data
    assert data["status"] == "pending"

    # Verify version was created in DB
    with migrated_engine.begin() as connection:
        row = connection.execute(
            sa.text(
                """
                SELECT quality, request_type, status
                FROM document_translation_versions
                WHERE doc_id = :doc_id
                """
            ),
            {"doc_id": db_uuid(UUID(doc_id))},
        ).fetchone()
        assert row is not None
        assert row[0] == "high"
        assert row[1] == "manual"
        assert row[2] == "pending"


def test_manual_translate_allows_new_version_even_when_high(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    """In 05c, multiple manual versions are allowed."""
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Content")

    _source_id, doc_id = _create_source_with_doc(
        migrated_engine, "users", path=str(test_file), translation_quality="high"
    )

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    response = client.post(
        f"/documents/{doc_id}/translate",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "translation_version_id" in data
    assert data["status"] == "pending"

    # Verify two versions exist (one would have been auto-created by the
    # test helper if it set quality=high, but here we check the new one)
    with migrated_engine.begin() as connection:
        count = connection.execute(
            sa.text(
                """
                SELECT COUNT(*) FROM document_translation_versions
                WHERE doc_id = :doc_id
                """
            ),
            {"doc_id": db_uuid(UUID(doc_id))},
        ).scalar_one()
        assert count == 1


def test_manual_translate_forbids_unauthorized(
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

    response = client.post(
        f"/documents/{doc_id}/translate",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_auto_enrich_fires_when_threshold_crossed(
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

    # Create 5 distinct users to trigger threshold (default: 5)
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        user_ids = []
        for i in range(5):
            user = auth_repo.create_local_user(
                email=f"viewer{i}@example.com",
                password_hash=hash_password("secret"),
                display_name=f"Viewer {i}",
                is_admin=False,
                group_names=["users"],
            )
            user_ids.append(str(user.id))

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )

    # First 4 previews should NOT trigger auto-enrich
    for i in range(4):
        login = client.post(
            "/auth/login",
            json={"email": f"viewer{i}@example.com", "password": "secret"},
        )
        token = login.json()["access_token"]
        response = client.get(f"/preview/{doc_id}", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["view_count"] == i + 1

    # Verify quality is still "fast"
    with migrated_engine.begin() as connection:
        row = connection.execute(
            sa.text("SELECT translation_quality FROM documents WHERE id = :id"),
            {"id": db_uuid(UUID(doc_id))},
        ).fetchone()
        assert row[0] == "fast"

    # 5th preview should trigger auto-enrich
    login = client.post(
        "/auth/login",
        json={"email": "viewer4@example.com", "password": "secret"},
    )
    token = login.json()["access_token"]
    response = client.get(f"/preview/{doc_id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["view_count"] == 5

    # Verify quality is now "pending_high"
    with migrated_engine.begin() as connection:
        row = connection.execute(
            sa.text("SELECT translation_quality FROM documents WHERE id = :id"),
            {"id": db_uuid(UUID(doc_id))},
        ).fetchone()
        assert row[0] == "pending_high"


def test_auto_enrich_fires_exactly_once(
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

    # Create 6 distinct users
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        for i in range(6):
            auth_repo.create_local_user(
                email=f"viewer{i}@example.com",
                password_hash=hash_password("secret"),
                display_name=f"Viewer {i}",
                is_admin=False,
                group_names=["users"],
            )

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )

    # All 6 users preview the document
    for i in range(6):
        login = client.post(
            "/auth/login",
            json={"email": f"viewer{i}@example.com", "password": "secret"},
        )
        token = login.json()["access_token"]
        client.get(f"/preview/{doc_id}", headers={"Authorization": f"Bearer {token}"})

    # Quality should be "pending_high", not toggling back and forth
    with migrated_engine.begin() as connection:
        row = connection.execute(
            sa.text("SELECT translation_quality FROM documents WHERE id = :id"),
            {"id": db_uuid(UUID(doc_id))},
        ).fetchone()
        assert row[0] == "pending_high"


def test_admin_enrichment_queue_lists_pending(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Content")

    # Create two docs: one pending_high, one fast
    _source_id, doc_id1 = _create_source_with_doc(
        migrated_engine,
        "users",
        doc_title="Pending Doc",
        path=str(test_file),
        translation_quality="pending_high",
    )
    _source_id, doc_id2 = _create_source_with_doc(
        migrated_engine,
        "users",
        doc_title="Fast Doc",
        path=str(test_file),
        translation_quality="fast",
    )

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    admin_token = _admin_token(client)

    response = client.get(
        "/admin/enrichment-queue",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["doc_id"] == doc_id1
    assert data[0]["title"] == "Pending Doc"


def test_admin_enrichment_queue_requires_admin(
    migrated_engine: Engine,
) -> None:
    _setup_users(migrated_engine)

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    response = client.get(
        "/admin/enrichment-queue",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_slow_worker_processes_pending_high(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Hello world document content.")

    _source_id, doc_id = _create_source_with_doc(
        migrated_engine, "users", path=str(test_file), translation_quality="pending_high"
    )

    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_translator = MagicMock()
    mock_translator.translate.return_value = "Translated hello world document content."

    from services.pipeline.slow_worker import SlowWorker
    from services.search.encoder import MockEncoder

    with migrated_engine.begin() as connection:
        doc_repo = DocumentRepository(connection)
        worker = SlowWorker(
            document_repository=doc_repo,
            extractor_registry=None,  # use real registry for text files
            translator=mock_translator,
            encoder=MockEncoder(),
            es_client=mock_es,
            qdrant_client=mock_qdrant,
        )
        worker.process_document(UUID(doc_id))

    # Verify quality updated to 'high' and status to 'indexed'
    with migrated_engine.begin() as connection:
        row = connection.execute(
            sa.text("SELECT translation_quality, status FROM documents WHERE id = :id"),
            {"id": db_uuid(UUID(doc_id))},
        ).fetchone()
        assert row[0] == "high"
        assert row[1] == "indexed"

    # Verify ES and Qdrant were called
    mock_es.index_document.assert_called_once()
    mock_qdrant.upsert_chunks.assert_called_once()
    with migrated_engine.begin() as connection:
        user_group_id = AuthRepository(connection).ensure_group("users")
    indexed_doc = mock_es.index_document.call_args.args[1]
    assert indexed_doc["allowed_group_ids"] == [str(user_group_id)]
    qdrant_chunks = mock_qdrant.upsert_chunks.call_args.args[0]
    assert qdrant_chunks[0]["group_id"] == [str(user_group_id)]


def test_slow_worker_failure_sets_failed(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Content")

    _source_id, doc_id = _create_source_with_doc(
        migrated_engine, "users", path=str(test_file), translation_quality="pending_high"
    )

    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_translator = MagicMock()
    mock_translator.translate.side_effect = RuntimeError("Translation failed")

    from services.pipeline.slow_worker import SlowWorker
    from services.search.encoder import MockEncoder

    with migrated_engine.begin() as connection:
        doc_repo = DocumentRepository(connection)
        worker = SlowWorker(
            document_repository=doc_repo,
            extractor_registry=None,
            translator=mock_translator,
            encoder=MockEncoder(),
            es_client=mock_es,
            qdrant_client=mock_qdrant,
        )
        worker.process_document(UUID(doc_id))

    # Verify status is 'failed', quality remains 'pending_high'
    with migrated_engine.begin() as connection:
        row = connection.execute(
            sa.text("SELECT translation_quality, status FROM documents WHERE id = :id"),
            {"id": db_uuid(UUID(doc_id))},
        ).fetchone()
        assert row[0] == "pending_high"
        assert row[1] == "failed"

    # Verify ES and Qdrant were NOT called
    mock_es.index_document.assert_not_called()
    mock_qdrant.upsert_chunks.assert_not_called()
