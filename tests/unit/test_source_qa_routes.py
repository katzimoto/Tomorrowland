"""Unit tests for GET /admin/sources/{source_id}/qa."""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from shared.config import Settings
from shared.db import db_uuid, to_uuid


def _settings(**overrides):
    return Settings(
        feature_meilisearch_search=False,
        feature_meilisearch_shadow_index=False,
        rabbitmq_enabled=False,
        **overrides,
    )


def _admin_token(client: TestClient, engine: Engine) -> str:
    with engine.begin() as conn:
        AuthRepository(conn).create_local_user(
            email="admin@example.com",
            password_hash=hash_password("secret"),
            display_name="Admin",
            is_admin=True,
            group_names=["admins"],
        )
    login = client.post("/auth/login", json={"email": "admin@example.com", "password": "secret"})
    assert login.status_code == 200
    return login.json()["access_token"]


def _create_source(conn: sa.Connection, source_id: str) -> None:
    conn.execute(
        sa.text("""
            INSERT INTO ingestion_sources (id, name, type, path, enabled, created_at, updated_at)
            VALUES (:id, :name, :type, :path, :enabled, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """),
        {"id": source_id, "name": "Test Source", "type": "folder", "path": "/tmp/test", "enabled": True},
    )


def test_admin_source_qa_returns_shape(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)

    # Create a source
    source_id = db_uuid(uuid4())
    with migrated_engine.begin() as conn:
        _create_source(conn, source_id)

    resp = client.get(
        f"/admin/sources/{source_id}/qa",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert to_uuid(data["source_id"]) == to_uuid(source_id)
    assert "checked_at" in data
    assert data["total_documents"] == 0
    assert data["indexed_documents"] == 0
    assert data["pending_documents"] == 0
    assert data["failed_documents"] == 0
    assert data["empty_chunks"] == 0
    assert data["missing_content"] == 0
    assert data["missing_metadata"] == 0
    assert data["missing_title"] == 0
    assert data["ocr_eligible"] == 0
    assert data["ocr_maybe_needed"] == 0
    assert data["index_lag_count"] == 0
    assert isinstance(data["issues"], list)


def test_admin_source_qa_404_for_unknown_source(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)

    resp = client.get(
        f"/admin/sources/{uuid4().hex}/qa",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Source not found"


def test_admin_source_qa_requires_auth(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))

    resp = client.get(f"/admin/sources/{uuid4().hex}/qa")
    assert resp.status_code == 401


def test_admin_source_qa_rejects_non_admin(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    with migrated_engine.begin() as conn:
        AuthRepository(conn).create_local_user(
            email="user@example.com",
            password_hash=hash_password("secret"),
            display_name="User",
            is_admin=False,
            group_names=["users"],
        )
    login = client.post("/auth/login", json={"email": "user@example.com", "password": "secret"})
    assert login.status_code == 200
    token = login.json()["access_token"]

    resp = client.get(
        f"/admin/sources/{uuid4().hex}/qa",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_admin_source_qa_detects_issues(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)

    source_id = db_uuid(uuid4())
    doc_id = db_uuid(uuid4())

    with migrated_engine.begin() as conn:
        _create_source(conn, source_id)
        conn.execute(
            sa.text("""
                INSERT INTO documents
                    (id, source_id, external_id, source, mime_type, title, status, metadata,
                     created_at, updated_at)
                VALUES
                    (:id, :source_id, :external_id, :source, :mime_type, :title, :status,
                     :metadata, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """),
            {
                "id": doc_id,
                "source_id": source_id,
                "external_id": doc_id,
                "source": "folder",
                "mime_type": "application/pdf",
                "title": None,
                "status": "indexed",
                "metadata": "{}",
            },
        )
        conn.execute(
            sa.text("""
                INSERT INTO document_payloads (document_id, content_text)
                VALUES (:doc_id, :content)
            """),
            {"doc_id": doc_id, "content": ""},
        )

    resp = client.get(
        f"/admin/sources/{source_id}/qa",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_documents"] == 1
    assert data["indexed_documents"] == 1
    assert data["empty_chunks"] == 1
    assert data["missing_metadata"] == 1
    assert data["missing_title"] == 1
    assert data["ocr_eligible"] == 1
    assert data["ocr_maybe_needed"] == 1
    assert len(data["issues"]) >= 4  # multiple issues found
