from __future__ import annotations

from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.documents.repository import (
    DocumentRelationshipRepository,
    DocumentRepository,
    TranslationVersionRepository,
)
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


def test_preview_reports_effective_quality_while_high_quality_pending(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    """A queued high-quality translation must not mislabel an available fast one.

    Regression: documents.translation_quality carries the transient
    "pending_high" state while a high-quality job is queued. The preview used
    to surface that raw value, so the frontend (which only knows fast/high/null)
    rendered an already-available fast translation as "Not translated". The
    preview must instead report the *effective* quality of the version shown
    (fast) plus a separate high_quality_pending flag.
    """
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Original file content.")

    _source_id, document_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

    with migrated_engine.begin() as connection:
        version_repo = TranslationVersionRepository(connection)
        created = version_repo.create_version(
            document_id=UUID(document_id),
            label="Ingestion",
            quality="fast",
            request_type="ingestion",
            target_language="en",
        )
        version_repo.update_version_status(
            UUID(str(created["id"])),
            "available",
            translated_text="Fast translated content.",
        )
        # A high-quality translation has since been requested/queued.
        DocumentRepository(connection).update_translation_quality(UUID(document_id), "pending_high")

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
    assert data["snippet"] == "Fast translated content."
    # Effective quality of the shown version, not the raw pending_high column.
    assert data["translation_quality"] == "fast"
    assert data["translation_score"] == 0.5
    assert data["high_quality_pending"] is True


def test_preview_reports_high_quality_when_available(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    """An available high-quality version reports quality=high, not pending."""
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Original file content.")

    _source_id, document_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

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
            translated_text="High quality translated content.",
        )
        DocumentRepository(connection).update_translation_quality(UUID(document_id), "high")

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
    assert data["translation_quality"] == "high"
    assert data["high_quality_pending"] is False


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


# ---------------------------------------------------------------------------
# Relationships in /preview/{doc_id}
# ---------------------------------------------------------------------------


def test_preview_includes_relationships_when_present(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    _setup_users(migrated_engine)
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello")
    _, parent_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))
    _, child_id = _create_source_with_doc(
        migrated_engine, "users", path=str(test_file), doc_title="Child Doc"
    )
    with migrated_engine.begin() as conn:
        rel_repo = DocumentRelationshipRepository(conn)
        rel_repo.create_relationship(
            UUID(parent_id), UUID(child_id), "archive_child", "nested/file.txt"
        )

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)

    resp = client.get(
        f"/preview/{parent_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["relationships"] is not None
    assert len(data["relationships"]) == 1
    assert data["relationships"][0]["direction"] == "child"
    assert data["relationships"][0]["other_document_id"] == child_id
    assert data["relationships"][0]["title"] == "Child Doc"


def test_preview_relationships_null_when_none(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello")
    _, doc_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)
    resp = client.get(
        f"/preview/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["relationships"] is None


def test_preview_relationships_child_sees_parent(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello")
    _, parent_id = _create_source_with_doc(
        migrated_engine, "users", path=str(test_file), doc_title="Email Parent"
    )
    _, child_id = _create_source_with_doc(
        migrated_engine, "users", path=str(test_file), doc_title="Attached PDF"
    )
    with migrated_engine.begin() as conn:
        rel_repo = DocumentRelationshipRepository(conn)
        rel_repo.create_relationship(
            UUID(parent_id), UUID(child_id), "email_attachment", "invoice.pdf"
        )

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )
    token = _user_token(client)
    resp = client.get(
        f"/preview/{child_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    rels = resp.json()["relationships"]
    assert rels is not None
    assert len(rels) == 1
    assert rels[0]["direction"] == "parent"
    assert rels[0]["title"] == "Email Parent"


class _FakeRabbit:
    """Records publishes without touching a real broker.

    Mirrors the subset of ``shared.rabbit.RabbitClient`` the API uses so a test
    can assert that an endpoint actually *publishes* a stage message instead of
    only writing a ``pending`` job row.
    """

    def __init__(self) -> None:
        self.connected = False
        self.topology_declared = False
        self.closed = False
        self.published: list[tuple[str, dict[str, object]]] = []

    def connect(self) -> None:
        self.connected = True

    def declare_topology(self) -> None:
        self.topology_declared = True

    def publish(self, routing_key: str, body: dict[str, object]) -> str:
        self.published.append((routing_key, body))
        return "msg-enrich-1"

    def publish_with_id(self, routing_key: str, body: dict[str, object], message_id: str) -> str:
        self.published.append((routing_key, body))
        return message_id

    def close(self) -> None:
        self.closed = True


def test_request_translation_publishes_enrich_message(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    """Manual translation must publish an enrich message, not just queue a row.

    Regression: the endpoint created the translation version and pipeline job
    but only published when a pre-connected ``app.state.rabbit`` happened to be
    present (it never is on the API), so the high-quality translation sat
    "pending" forever. The request must drive the job onto the broker.
    """
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Original content to translate.")

    _source_id, document_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

    # The test harness forces RABBITMQ_ENABLED=false (conftest); enable it
    # explicitly here and inject a fake broker so the publish path runs without
    # a real connection.
    client = TestClient(
        create_app(
            migrated_engine,
            Settings(
                auth_provider="local",
                jwt_secret=TEST_JWT_SECRET,
                rabbitmq_enabled=True,
            ),
        )
    )
    fake = _FakeRabbit()
    client.app.state.rabbit = fake
    token = _user_token(client)

    response = client.post(
        f"/documents/{document_id}/translate",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "pending"

    # The enrich message must have been published for this document...
    enrich = [body for rk, body in fake.published if rk == "document.enrich.requested"]
    assert len(enrich) == 1, f"expected one enrich publish, got {fake.published}"
    assert enrich[0]["document_id"] == document_id
    assert fake.connected and fake.topology_declared and fake.closed

    # ...and the publish must be recorded back onto the job row.
    with migrated_engine.begin() as connection:
        row = (
            connection.execute(
                sa.text(
                    "SELECT rabbit_message_id FROM pipeline_jobs "
                    "WHERE document_id = :d AND job_type = 'enrich_document'"
                ),
                {"d": db_uuid(UUID(document_id))},
            )
            .mappings()
            .first()
        )
    assert row is not None
    assert row["rabbit_message_id"] == "msg-enrich-1"


def test_request_translation_skips_publish_when_rabbitmq_disabled(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    """With RabbitMQ disabled the version is still queued but nothing publishes."""
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Original content to translate.")

    _source_id, document_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(
                auth_provider="local",
                jwt_secret=TEST_JWT_SECRET,
                rabbitmq_enabled=False,
            ),
        )
    )
    fake = _FakeRabbit()
    client.app.state.rabbit = fake
    token = _user_token(client)

    response = client.post(
        f"/documents/{document_id}/translate",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert fake.published == []


def test_request_translation_idempotent_does_not_republish(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    """A second request while one is pending returns it without re-publishing."""
    _setup_users(migrated_engine)

    files_root = tmp_path / "files"
    files_root.mkdir()
    test_file = files_root / "test.txt"
    test_file.write_text("Original content to translate.")

    _source_id, document_id = _create_source_with_doc(migrated_engine, "users", path=str(test_file))

    client = TestClient(
        create_app(
            migrated_engine,
            Settings(
                auth_provider="local",
                jwt_secret=TEST_JWT_SECRET,
                rabbitmq_enabled=True,
            ),
        )
    )
    fake = _FakeRabbit()
    client.app.state.rabbit = fake
    token = _user_token(client)

    first = client.post(
        f"/documents/{document_id}/translate",
        headers={"Authorization": f"Bearer {token}"},
    )
    second = client.post(
        f"/documents/{document_id}/translate",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["translation_version_id"] == first.json()["translation_version_id"]
    # Only the first request publishes; the second short-circuits on the
    # existing pending version.
    assert len(fake.published) == 1
