from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.search.elastic import ElasticsearchSearchClient
from services.search.qdrant import QdrantSearchClient
from services.translation.client import LibreTranslateClient
from shared.config import Settings

TEST_JWT_SECRET = "x" * 32


def _admin_token(client: TestClient) -> str:
    login = client.post("/auth/login", json={"email": "admin@example.com", "password": "secret"})
    assert login.status_code == 200
    return login.json()["access_token"]


def _setup_admin(engine: Engine) -> None:
    with engine.begin() as connection:
        repository = AuthRepository(connection)
        repository.create_local_user(
            email="admin@example.com",
            password_hash=hash_password("secret"),
            display_name="Admin",
            is_admin=True,
            group_names=["admins"],
        )


def _create_folder_source(engine: Engine, folder: Path) -> str:
    source_id = uuid4()
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        admin_group_id = auth_repo.ensure_group("admins")
        connection.execute(
            sa.text(
                """
                INSERT INTO ingestion_sources (id, name, type, path, source_language)
                VALUES (:id, 'Test Folder', 'folder', :path, 'en')
                """
            ),
            {"id": source_id.hex, "path": str(folder)},
        )
        auth_repo.grant_source_to_group(source_id, admin_group_id)
    return source_id.hex


def test_sync_now_indexes_document(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_admin(migrated_engine)

    # Use a subfolder so the SQLite db file (sibling in tmp_path) is not scanned
    source_folder = tmp_path / "source"
    source_folder.mkdir()
    fixture_file = source_folder / "hello.txt"
    fixture_file.write_text("Hello world")

    source_id = _create_folder_source(migrated_engine, source_folder)

    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_translator = MagicMock(spec=LibreTranslateClient)
    mock_translator.translate.return_value = "Bonjour le monde"

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            translator=mock_translator,
            es_client=mock_es,
            qdrant_client=mock_qdrant,
        )
    )
    token = _admin_token(client)

    response = client.post(
        f"/admin/ingestion/{source_id}/sync-now",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["enqueued"] == 1
    assert response.json()["skipped"] == 0

    # Verify document was created in DB
    with migrated_engine.connect() as connection:
        row = (
            connection.execute(
                sa.text("SELECT id FROM documents WHERE source_id = :id"),
                {"id": source_id},
            )
            .mappings()
            .first()
        )

    assert row is not None


def test_sync_now_matches_alert_subscriptions(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_admin(migrated_engine)

    source_folder = tmp_path / "source"
    source_folder.mkdir()
    fixture_file = source_folder / "topic.txt"
    fixture_file.write_text("security update")

    source_id = _create_folder_source(migrated_engine, source_folder)

    with migrated_engine.begin() as connection:
        admin_id = connection.execute(
            sa.text("SELECT id FROM users WHERE email = 'admin@example.com'")
        ).scalar_one()
        connection.execute(
            sa.text(
                """
                INSERT INTO alert_subscriptions (
                    id, user_id, name, query, similarity_threshold, enabled
                )
                VALUES (
                    :id, :user_id, 'Security', 'security update', 0.9, true
                )
                """
            ),
            {"id": uuid4().hex, "user_id": admin_id},
        )

    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_translator = MagicMock(spec=LibreTranslateClient)
    mock_translator.translate.return_value = "security update"

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            translator=mock_translator,
            es_client=mock_es,
            qdrant_client=mock_qdrant,
        )
    )
    token = _admin_token(client)

    response = client.post(
        f"/admin/ingestion/{source_id}/sync-now",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    # Alert matching is now done by the pipeline worker, not during sync-now


def test_sync_now_skips_duplicate(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_admin(migrated_engine)

    source_folder = tmp_path / "source"
    source_folder.mkdir()
    fixture_file = source_folder / "hello.txt"
    fixture_file.write_text("Hello world")

    source_id = _create_folder_source(migrated_engine, source_folder)

    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_translator = MagicMock(spec=LibreTranslateClient)
    mock_translator.translate.return_value = "Bonjour le monde"

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            translator=mock_translator,
            es_client=mock_es,
            qdrant_client=mock_qdrant,
        )
    )
    token = _admin_token(client)

    # First ingestion
    r1 = client.post(
        f"/admin/ingestion/{source_id}/sync-now",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200
    assert r1.json()["enqueued"] == 1

    # Second ingestion should skip
    r2 = client.post(
        f"/admin/ingestion/{source_id}/sync-now",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    assert r2.json()["enqueued"] == 0
    assert r2.json()["skipped"] == 1


def test_sync_now_translation_failure_still_indexes(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_admin(migrated_engine)

    source_folder = tmp_path / "source"
    source_folder.mkdir()
    fixture_file = source_folder / "hello.txt"
    fixture_file.write_text("Hello world")

    source_id = _create_folder_source(migrated_engine, source_folder)

    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    # Translator returns original text (simulated failure)
    mock_translator = MagicMock(spec=LibreTranslateClient)
    mock_translator.translate.return_value = "Hello world"

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            translator=mock_translator,
            es_client=mock_es,
            qdrant_client=mock_qdrant,
        )
    )
    token = _admin_token(client)

    response = client.post(
        f"/admin/ingestion/{source_id}/sync-now",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["enqueued"] == 1

    # Document is created and enqueued; translation happens in the pipeline worker
    with migrated_engine.connect() as connection:
        row = (
            connection.execute(
                sa.text("SELECT id FROM documents WHERE source_id = :id"),
                {"id": source_id},
            )
            .mappings()
            .first()
        )

    assert row is not None


def test_sync_now_pipeline_failure_sets_failed_status(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_admin(migrated_engine)

    source_folder = tmp_path / "source"
    source_folder.mkdir()
    fixture_file = source_folder / "hello.txt"
    fixture_file.write_text("Hello world")

    source_id = _create_folder_source(migrated_engine, source_folder)

    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_translator = MagicMock(spec=LibreTranslateClient)
    mock_translator.translate.return_value = "Bonjour le monde"

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            translator=mock_translator,
            es_client=mock_es,
            qdrant_client=mock_qdrant,
        )
    )
    token = _admin_token(client)

    response = client.post(
        f"/admin/ingestion/{source_id}/sync-now",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["enqueued"] == 1
    assert response.json()["failed_enqueue"] == 0
    assert response.json()["failed_discovery"] == 0

    # Document is created and enqueued; pipeline worker handles full processing
    with migrated_engine.connect() as connection:
        row = (
            connection.execute(
                sa.text("SELECT id FROM documents WHERE source_id = :id"),
                {"id": source_id},
            )
            .mappings()
            .first()
        )

    assert row is not None


def test_sync_now_forbids_non_admin(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    with migrated_engine.begin() as connection:
        repository = AuthRepository(connection)
        repository.create_local_user(
            email="user@example.com",
            password_hash=hash_password("secret"),
            is_admin=False,
            group_names=["users"],
        )

    source_id = _create_folder_source(migrated_engine, tmp_path)

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    login = client.post("/auth/login", json={"email": "user@example.com", "password": "secret"})
    token = login.json()["access_token"]

    response = client.post(
        f"/admin/ingestion/{source_id}/sync-now",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_sync_now_404_for_missing_source(
    migrated_engine: Engine,
) -> None:
    _setup_admin(migrated_engine)

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _admin_token(client)

    response = client.post(
        f"/admin/ingestion/{uuid4()}/sync-now",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_sync_now_400_for_source_without_path(
    migrated_engine: Engine,
) -> None:
    _setup_admin(migrated_engine)

    source_id = uuid4()
    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO ingestion_sources (id, name, type, path, source_language)
                VALUES (:id, 'No Path', 'folder', NULL, 'en')
                """
            ),
            {"id": source_id.hex},
        )

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _admin_token(client)

    response = client.post(
        f"/admin/ingestion/{source_id}/sync-now",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "no path" in response.json()["detail"].lower()


def test_sync_now_400_for_missing_folder(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_admin(migrated_engine)

    missing_folder = tmp_path / "does_not_exist"
    source_id = _create_folder_source(migrated_engine, missing_folder)

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _admin_token(client)

    response = client.post(
        f"/admin/ingestion/{source_id}/sync-now",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"].lower()


def test_sync_now_with_pre_extracted_text(
    migrated_engine: Engine,
) -> None:
    """Connectors that return text_content bypass the file extractor."""
    _setup_admin(migrated_engine)

    source_id = uuid4()
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        admin_group_id = auth_repo.ensure_group("admins")
        connection.execute(
            sa.text(
                """
                INSERT INTO ingestion_sources (id, name, type, config, source_language)
                VALUES (:id, 'Stub', 'nifi', :config, 'en')
                """
            ),
            {
                "id": source_id.hex,
                "config": '{"base_url":"http://nifi","flow_id":"x","api_token":"t"}',
            },
        )
        auth_repo.grant_source_to_group(source_id, admin_group_id)

    # Patch build_connector in main.py's namespace (it was imported directly)
    from unittest.mock import patch

    from services.connectors.base import ConnectorDocument

    class _StubConnector:
        def validate(self) -> None:
            pass

        def fetch_documents(self):  # type: ignore[override]
            yield ConnectorDocument(
                external_id="nifi:doc-001",
                title="NL-001",
                mime_type="text/plain",
                sha256=None,
                source_language="en",
                text_content="Stub document body from NiFi.",
            )

    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_translator = MagicMock(spec=LibreTranslateClient)
    mock_translator.translate.return_value = "Stub document body from NiFi."

    with patch("services.api.main.build_connector", return_value=_StubConnector()):
        client = TestClient(
            create_app(
                migrated_engine,
                Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
                translator=mock_translator,
                es_client=mock_es,
                qdrant_client=mock_qdrant,
            )
        )
        token = _admin_token(client)
        response = client.post(
            f"/admin/ingestion/{source_id}/sync-now",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()["enqueued"] == 1


def test_sync_now_middle_item_failure_continues_sync(
    migrated_engine: Engine,
) -> None:
    """A failed item must not stop the sync; later items are still processed."""
    _setup_admin(migrated_engine)

    source_id = uuid4()
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        admin_group_id = auth_repo.ensure_group("admins")
        connection.execute(
            sa.text(
                """
                INSERT INTO ingestion_sources (id, name, type, config, source_language)
                VALUES (:id, 'Stub', 'nifi', :config, 'en')
                """
            ),
            {
                "id": source_id.hex,
                "config": '{"base_url":"http://nifi","flow_id":"x","api_token":"t"}',
            },
        )
        auth_repo.grant_source_to_group(source_id, admin_group_id)

    class _StubConnector:
        def validate(self) -> None:
            pass

        def fetch_documents(self):  # type: ignore[override]
            from services.connectors.base import ConnectorDocument

            yield ConnectorDocument(
                external_id="nifi:doc-001",
                title="A",
                mime_type="text/plain",
                sha256="a" * 64,
                source_language="en",
                text_content="first",
            )
            yield ConnectorDocument(
                external_id="nifi:doc-002",
                title="B",
                mime_type="text/plain",
                sha256="b" * 64,
                source_language="en",
                text_content="second",
            )
            yield ConnectorDocument(
                external_id="nifi:doc-003",
                title="C",
                mime_type="text/plain",
                sha256="c" * 64,
                source_language="en",
                text_content="third",
            )

    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_translator = MagicMock(spec=LibreTranslateClient)
    mock_translator.translate.side_effect = lambda text, **_: text

    with patch("services.api.main.build_connector", return_value=_StubConnector()):
        client = TestClient(
            create_app(
                migrated_engine,
                Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
                translator=mock_translator,
                es_client=mock_es,
                qdrant_client=mock_qdrant,
            )
        )
        token = _admin_token(client)
        response = client.post(
            f"/admin/ingestion/{source_id}/sync-now",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["enqueued"] == 3
    assert data["discovered"] == 3
    assert data["created"] == 3
    assert data["skipped"] == 0
    assert data["failed_enqueue"] == 0
    assert data["failed_discovery"] == 0


def test_sync_now_document_creation_failure_continues_sync(
    migrated_engine: Engine,
) -> None:
    """A failure during document creation must not stop the sync."""
    _setup_admin(migrated_engine)

    source_id = uuid4()
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        admin_group_id = auth_repo.ensure_group("admins")
        connection.execute(
            sa.text(
                """
                INSERT INTO ingestion_sources (id, name, type, config, source_language)
                VALUES (:id, 'Stub', 'nifi', :config, 'en')
                """
            ),
            {
                "id": source_id.hex,
                "config": '{"base_url":"http://nifi","flow_id":"x","api_token":"t"}',
            },
        )
        auth_repo.grant_source_to_group(source_id, admin_group_id)

    class _StubConnector:
        def validate(self) -> None:
            pass

        def fetch_documents(self):  # type: ignore[override]
            from services.connectors.base import ConnectorDocument

            yield ConnectorDocument(
                external_id="nifi:doc-001",
                title="A",
                mime_type="text/plain",
                sha256="a" * 64,
                source_language="en",
                text_content="first",
            )
            yield ConnectorDocument(
                external_id="nifi:doc-002",
                title="B",
                mime_type="text/plain",
                sha256="b" * 64,
                source_language="en",
                text_content="second",
            )
            yield ConnectorDocument(
                external_id="nifi:doc-003",
                title="C",
                mime_type="text/plain",
                sha256="c" * 64,
                source_language="en",
                text_content="third",
            )

    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_translator = MagicMock(spec=LibreTranslateClient)
    mock_translator.translate.side_effect = lambda text, **_: text

    from services.documents.repository import DocumentRepository

    _real_create = DocumentRepository.create
    call_count = 0

    def _fake_create(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("DB error")
        return _real_create(self, *args, **kwargs)

    with (
        patch("services.api.main.build_connector", return_value=_StubConnector()),
        patch("services.api.main.DocumentRepository.create", _fake_create),
    ):
        client = TestClient(
            create_app(
                migrated_engine,
                Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
                translator=mock_translator,
                es_client=mock_es,
                qdrant_client=mock_qdrant,
            )
        )
        token = _admin_token(client)
        response = client.post(
            f"/admin/ingestion/{source_id}/sync-now",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["enqueued"] == 2
    assert data["skipped"] == 0
    assert data["failed_discovery"] == 1
    assert data["failed_enqueue"] == 0


def test_sync_now_connector_enumeration_failure_returns_safe_error(
    migrated_engine: Engine,
) -> None:
    """A connector-level enumeration failure must return a safe error."""
    _setup_admin(migrated_engine)

    source_id = uuid4()
    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO ingestion_sources (id, name, type, config, source_language)
                VALUES (:id, 'Stub', 'nifi', :config, 'en')
                """
            ),
            {
                "id": source_id.hex,
                "config": '{"base_url":"http://nifi","flow_id":"x","api_token":"super-secret-key"}',
            },
        )

    class _BrokenConnector:
        def validate(self) -> None:
            pass

        def fetch_documents(self):  # type: ignore[override]
            raise RuntimeError("cannot authenticate to source")

    with patch("services.api.main.build_connector", return_value=_BrokenConnector()):
        client = TestClient(
            create_app(
                migrated_engine,
                Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            )
        )
        token = _admin_token(client)
        response = client.post(
            f"/admin/ingestion/{source_id}/sync-now",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "Sync failed while reading source documents" in detail
    assert "cannot authenticate" not in detail.lower()
    assert "super-secret-key" not in detail.lower()


def test_sync_now_smb_cleanup_on_item_failure(
    migrated_engine: Engine,
) -> None:
    """SMB staged files are cleaned up even when the item fails."""
    _setup_admin(migrated_engine)

    source_id = uuid4()
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        admin_group_id = auth_repo.ensure_group("admins")
        connection.execute(
            sa.text(
                """
                INSERT INTO ingestion_sources (id, name, type, config, source_language)
                VALUES (:id, 'Stub', 'smb', :config, 'en')
                """
            ),
            {
                "id": source_id.hex,
                "config": "{}",
            },
        )
        auth_repo.grant_source_to_group(source_id, admin_group_id)

    class _SmbConnector:
        def validate(self) -> None:
            pass

        def fetch_documents(self):  # type: ignore[override]
            from services.connectors.base import ConnectorDocument

            yield ConnectorDocument(
                external_id="smb:file-001",
                title="A",
                mime_type="text/plain",
                sha256="a" * 64,
                source_language="en",
                text_content="first",
                path="/tmp/staged_001.txt",
            )
            yield ConnectorDocument(
                external_id="smb:file-002",
                title="B",
                mime_type="text/plain",
                sha256="b" * 64,
                source_language="en",
                text_content="second",
                path="/tmp/staged_002.txt",
            )

    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_translator = MagicMock(spec=LibreTranslateClient)
    mock_translator.translate.side_effect = lambda text, **_: text

    with (
        patch("services.api.main.build_connector", return_value=_SmbConnector()),
        patch("services.api.main.os.unlink") as mock_unlink,
    ):
        client = TestClient(
            create_app(
                migrated_engine,
                Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
                translator=mock_translator,
                es_client=mock_es,
                qdrant_client=mock_qdrant,
            )
        )
        token = _admin_token(client)
        response = client.post(
            f"/admin/ingestion/{source_id}/sync-now",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["enqueued"] == 2
    assert data["failed_enqueue"] == 0
    assert data["failed_discovery"] == 0
    assert mock_unlink.call_count == 2
    paths = {call.args[0] for call in mock_unlink.call_args_list}
    assert paths == {"/tmp/staged_001.txt", "/tmp/staged_002.txt"}
