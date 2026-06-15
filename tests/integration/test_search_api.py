from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
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
from services.search.hybrid import SearchResult
from services.search.meili_types import (
    DocumentSearchQuery,
)
from services.search.models import SearchResults
from services.search.qdrant import QdrantSearchClient
from shared.config import Settings
from shared.db import db_uuid, to_uuid

TEST_JWT_SECRET = "x" * 32


class _FakeMeiliProvider:
    def __init__(self, engine: Engine, estimated_total: int | None = None) -> None:
        self._engine = engine
        # When set, simulate Meilisearch reporting more estimated hits than the
        # candidate window returned (corpus exceeds top_k).  Otherwise ``total``
        # mirrors the number of returned rows (window held every match).
        self._estimated_total = estimated_total

    def search(self, query: DocumentSearchQuery, user: object) -> SearchResults:
        # The real Meilisearch provider enforces document ACLs via a permission
        # filter, and the search route trusts the provider to do so (it does not
        # re-filter BM25 results). Replicate that here: non-admins only see
        # documents whose source is granted to one of their groups.
        is_admin = bool(getattr(user, "is_admin", False))
        group_ids = [db_uuid(to_uuid(g)) for g in getattr(user, "groups", [])]
        params: dict[str, object] = {"q": f"%{query.q}%", "limit": query.limit}
        with self._engine.begin() as conn:
            if is_admin:
                rows = conn.execute(
                    sa.text(
                        "SELECT id, title FROM documents "
                        "WHERE LOWER(title) LIKE LOWER(:q) LIMIT :limit"
                    ),
                    params,
                ).fetchall()
            elif not group_ids:
                rows = []
            else:
                placeholders = ", ".join(f":g{i}" for i in range(len(group_ids)))
                params.update({f"g{i}": gid for i, gid in enumerate(group_ids)})
                rows = conn.execute(
                    sa.text(
                        "SELECT d.id, d.title FROM documents d "
                        "JOIN source_permissions sp ON sp.source_id = d.source_id "
                        f"WHERE LOWER(d.title) LIKE LOWER(:q) AND sp.group_id IN ({placeholders}) "
                        "LIMIT :limit"
                    ),
                    params,
                ).fetchall()
        # Normalise the DB id to a canonical dashed UUID string so it matches the
        # search route's document lookup keys (SQLite stores UUIDs without dashes).
        results = [
            SearchResult(document_id=str(to_uuid(row[0])), score=1.0, title=row[1]) for row in rows
        ]
        total = self._estimated_total if self._estimated_total is not None else len(results)
        return SearchResults(results=results, facets={}, total=total)


def _meili(engine: Engine, estimated_total: int | None = None) -> _FakeMeiliProvider:
    return _FakeMeiliProvider(engine, estimated_total=estimated_total)


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
    Returns (source_id, document_id).
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

    source_id, document_id = _create_source_with_doc(migrated_engine, "users", "Hello Doc")

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = [
        SearchResult(document_id=document_id, score=0.9, chunk_text="hello chunk")
    ]

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(
                auth_provider="local",
                jwt_secret=TEST_JWT_SECRET,
                app_env="dev",
                search_reranker_enabled=False,
            ),
            qdrant_client=mock_qdrant,
            meili_provider=_meili(migrated_engine),
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
    assert data["query"] == "hello"
    assert len(data["results"]) == 1
    result = data["results"][0]
    assert result["document_id"] == document_id
    assert result["title"] == "Hello Doc"
    assert result["snippet"] == "Hello Doc"
    assert result["source"] == "folder"
    assert result["source_label"] == "Folder"
    assert result["mime_type"] == "text/plain"
    assert result["tags"] == []
    assert result["score"] > 0
    assert "updated_at" in result
    assert "indexed_at" in result
    assert result["source_id"] == source_id


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

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = []

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            qdrant_client=mock_qdrant,
            meili_provider=_meili(migrated_engine),
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

    source_id, document_id = _create_source_with_doc(migrated_engine, "users")

    # Create 5 documents so mock results can reference distinct doc IDs
    doc_ids: list[str] = [document_id]
    for i in range(4):
        _, extra_id = _create_source_with_doc(migrated_engine, "users", f"Doc {i}")
        doc_ids.append(extra_id)

    # Vector search returns all 5 documents so pagination can be exercised.
    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = [
        SearchResult(document_id=doc_id, score=0.9 - i * 0.1, chunk_text=f"chunk {i}")
        for i, doc_id in enumerate(doc_ids)
    ]

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            qdrant_client=mock_qdrant,
            meili_provider=_meili(migrated_engine),
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

    _source_id, document_id = _create_source_with_doc(migrated_engine, "users", "Preview Doc")

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    response = client.get(f"/preview/{document_id}", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == document_id
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
        document_id = str(doc.id)

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    response = client.get(f"/preview/{document_id}", headers={"Authorization": f"Bearer {token}"})

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
        document_id = str(doc.id)

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

    response = client.get(f"/download/{document_id}", headers={"Authorization": f"Bearer {token}"})

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
        document_id = str(doc.id)

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

    response = client.get(f"/download/{document_id}", headers={"Authorization": f"Bearer {token}"})

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

    source_id, document_id = _create_source_with_doc(migrated_engine, "users")

    # Set translation_quality to null explicitly
    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE documents SET translation_quality = NULL WHERE id = :id"),
            {"id": document_id},
        )

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = []

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            qdrant_client=mock_qdrant,
            meili_provider=_meili(migrated_engine),
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
    assert data["results"][0]["document_id"] == document_id


def test_search_encoder_failure_returns_bm25_only(
    migrated_engine: Engine,
) -> None:
    """When encoder fails, search should still return BM25 results."""
    _setup_users(migrated_engine)

    source_id, document_id = _create_source_with_doc(migrated_engine, "users", "Hello Doc")

    mock_qdrant = MagicMock(spec=QdrantSearchClient)

    from services.search.encoder import TextEncoder

    class BrokenEncoder(TextEncoder):
        def encode(self, text: str) -> list[float]:
            raise RuntimeError("Ollama is down")

    with patch("services.api.routers.search.build_encoder", return_value=BrokenEncoder()):
        client = TestClient(
            create_app(
                migrated_engine,
                Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
                qdrant_client=mock_qdrant,
                meili_provider=_meili(migrated_engine),
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
    assert data["results"][0]["document_id"] == document_id


def test_search_qdrant_failure_returns_bm25_only(
    migrated_engine: Engine,
) -> None:
    """When Qdrant fails, search should still return BM25 results."""
    _setup_users(migrated_engine)

    source_id, document_id = _create_source_with_doc(migrated_engine, "users", "Hello Doc")

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.side_effect = RuntimeError("Qdrant unavailable")

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            qdrant_client=mock_qdrant,
            meili_provider=_meili(migrated_engine),
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
    assert data["results"][0]["document_id"] == document_id


def test_search_logs_no_raw_query_on_vector_degradation(
    migrated_engine: Engine,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When vector search fails, logs must not contain the raw query text."""
    _setup_users(migrated_engine)

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.side_effect = RuntimeError("Qdrant unavailable")

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            qdrant_client=mock_qdrant,
            meili_provider=_meili(migrated_engine),
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

    _source_id, document_id = _create_source_with_doc(migrated_engine, "users", "Related Doc")

    # Create a real file for extraction
    import tempfile
    from pathlib import Path

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("test content")
        path = f.name

    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE documents SET path = :path WHERE id = :id"),
            {"path": path, "id": document_id},
        )

    with patch("services.api.routers.documents.build_encoder", return_value=BrokenEncoder()):
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
        f"/documents/{document_id}/related",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == document_id
    assert data["related"] == []

    Path(path).unlink(missing_ok=True)


def test_oversized_search_query_returns_422(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET))
    )
    token = _user_token(client)

    resp = client.post(
        "/search",
        json={"query": "x" * 501, "mode": "hybrid"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_expertise_degraded_on_encoder_failure(
    migrated_engine: Engine,
) -> None:
    """When encoder fails, expertise should return empty list safely."""
    _setup_users(migrated_engine)

    from services.search.encoder import TextEncoder

    class BrokenEncoder(TextEncoder):
        def encode(self, text: str) -> list[float]:
            raise RuntimeError("Ollama is down")

    with patch("services.api.routers.documents.build_encoder", return_value=BrokenEncoder()):
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


def test_oversized_expertise_topic_returns_422(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    app = create_app(
        migrated_engine,
        Settings(
            auth_provider="local",
            jwt_secret=TEST_JWT_SECRET,
            feature_expertise_map=True,
        ),
    )
    client = TestClient(app)
    token = _user_token(client)

    resp = client.get(
        f"/expertise?topic={'x' * 501}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_search_admin_passes_allow_all_to_backends(
    migrated_engine: Engine,
) -> None:
    """H1: admin bypass — Qdrant receives allow_all=True."""
    _setup_users(migrated_engine)
    _, document_id = _create_source_with_doc(migrated_engine, "users", "Visible Doc")

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = []

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            qdrant_client=mock_qdrant,
            meili_provider=_meili(migrated_engine),
        )
    )
    token = _admin_token(client)

    resp = client.post(
        "/search",
        json={"query": "visible", "page": 1, "page_size": 10},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    assert mock_qdrant.search.called
    qdrant_kwargs = mock_qdrant.search.call_args.kwargs
    assert qdrant_kwargs.get("allow_all") is True


def test_search_backends_execute_in_parallel(
    migrated_engine: Engine,
) -> None:
    """Verify search fires Meilisearch and Qdrant concurrently via
    ThreadPoolExecutor, not serially."""
    _setup_users(migrated_engine)
    _, document_id = _create_source_with_doc(migrated_engine, "users", "Parallel Doc")

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = [
        SearchResult(document_id=document_id, score=0.9, chunk_text="chunk")
    ]

    real_submit = ThreadPoolExecutor.submit
    submit_calls: list[str] = []

    def _tracking_submit(self, fn, *args, **kwargs):
        fn_name = getattr(fn, "__name__", str(fn))
        submit_calls.append(fn_name)
        return real_submit(self, fn, *args, **kwargs)

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            qdrant_client=mock_qdrant,
            meili_provider=_meili(migrated_engine),
        )
    )
    token = _user_token(client)

    with patch("concurrent.futures.ThreadPoolExecutor.submit", _tracking_submit):
        response = client.post(
            "/search",
            json={"query": "parallel", "page": 1, "page_size": 10},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200

    # Both backends must have been submitted to the thread pool
    assert "_run_meilisearch" in submit_calls, (
        f"_run_meilisearch not submitted to ThreadPoolExecutor: {submit_calls}"
    )
    assert "_run_qdrant" in submit_calls, (
        f"_run_qdrant not submitted to ThreadPoolExecutor: {submit_calls}"
    )


def test_search_hanging_qdrant_does_not_block_shutdown(
    migrated_engine: Engine,
) -> None:
    """When Qdrant hangs, pool.shutdown(wait=False) must not block the request.

    Before the fix, the ThreadPoolExecutor context manager called
    shutdown(wait=True) on exit, which blocked until all threads completed.
    Now shutdown(wait=False, cancel_futures=True) is used so a stuck backend
    cannot hold the request open beyond the future.result(timeout) window.
    """
    _setup_users(migrated_engine)
    _, document_id = _create_source_with_doc(migrated_engine, "users", "Hello Doc")

    import threading

    _hang_event = threading.Event()

    def _hanging_search(**kwargs):
        _hang_event.wait()  # Never set — hangs forever
        return []

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.side_effect = _hanging_search

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            qdrant_client=mock_qdrant,
            meili_provider=_meili(migrated_engine),
        )
    )
    token = _user_token(client)

    # Patch future.result to use a very short timeout so the test completes
    # quickly instead of waiting the default 30s.
    from concurrent.futures import Future as _RealFuture

    _real_result = _RealFuture.result

    def _short_timeout_result(self, timeout=None):
        if timeout is not None:
            timeout = 0.5
        return _real_result(self, timeout=timeout)

    t0 = time.perf_counter()
    with patch.object(_RealFuture, "result", _short_timeout_result):
        response = client.post(
            "/search",
            json={"query": "hello", "page": 1, "page_size": 10},
            headers={"Authorization": f"Bearer {token}"},
        )
    elapsed = time.perf_counter() - t0

    # Must return BM25 results despite hanging Qdrant
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["results"]) >= 1
    assert data["retrieval_degraded"] is True
    # Must NOT block beyond the short timeout + small overhead.  Allow a
    # generous margin for CI jitter (the pool has a 0.5s result timeout).
    assert elapsed < 5.0, f"Request took {elapsed:.2f}s — pool shutdown may be blocking!"


def test_search_drops_orphaned_qdrant_vector(
    migrated_engine: Engine,
) -> None:
    """H3: orphaned Qdrant vector (doc deleted from DB) must not appear in search results."""
    _setup_users(migrated_engine)
    _, real_doc_id = _create_source_with_doc(migrated_engine, "users", "Real Doc")
    orphaned_id = str(uuid4())

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = [
        SearchResult(document_id=real_doc_id, score=0.9, chunk_text="real chunk"),
        SearchResult(document_id=orphaned_id, score=0.95, chunk_text="secret orphaned chunk"),
    ]

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
            qdrant_client=mock_qdrant,
            meili_provider=_meili(migrated_engine),
        )
    )
    token = _user_token(client)

    resp = client.post(
        "/search",
        json={"query": "test", "page": 1, "page_size": 10},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    returned_ids = [r["document_id"] for r in data["results"]]
    assert orphaned_id not in returned_ids
    assert real_doc_id in returned_ids


# ---------------------------------------------------------------------------
# reranker_applied flag
# ---------------------------------------------------------------------------


def test_search_reranker_applied_false_when_disabled(
    migrated_engine: Engine,
) -> None:
    _setup_users(migrated_engine)
    _, document_id = _create_source_with_doc(migrated_engine, "users")

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = [
        SearchResult(document_id=document_id, score=0.9, chunk_text="chunk")
    ]

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(
                auth_provider="local",
                jwt_secret=TEST_JWT_SECRET,
                search_reranker_enabled=False,
            ),
            qdrant_client=mock_qdrant,
            meili_provider=_meili(migrated_engine),
        )
    )
    token = _user_token(client)

    response = client.post(
        "/search",
        json={"query": "test", "page": 1, "page_size": 10},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["reranker_applied"] is False


def test_search_reranker_applied_true_when_rerank_succeeds(
    migrated_engine: Engine,
) -> None:
    _setup_users(migrated_engine)
    _, document_id = _create_source_with_doc(migrated_engine, "users")

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = [
        SearchResult(document_id=document_id, score=0.9, chunk_text="chunk")
    ]

    mock_reranker = MagicMock()
    mock_reranker.rerank.side_effect = lambda _query, results: results

    with patch(
        "services.api.routers.search.build_reranker",
        return_value=mock_reranker,
    ):
        client = TestClient(
            create_app(
                migrated_engine,
                Settings(
                    auth_provider="local",
                    jwt_secret=TEST_JWT_SECRET,
                    search_reranker_enabled=True,
                    search_reranker_url="http://fake-reranker",
                ),
                qdrant_client=mock_qdrant,
                meili_provider=_meili(migrated_engine),
            )
        )
        token = _user_token(client)

        response = client.post(
            "/search",
            json={"query": "test", "page": 1, "page_size": 10},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()["reranker_applied"] is True
    mock_reranker.rerank.assert_called_once()


def test_search_reranker_applied_false_when_reranker_raises(
    migrated_engine: Engine,
) -> None:
    """Reranker exception degrades gracefully: results still returned, reranker_applied=False."""
    _setup_users(migrated_engine)
    _, document_id = _create_source_with_doc(migrated_engine, "users")

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = [
        SearchResult(document_id=document_id, score=0.9, chunk_text="chunk")
    ]

    mock_reranker = MagicMock()
    mock_reranker.rerank.side_effect = RuntimeError("reranker unavailable")

    with patch(
        "services.api.routers.search.build_reranker",
        return_value=mock_reranker,
    ):
        client = TestClient(
            create_app(
                migrated_engine,
                Settings(
                    auth_provider="local",
                    jwt_secret=TEST_JWT_SECRET,
                    search_reranker_enabled=True,
                    search_reranker_url="http://fake-reranker",
                ),
                qdrant_client=mock_qdrant,
                meili_provider=_meili(migrated_engine),
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
    assert data["reranker_applied"] is False
    # Results still returned despite reranker failure
    assert len(data["results"]) == 1


# ---------------------------------------------------------------------------
# Pagination semantics (#762)
# ---------------------------------------------------------------------------


def test_search_pagination_bm25_only_total_is_exact(
    migrated_engine: Engine,
) -> None:
    """BM25-only (no vector results) returns total_is_approximate=False."""
    _setup_users(migrated_engine)

    source_id_1, doc_id_1 = _create_source_with_doc(migrated_engine, "users", "Alpha Doc")
    source_id_2, doc_id_2 = _create_source_with_doc(migrated_engine, "users", "Beta Doc")
    source_id_3, doc_id_3 = _create_source_with_doc(migrated_engine, "users", "Gamma Doc")

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = []

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET, app_env="dev"),
            qdrant_client=mock_qdrant,
            meili_provider=_meili(migrated_engine),
        )
    )
    token = _user_token(client)

    response = client.post(
        "/search",
        json={"query": "doc", "page": 1, "page_size": 2},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 2
    assert data["total"] == 3
    assert data["total_is_approximate"] is False
    assert data["candidate_count"] == 3
    assert data["returned_count"] == 2
    assert data["offset"] == 0
    assert data["limit"] == 2


def test_search_pagination_bm25_only_approximate_when_window_truncated(
    migrated_engine: Engine,
) -> None:
    """BM25-only is approximate when the corpus has more matches than the window.

    When Meilisearch reports ``estimatedTotalHits`` larger than the candidate
    window it returned, the merged total is a capped candidate count, not the
    true corpus total — so ``total_is_approximate`` must be True even with no
    vector results.
    """
    _setup_users(migrated_engine)

    _create_source_with_doc(migrated_engine, "users", "Alpha Doc")
    _create_source_with_doc(migrated_engine, "users", "Beta Doc")
    _create_source_with_doc(migrated_engine, "users", "Gamma Doc")

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = []

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET, app_env="dev"),
            qdrant_client=mock_qdrant,
            # Corpus reports 99 estimated hits while the window returns only 3.
            meili_provider=_meili(migrated_engine, estimated_total=99),
        )
    )
    token = _user_token(client)

    response = client.post(
        "/search",
        json={"query": "doc", "page": 1, "page_size": 2},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    # total is still the paginable (post-filter) count, not the corpus estimate.
    assert data["total"] == 3
    # ...but flagged approximate because the window truncated the corpus.
    assert data["total_is_approximate"] is True


def test_search_pagination_hybrid_total_is_approximate(
    migrated_engine: Engine,
) -> None:
    """Hybrid search returns total_is_approximate=True."""
    _setup_users(migrated_engine)

    _, doc_id_1 = _create_source_with_doc(migrated_engine, "users", "Hybrid One")
    _, doc_id_2 = _create_source_with_doc(migrated_engine, "users", "Hybrid Two")

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = [
        SearchResult(document_id=doc_id_1, score=0.9, chunk_text="hybrid chunk"),
        SearchResult(document_id=doc_id_2, score=0.8, chunk_text="hybrid chunk"),
    ]

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET, app_env="dev"),
            qdrant_client=mock_qdrant,
            meili_provider=_meili(migrated_engine),
        )
    )
    token = _user_token(client)

    response = client.post(
        "/search",
        json={"query": "hybrid", "page": 1, "page_size": 10},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_is_approximate"] is True


def test_search_pagination_page2_works(
    migrated_engine: Engine,
) -> None:
    """Page 2 returns remaining results correctly."""
    _setup_users(migrated_engine)

    doc_ids: list[str] = []
    for i in range(5):
        _, did = _create_source_with_doc(migrated_engine, "users", f"Page Doc {i}")
        doc_ids.append(did)

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = [
        SearchResult(document_id=did, score=0.9, chunk_text="page chunk") for did in doc_ids
    ]

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET, app_env="dev"),
            qdrant_client=mock_qdrant,
            meili_provider=_meili(migrated_engine),
        )
    )
    token = _user_token(client)

    # Page 1: page_size=2 → 2 results
    r1 = client.post(
        "/search",
        json={"query": "page", "page": 1, "page_size": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 200
    p1 = r1.json()
    assert len(p1["results"]) == 2
    assert p1["total"] == 5
    assert p1["offset"] == 0
    assert p1["returned_count"] == 2

    # Page 2: page_size=2 → next 2 results
    r2 = client.post(
        "/search",
        json={"query": "page", "page": 2, "page_size": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 200
    p2 = r2.json()
    assert len(p2["results"]) == 2
    assert p2["total"] == 5
    assert p2["offset"] == 2
    assert p2["returned_count"] == 2

    # Page 3: page_size=2 → last result
    r3 = client.post(
        "/search",
        json={"query": "page", "page": 3, "page_size": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r3.status_code == 200
    p3 = r3.json()
    assert len(p3["results"]) == 1
    assert p3["total"] == 5
    assert p3["offset"] == 4
    assert p3["returned_count"] == 1

    # Page 4: beyond available → empty
    r4 = client.post(
        "/search",
        json={"query": "page", "page": 4, "page_size": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r4.status_code == 200
    p4 = r4.json()
    assert len(p4["results"]) == 0
    assert p4["total"] == 5
    assert p4["returned_count"] == 0


def test_search_pagination_empty_results(
    migrated_engine: Engine,
) -> None:
    """Empty results return sane pagination metadata."""
    _setup_users(migrated_engine)

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.return_value = []

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET, app_env="dev"),
            qdrant_client=mock_qdrant,
            meili_provider=_meili(migrated_engine),
        )
    )
    token = _user_token(client)

    response = client.post(
        "/search",
        json={"query": "zzzzz_nothing", "page": 1, "page_size": 20},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 0
    assert data["total"] == 0
    assert data["total_is_approximate"] is False
    assert data["candidate_count"] == 0
    assert data["returned_count"] == 0
    assert data["offset"] == 0
    assert data["limit"] == 20


def test_search_pagination_degraded_backend_still_returns_metadata(
    migrated_engine: Engine,
) -> None:
    """When the vector backend fails, response still has valid pagination metadata."""
    _setup_users(migrated_engine)

    mock_qdrant = MagicMock(spec=QdrantSearchClient)
    mock_qdrant.search.side_effect = RuntimeError("Qdrant unavailable")

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET, app_env="dev"),
            qdrant_client=mock_qdrant,
            meili_provider=_meili(migrated_engine),
        )
    )
    token = _user_token(client)

    response = client.post(
        "/search",
        json={"query": "anything", "page": 1, "page_size": 20},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["retrieval_degraded"] is True
    assert data["total"] >= 0
    assert data["candidate_count"] >= 0
    assert "offset" in data
    assert "limit" in data
    assert "returned_count" in data
