from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.documents.repository import DocumentRepository
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
    mime_type: str = "text/plain",
    path: str = "/data/test.txt",
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
        return str(source_id), str(doc.id)


def test_preview_returns_snippet_and_view_count(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Hello world, this is a test document for preview.")

    _source_id, doc_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

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
    assert data["snippet"] == "Hello world, this is a test document for preview."
    assert data["view_count"] == 1


def test_preview_deduplicates_views(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Content")

    # Create source granted to both users and admins groups
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        users_group = auth_repo.ensure_group("users")
        admins_group = auth_repo.ensure_group("admins")
        source_id = auth_repo.create_ingestion_source("Shared Source")
        auth_repo.grant_source_to_group(source_id, users_group)
        auth_repo.grant_source_to_group(source_id, admins_group)

        doc_repo = DocumentRepository(connection)
        doc = doc_repo.create(
            source_id=source_id,
            external_id="file:/data/test.txt",
            source="folder",
            mime_type="text/plain",
            title="Shared Doc",
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

    # First preview
    response = client.get(f"/preview/{doc_id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["view_count"] == 1

    # Second preview by same user — should not increment
    response = client.get(f"/preview/{doc_id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["view_count"] == 1

    # Preview by different user should increment
    admin_token = _admin_token(client)
    response = client.get(f"/preview/{doc_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    assert response.json()["view_count"] == 2


def test_preview_truncates_long_text(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    long_text = "A" * 3000
    test_file.write_text(long_text)

    _source_id, doc_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

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
    assert len(data["snippet"]) == 2000


def test_preview_sanitizes_html(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.html"
    test_file.write_text(
        "<p>Hello</p><script>alert('xss')</script><div onclick='bad()'>Click</div>"
    )

    _source_id, doc_id = _create_source_with_doc(
        migrated_engine, "users", mime_type="text/html", path=str(test_file)
    )

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
    snippet = data["snippet"]
    # HTML extractor strips all tags; sanitizer ensures no dangerous content remains
    assert "<script>" not in snippet
    assert "onclick" not in snippet
    assert "Hello" in snippet
    assert "Click" in snippet


def test_preview_archive_lists_filenames(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.zip"

    import zipfile

    with zipfile.ZipFile(test_file, "w") as zf:
        zf.writestr("file1.txt", "content1")
        zf.writestr("file2.txt", "content2")

    _source_id, doc_id = _create_source_with_doc(
        migrated_engine, "users", mime_type="application/zip", path=str(test_file)
    )

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
    assert "file1.txt" in data["snippet"]
    assert "file2.txt" in data["snippet"]


def test_preview_tar_archive_lists_filenames(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.tar.gz"

    import tarfile

    with tarfile.open(test_file, "w:gz") as tf:
        import io

        for name, content in [("a.txt", "a"), ("b.txt", "b")]:
            data = content.encode()
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

    _source_id, doc_id = _create_source_with_doc(
        migrated_engine, "users", mime_type="application/gzip", path=str(test_file)
    )

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
    assert "a.txt" in data["snippet"]
    assert "b.txt" in data["snippet"]


def test_me_activity_returns_view_history(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Content")

    _source_id, doc_id = _create_source_with_doc(
        migrated_engine, "users", doc_title="History Doc", path=str(test_file)
    )

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    # Preview the document
    response = client.get(f"/preview/{doc_id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

    # Get activity
    response = client.get("/me/activity", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["doc_id"] == doc_id
    assert data[0]["title"] == "History Doc"
    assert data[0]["mime_type"] == "text/plain"
    assert data[0]["viewed_at"] is not None


def test_me_activity_orders_by_most_recent(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    import time

    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    file1 = files_root / "doc1.txt"
    file2 = files_root / "doc2.txt"
    file1.write_text("Content 1")
    file2.write_text("Content 2")

    _source_id, doc_id1 = _create_source_with_doc(
        migrated_engine, "users", doc_title="Doc 1", path=str(file1)
    )
    _source_id, doc_id2 = _create_source_with_doc(
        migrated_engine, "users", doc_title="Doc 2", path=str(file2)
    )

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    # View doc1 then doc2 with 1s gap for SQLite timestamp resolution
    client.get(f"/preview/{doc_id1}", headers={"Authorization": f"Bearer {token}"})
    time.sleep(1)
    client.get(f"/preview/{doc_id2}", headers={"Authorization": f"Bearer {token}"})

    # Get activity — doc2 should be first
    response = client.get("/me/activity", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["doc_id"] == doc_id2
    assert data[1]["doc_id"] == doc_id1


def test_preview_returns_empty_snippet_for_missing_file(
    migrated_engine: Engine,
) -> None:
    _setup_users(migrated_engine)

    _source_id, doc_id = _create_source_with_doc(
        migrated_engine, "users", path="/nonexistent/file.txt"
    )

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
    assert data["snippet"] == ""
    assert data["view_count"] == 1


def test_me_activity_empty_for_new_user(
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

    response = client.get("/me/activity", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == []
