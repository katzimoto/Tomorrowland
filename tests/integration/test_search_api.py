from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.documents.repository import DocumentRepository
from services.search.elastic import ElasticsearchSearchClient
from services.search.hybrid import SearchResult
from services.search.qdrant import QdrantSearchClient
from shared.config import Settings

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
) -> tuple[str, str]:
    """Create an ingestion source, grant it to a group, and create a document.
    Returns (source_id, doc_id).
    """
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
            mime_type="text/plain",
            title=doc_title,
            path="/data/test.txt",
        )
        assert doc is not None
        return str(source_id), str(doc.id)


def test_search_returns_matching_documents(
    migrated_engine: Engine,
) -> None:
    _setup_users(migrated_engine)

    source_id, doc_id = _create_source_with_doc(migrated_engine, "users", "Hello Doc")

    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_es.search.return_value = [SearchResult(doc_id=doc_id, score=1.5, title="Hello Doc")]
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = [
        SearchResult(doc_id=doc_id, score=0.9, chunk_text="hello chunk")
    ]

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            es_client=mock_es,
            qdrant_client=mock_qdrant,
        )
    )
    token = _user_token(client)

    response = client.post(
        "/search",
        json={"query": "hello", "page": 1, "page_size": 10},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["results"]) == 1
    assert data["results"][0]["doc_id"] == doc_id
    assert data["results"][0]["title"] == "Hello Doc"

    # Verify group filtering was passed to search clients
    es_call = mock_es.search.call_args
    assert len(es_call.kwargs["group_ids"]) > 0


def test_search_excludes_unauthorized_documents(
    migrated_engine: Engine,
) -> None:
    _setup_users(migrated_engine)

    # Create a source granted to "admins" only
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
            path="/data/admin.txt",
        )
        assert doc is not None

    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_es.search.return_value = []
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = []

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            es_client=mock_es,
            qdrant_client=mock_qdrant,
        )
    )
    token = _user_token(client)

    response = client.post(
        "/search",
        json={"query": "admin", "page": 1, "page_size": 10},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["results"] == []


def test_search_pagination(
    migrated_engine: Engine,
) -> None:
    _setup_users(migrated_engine)

    source_id, doc_id = _create_source_with_doc(migrated_engine, "users")

    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_es.search.return_value = [
        SearchResult(doc_id=f"doc-{i}", score=float(i), title=f"Doc {i}") for i in range(5)
    ]
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = []

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            es_client=mock_es,
            qdrant_client=mock_qdrant,
        )
    )
    token = _user_token(client)

    response = client.post(
        "/search",
        json={"query": "test", "page": 1, "page_size": 2},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["results"]) == 2


def test_preview_returns_authorized_document(
    migrated_engine: Engine,
) -> None:
    _setup_users(migrated_engine)

    _source_id, doc_id = _create_source_with_doc(migrated_engine, "users", "Preview Doc")

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    response = client.get(f"/preview/{doc_id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    assert data["doc_id"] == doc_id
    assert data["title"] == "Preview Doc"
    assert data["mime_type"] == "text/plain"


def test_preview_forbids_unauthorized_document(
    migrated_engine: Engine,
) -> None:
    _setup_users(migrated_engine)

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
            path="/data/admin.txt",
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

    response = client.get(f"/preview/{doc_id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403


def test_download_returns_file_bytes(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    # Create a real file to download
    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Hello world")

    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        user_group = auth_repo.ensure_group("users")
        source_id = auth_repo.create_ingestion_source("Test Source")
        auth_repo.grant_source_to_group(source_id, user_group)

        doc_repo = DocumentRepository(connection)
        doc = doc_repo.create(
            source_id=source_id,
            external_id="file:/data/test.txt",
            source="folder",
            mime_type="text/plain",
            title="Test Doc",
            path=str(test_file),
        )
        assert doc is not None
        doc_id = str(doc.id)

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(
                auth_provider="local",
                jwt_secret=TEST_JWT_SECRET,
                files_root=files_root,
            ),
        )
    )
    token = _user_token(client)

    response = client.get(f"/download/{doc_id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.content == b"Hello world"
    assert response.headers["content-type"].startswith("text/plain")


def test_download_blocks_path_traversal(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("secret")

    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        user_group = auth_repo.ensure_group("users")
        source_id = auth_repo.create_ingestion_source("Test Source")
        auth_repo.grant_source_to_group(source_id, user_group)

        doc_repo = DocumentRepository(connection)
        # Store a path that tries to escape files_root
        doc = doc_repo.create(
            source_id=source_id,
            external_id="file:/data/traversal.txt",
            source="folder",
            mime_type="text/plain",
            title="Traversal Doc",
            path=str(tmp_path / ".." / "secret.txt"),
        )
        assert doc is not None
        doc_id = str(doc.id)

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(
                auth_provider="local",
                jwt_secret=TEST_JWT_SECRET,
                files_root=files_root,
            ),
        )
    )
    token = _user_token(client)

    response = client.get(f"/download/{doc_id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 400


def test_preview_404_for_missing_document(
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

    response = client.get(f"/preview/{uuid4()}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404


def test_download_404_for_missing_document(
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

    response = client.get(f"/download/{uuid4()}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404


def test_search_with_null_translation_quality(
    migrated_engine: Engine,
) -> None:
    _setup_users(migrated_engine)

    source_id, doc_id = _create_source_with_doc(migrated_engine, "users")

    # Set translation_quality to null explicitly
    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE documents SET translation_quality = NULL WHERE id = :id"),
            {"id": doc_id},
        )

    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_es.search.return_value = [SearchResult(doc_id=doc_id, score=1.0, title="No Translation")]
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = []

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            es_client=mock_es,
            qdrant_client=mock_qdrant,
        )
    )
    token = _user_token(client)

    response = client.post(
        "/search",
        json={"query": "test", "page": 1, "page_size": 10},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["results"][0]["doc_id"] == doc_id


def test_search_encoder_failure_returns_bm25_only(
    migrated_engine: Engine,
) -> None:
    """When encoder fails, search should still return BM25 results."""
    _setup_users(migrated_engine)

    source_id, doc_id = _create_source_with_doc(migrated_engine, "users", "Hello Doc")

    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_es.search.return_value = [SearchResult(doc_id=doc_id, score=1.5, title="Hello Doc")]
    mock_qdrant = MagicMock(spec=QdrantSearchClient)

    from services.search.encoder import TextEncoder

    class BrokenEncoder(TextEncoder):
        def encode(self, text: str) -> list[float]:
            raise RuntimeError("Ollama is down")

    with patch("services.api.main.build_encoder", return_value=BrokenEncoder()):
        client = TestClient(
            create_app(
                migrated_engine,
                Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
                es_client=mock_es,
                qdrant_client=mock_qdrant,
            )
        )
    token = _user_token(client)

    response = client.post(
        "/search",
        json={"query": "hello", "page": 1, "page_size": 10},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["results"]) == 1
    assert data["results"][0]["doc_id"] == doc_id


def test_search_qdrant_failure_returns_bm25_only(
    migrated_engine: Engine,
) -> None:
    """When Qdrant fails, search should still return BM25 results."""
    _setup_users(migrated_engine)

    source_id, doc_id = _create_source_with_doc(migrated_engine, "users", "Hello Doc")

    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_es.search.return_value = [SearchResult(doc_id=doc_id, score=1.5, title="Hello Doc")]
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.side_effect = RuntimeError("Qdrant unavailable")

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            es_client=mock_es,
            qdrant_client=mock_qdrant,
        )
    )
    token = _user_token(client)

    response = client.post(
        "/search",
        json={"query": "hello", "page": 1, "page_size": 10},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["results"]) == 1
    assert data["results"][0]["doc_id"] == doc_id


def test_search_es_failure_still_fails(
    migrated_engine: Engine,
) -> None:
    """When Elasticsearch fails, search should fail because there is no fallback."""
    _setup_users(migrated_engine)

    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_es.search.side_effect = RuntimeError("ES down")
    mock_qdrant = MagicMock(spec=QdrantSearchClient)

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            es_client=mock_es,
            qdrant_client=mock_qdrant,
        )
    )
    token = _user_token(client)

    response = client.post(
        "/search",
        json={"query": "hello", "page": 1, "page_size": 10},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 500


def test_search_logs_no_raw_query_on_vector_degradation(
    migrated_engine: Engine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When vector search fails, logs must not contain the raw query text."""
    _setup_users(migrated_engine)

    mock_es = MagicMock(spec=ElasticsearchSearchClient)
    mock_es.search.return_value = []
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.side_effect = RuntimeError("Qdrant unavailable")

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            es_client=mock_es,
            qdrant_client=mock_qdrant,
        )
    )
    token = _user_token(client)

    with caplog.at_level("WARNING"):
        client.post(
            "/search",
            json={"query": "super-secret-query-12345", "page": 1, "page_size": 10},
            headers={"Authorization": f"Bearer {token}"},
        )

    for record in caplog.records:
        assert "super-secret-query-12345" not in record.message


def test_related_documents_degraded_on_encoder_failure(
    migrated_engine: Engine,
) -> None:
    """When encoder fails, related documents should return empty list safely."""
    _setup_users(migrated_engine)

    from services.search.encoder import TextEncoder

    class BrokenEncoder(TextEncoder):
        def encode(self, text: str) -> list[float]:
            raise RuntimeError("Ollama is down")

    _source_id, doc_id = _create_source_with_doc(migrated_engine, "users", "Related Doc")

    # Create a real file for extraction
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("test content")
        path = f.name

    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE documents SET path = :path WHERE id = :id"),
            {"path": path, "id": doc_id},
        )

    with patch("services.api.main.build_encoder", return_value=BrokenEncoder()):
        client = TestClient(
            create_app(
                migrated_engine,
                Settings(
                    auth_provider="local",
                    jwt_secret=TEST_JWT_SECRET,
                    feature_related_docs=True,
                ),
            )
        )
    token = _user_token(client)

    response = client.get(
        f"/documents/{doc_id}/related",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["doc_id"] == doc_id
    assert data["related"] == []

    Path(path).unlink(missing_ok=True)


def test_expertise_degraded_on_encoder_failure(
    migrated_engine: Engine,
) -> None:
    """When encoder fails, expertise should return empty list safely."""
    _setup_users(migrated_engine)

    from services.search.encoder import TextEncoder

    class BrokenEncoder(TextEncoder):
        def encode(self, text: str) -> list[float]:
            raise RuntimeError("Ollama is down")

    with patch("services.api.main.build_encoder", return_value=BrokenEncoder()):
        client = TestClient(
            create_app(
                migrated_engine,
                Settings(
                    auth_provider="local",
                    jwt_secret=TEST_JWT_SECRET,
                    feature_expertise_map=True,
                ),
            )
        )
    token = _user_token(client)

    response = client.get(
        "/expertise?topic=ai",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == []
