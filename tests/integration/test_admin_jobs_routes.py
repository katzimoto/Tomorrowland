"""Integration tests for GET /admin/jobs and GET /admin/jobs/{job_id}."""

from uuid import uuid4

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from shared.config import Settings
from shared.db import db_uuid


def _settings(**overrides):
    return Settings(
        feature_meilisearch_search=False,
        feature_meilisearch_shadow_index=False,
        **overrides,
    )


def _admin_token(client: TestClient) -> str:
    login = client.post("/auth/login", json={"email": "admin@example.com", "password": "secret"})
    assert login.status_code == 200, f"login failed: {login.text}"
    return login.json()["access_token"]


def _setup_users(engine: Engine) -> None:
    with engine.begin() as conn:
        AuthRepository(conn).create_local_user(
            email="admin@example.com",
            password_hash=hash_password("secret"),
            display_name="Admin",
            is_admin=True,
            group_names=["admins"],
        )


def _seed_job(engine: Engine):
    with engine.begin() as conn:
        source_id = uuid4()
        document_id = uuid4()
        conn.execute(
            sa.text(
                """
            INSERT INTO ingestion_sources (id, name, type, path, source_language, enabled)
            VALUES (:id, 'test', 'folder', '/tmp', 'en', true)
            """
            ),
            {"id": db_uuid(source_id)},
        )
        conn.execute(
            sa.text(
                """
            INSERT INTO documents (id, source_id, external_id, source, mime_type, status)
            VALUES (:id, :source_id, :ext, 'folder', 'text/plain', 'pending')
            """
            ),
            {
                "id": db_uuid(document_id),
                "source_id": db_uuid(source_id),
                "ext": str(document_id)[:8],
            },
        )
        job_id = uuid4()
        conn.execute(
            sa.text(
                """
            INSERT INTO pipeline_jobs
              (id, document_id, source_id, job_type, status, priority,
               max_attempts, run_after, created_at, updated_at, stage)
            VALUES
              (:id, :document_id, :source_id, 'process_document', 'pending', 0,
               5, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'queued')
            """
            ),
            {
                "id": db_uuid(job_id),
                "document_id": db_uuid(document_id),
                "source_id": db_uuid(source_id),
            },
        )
        return job_id


def test_admin_list_jobs_returns_jobs(migrated_engine: Engine):
    _setup_users(migrated_engine)
    job_id = _seed_job(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    resp = client.get(
        "/admin/jobs?status=pending",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "jobs" in data and "total" in data
    ids = [j["id"] for j in data["jobs"]]
    assert str(job_id) in ids


def test_admin_get_job_detail(migrated_engine: Engine):
    _setup_users(migrated_engine)
    job_id = _seed_job(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    resp = client.get(
        f"/admin/jobs/{job_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    j = resp.json()
    assert j["id"] == str(job_id)
    assert j["status"] == "pending"


def test_admin_get_job_404(migrated_engine: Engine):
    _setup_users(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    resp = client.get(
        f"/admin/jobs/{uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
