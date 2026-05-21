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


def _user_token(client: TestClient) -> str:
    login = client.post("/auth/login", json={"email": "user@example.com", "password": "secret"})
    assert login.status_code == 200
    return login.json()["access_token"]


def _setup_users(engine: Engine) -> None:
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        auth_repo.create_local_user(
            email="user@example.com",
            password_hash=hash_password("secret"),
            display_name="User",
            is_admin=False,
            group_names=["users"],
        )


def _create_doc(
    engine: Engine,
    group_name: str = "users",
    path: str = "/data/test.txt",
    mime_type: str = "text/plain",
) -> str:
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
            title="Test Doc",
            path=path,
        )
        return str(doc.id)


def _insert_payload(
    engine: Engine,
    document_id: str,
    content_text: str = "",
    translated_text: str = "",
) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.text("""
                INSERT INTO document_payloads
                    (document_id, content_text, translated_text, created_at, updated_at)
                VALUES
                    (:document_id, :content_text, :translated_text,
                     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (document_id) DO UPDATE SET
                    content_text = EXCLUDED.content_text,
                    translated_text = EXCLUDED.translated_text,
                    updated_at = CURRENT_TIMESTAMP
            """),
            {
                "document_id": db_uuid(UUID(document_id)),
                "content_text": content_text,
                "translated_text": translated_text,
            },
        )


def _make_client(migrated_engine: Engine) -> TestClient:
    return TestClient(
        create_app(
            migrated_engine,
            Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET),
        )
    )


def test_returns_content_text_when_no_translation(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)
    test_file = tmp_path / "test.txt"
    test_file.write_text("Full original content here.")
    doc_id = _create_doc(migrated_engine, path=str(test_file))
    _insert_payload(migrated_engine, doc_id, content_text="Full original content here.")

    client = _make_client(migrated_engine)
    token = _user_token(client)
    resp = client.get(f"/documents/{doc_id}/text", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "Full original content here."
    assert data["total_length"] == len("Full original content here.")
    assert data["offset"] == 0
    assert data["truncated"] is False


def test_show_original_returns_content_text_over_translation(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)
    test_file = tmp_path / "test.txt"
    test_file.write_text("Original text.")
    doc_id = _create_doc(migrated_engine, path=str(test_file))
    _insert_payload(
        migrated_engine,
        doc_id,
        content_text="Original text.",
        translated_text="Translated text.",
    )

    client = _make_client(migrated_engine)
    token = _user_token(client)
    resp = client.get(
        f"/documents/{doc_id}/text?show_original=true",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    assert resp.json()["text"] == "Original text."


def test_returns_translation_by_default_when_available(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)
    test_file = tmp_path / "test.txt"
    test_file.write_text("Original text.")
    doc_id = _create_doc(migrated_engine, path=str(test_file))
    _insert_payload(
        migrated_engine,
        doc_id,
        content_text="Original text.",
        translated_text="Translated text.",
    )

    client = _make_client(migrated_engine)
    token = _user_token(client)
    resp = client.get(f"/documents/{doc_id}/text", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    assert resp.json()["text"] == "Translated text."


def test_offset_and_limit_slicing(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)
    test_file = tmp_path / "test.txt"
    test_file.write_text("abcdefghij")
    doc_id = _create_doc(migrated_engine, path=str(test_file))
    _insert_payload(migrated_engine, doc_id, content_text="abcdefghij")

    client = _make_client(migrated_engine)
    token = _user_token(client)

    resp = client.get(
        f"/documents/{doc_id}/text?show_original=true&offset=3&limit=4",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == "defg"
    assert data["total_length"] == 10
    assert data["offset"] == 3
    assert data["limit"] == 4
    assert data["truncated"] is True


def test_offset_beyond_end_returns_empty(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)
    test_file = tmp_path / "test.txt"
    test_file.write_text("short")
    doc_id = _create_doc(migrated_engine, path=str(test_file))
    _insert_payload(migrated_engine, doc_id, content_text="short")

    client = _make_client(migrated_engine)
    token = _user_token(client)

    resp = client.get(
        f"/documents/{doc_id}/text?show_original=true&offset=100",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == ""
    assert data["total_length"] == 5
    assert data["truncated"] is False


def test_empty_text_returns_empty_response_not_error(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)
    test_file = tmp_path / "test.txt"
    test_file.write_text("ignored file")
    doc_id = _create_doc(migrated_engine, path=str(test_file))
    # No payload inserted — no extracted text

    client = _make_client(migrated_engine)
    token = _user_token(client)
    resp = client.get(f"/documents/{doc_id}/text", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["text"] == ""
    assert data["total_length"] == 0
    assert data["truncated"] is False


def test_missing_document_returns_404(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = _make_client(migrated_engine)
    token = _user_token(client)

    resp = client.get(
        "/documents/00000000-0000-0000-0000-000000000001/text",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 404


def test_limit_validation_rejects_above_100000(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello")
    doc_id = _create_doc(migrated_engine, path=str(test_file))

    client = _make_client(migrated_engine)
    token = _user_token(client)
    resp = client.get(
        f"/documents/{doc_id}/text?limit=200000",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 422


def test_translation_version_id_resolves_specific_version(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)
    test_file = tmp_path / "test.txt"
    test_file.write_text("Original.")
    doc_id = _create_doc(migrated_engine, path=str(test_file))

    with migrated_engine.begin() as connection:
        version_repo = TranslationVersionRepository(connection)
        version = version_repo.create_version(
            document_id=UUID(doc_id),
            label="v1",
            quality="fast",
            request_type="manual",
            requested_by_id=None,
            target_language="en",
        )
        version_id = str(version["id"])
        # Mark available and add translated text
        connection.execute(
            sa.text("""
                UPDATE document_translation_versions
                SET status = 'available', translated_text = 'Version-specific translation.'
                WHERE id = :id
            """),
            {"id": db_uuid(UUID(version_id))},
        )

    client = _make_client(migrated_engine)
    token = _user_token(client)
    resp = client.get(
        f"/documents/{doc_id}/text?translation_version_id={version_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    assert resp.json()["text"] == "Version-specific translation."
