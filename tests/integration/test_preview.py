from __future__ import annotations

from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.documents.repository import DocumentRepository, TranslationVersionRepository
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

    _source_id, document_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

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
    assert data["snippet"] == "Hello world, this is a test document for preview."
    assert data["view_count"] == 1
    assert data["translation_score"] == 0.0
    assert data["translation_quality"] is None


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
        document_id = str(doc.id)

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    # First preview
    response = client.get(f"/preview/{document_id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["view_count"] == 1
    assert "translation_score" in data

    # Second preview by same user — should not increment
    response = client.get(f"/preview/{document_id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["view_count"] == 1

    # Preview by different user should increment
    admin_token = _admin_token(client)
    response = client.get(
        f"/preview/{document_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
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

    _source_id, document_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

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

    _source_id, document_id = _create_source_with_doc(
        migrated_engine, "users", mime_type="text/html", path=str(test_file)
    )

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

    _source_id, document_id = _create_source_with_doc(
        migrated_engine, "users", mime_type="application/zip", path=str(test_file)
    )

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

    _source_id, document_id = _create_source_with_doc(
        migrated_engine, "users", mime_type="application/gzip", path=str(test_file)
    )

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
    assert "a.txt" in data["snippet"]
    assert "b.txt" in data["snippet"]


def test_preview_with_show_original_returns_original_text(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Original file content only.")

    _source_id, document_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

    # Create a translation version so the non-original path would resolve
    with migrated_engine.begin() as connection:
        version_repo = TranslationVersionRepository(connection)
        created = version_repo.create_version(
            document_id=UUID(document_id),
            label="Manual",
            quality="high",
            request_type="manual",
            target_language="en",
        )
        version_repo.update_version_status(
            UUID(str(created["id"])),
            "available",
            translated_text="Translated version content.",
        )

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    # Without show_original — should return the translated version
    response = client.get(f"/preview/{document_id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["snippet"] == "Translated version content."

    # With show_original=true — should return the original file text
    response = client.get(
        f"/preview/{document_id}?show_original=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["snippet"] == "Original file content only."


def test_preview_falls_back_to_document_payloads_translated_text(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Original file content.")

    _source_id, document_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

    # Insert a document_payloads record with translated_text but
    # NO document_translation_versions record (legacy scenario).
    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text("""
                INSERT INTO document_payloads
                    (document_id, content_text, translated_text, created_at, updated_at)
                VALUES
                    (:document_id, :content_text, :translated_text,
                     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (document_id) DO UPDATE SET
                    translated_text = EXCLUDED.translated_text,
                    updated_at = CURRENT_TIMESTAMP
            """),
            {
                "document_id": db_uuid(UUID(document_id)),
                "content_text": "Original file content.",
                "translated_text": "Payload translated content.",
            },
        )

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    # Without show_original — should fall back to document_payloads.translated_text
    response = client.get(f"/preview/{document_id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["snippet"] == "Payload translated content."

    # With show_original=true — should return original file content
    response = client.get(
        f"/preview/{document_id}?show_original=true",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["snippet"] == "Original file content."


def test_me_activity_returns_view_history(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Content")

    _source_id, document_id = _create_source_with_doc(
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
    response = client.get(f"/preview/{document_id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

    # Get activity
    response = client.get("/me/activity", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["document_id"] == document_id
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
    assert data[0]["document_id"] == doc_id2
    assert data[1]["document_id"] == doc_id1


def test_preview_returns_empty_snippet_for_missing_file(
    migrated_engine: Engine,
) -> None:
    _setup_users(migrated_engine)

    _source_id, document_id = _create_source_with_doc(
        migrated_engine, "users", path="/nonexistent/file.txt"
    )

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


def test_download_returns_nosniff_header(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Hello this is a downloadable file.")

    _source_id, document_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    response = client.get(
        f"/download/{document_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.headers.get("x-content-type-options") == "nosniff"
