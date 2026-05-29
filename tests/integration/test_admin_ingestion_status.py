"""Integration tests for admin ingestion status endpoints."""

from datetime import UTC, datetime, timedelta
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


def _user_token(client: TestClient) -> str:
    login = client.post("/auth/login", json={"email": "user@example.com", "password": "secret"})
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
        AuthRepository(conn).create_local_user(
            email="user@example.com",
            password_hash=hash_password("secret"),
            display_name="User",
            is_admin=False,
            group_names=["users"],
        )


def _seed_ingestion_status_data(engine: Engine):
    """Seed sources, documents, and pipeline_jobs for status tests."""
    with engine.begin() as conn:
        source_id = uuid4()
        conn.execute(
            sa.text("INSERT INTO ingestion_sources (id, name, type) VALUES (:id, :name, :type)"),
            {"id": db_uuid(source_id), "name": "test-source", "type": "folder"},
        )

        doc_pending = uuid4()
        doc_succeeded = uuid4()
        doc_dead = uuid4()

        for doc_id in (doc_pending, doc_succeeded, doc_dead):
            conn.execute(
                sa.text(
                    "INSERT INTO documents (id, source_id, external_id, source, mime_type, title) "
                    "VALUES (:id, :source_id, :ext, :source, :mime, :title)"
                ),
                {
                    "id": db_uuid(doc_id),
                    "source_id": db_uuid(source_id),
                    "ext": str(doc_id)[:8],
                    "source": "folder",
                    "mime": "text/plain",
                    "title": f"Doc {str(doc_id)[:8]}",
                },
            )

        now = datetime.now(UTC)
        # pending job
        pending_job_id = uuid4()
        conn.execute(
            sa.text("""
                INSERT INTO pipeline_jobs
                    (id, document_id, source_id, job_type,
                     status, created_at, updated_at)
                VALUES (:id, :document_id, :source_id, :job_type,
                        :status, :created_at, :updated_at)
            """),
            {
                "id": db_uuid(pending_job_id),
                "document_id": db_uuid(doc_pending),
                "source_id": db_uuid(source_id),
                "job_type": "process_document",
                "status": "pending",
                "created_at": now,
                "updated_at": now,
            },
        )

        # succeeded job
        succeeded_job_id = uuid4()
        conn.execute(
            sa.text("""
                INSERT INTO pipeline_jobs
                    (id, document_id, source_id, job_type, status,
                     stage, attempts, max_attempts, created_at, updated_at)
                VALUES (:id, :document_id, :source_id, :job_type, :status,
                        :stage, :attempts, :max_attempts, :created_at, :updated_at)
            """),
            {
                "id": db_uuid(succeeded_job_id),
                "document_id": db_uuid(doc_succeeded),
                "source_id": db_uuid(source_id),
                "job_type": "vector_index_document",
                "status": "succeeded",
                "stage": "index",
                "attempts": 1,
                "max_attempts": 5,
                "created_at": now - timedelta(hours=1),
                "updated_at": now,
            },
        )

        # dead_letter job
        dead_job_id = uuid4()
        conn.execute(
            sa.text("""
                INSERT INTO pipeline_jobs
                    (id, document_id, source_id, job_type, status,
                     stage, attempts, max_attempts, last_error,
                     created_at, updated_at)
                VALUES (:id, :document_id, :source_id, :job_type, :status,
                        :stage, :attempts, :max_attempts, :last_error,
                        :created_at, :updated_at)
            """),
            {
                "id": db_uuid(dead_job_id),
                "document_id": db_uuid(doc_dead),
                "source_id": db_uuid(source_id),
                "job_type": "process_document",
                "status": "dead_letter",
                "stage": "extract",
                "attempts": 5,
                "max_attempts": 5,
                "last_error": "UnexpectedResponse:process",
                "created_at": now - timedelta(hours=2),
                "updated_at": now,
            },
        )

        return {
            "source_id": source_id,
            "docs": {
                "pending": doc_pending,
                "succeeded": doc_succeeded,
                "dead": doc_dead,
            },
            "jobs": {
                "pending": pending_job_id,
                "succeeded": succeeded_job_id,
                "dead": dead_job_id,
            },
        }


def test_non_admin_denied(migrated_engine: Engine):
    _setup_users(migrated_engine)
    _seed_ingestion_status_data(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _user_token(client)

    resp = client.get(
        "/admin/ingestion/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403

    resp = client.get(
        f"/admin/ingestion/status/{uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_list_returns_seeded_jobs(migrated_engine: Engine):
    _setup_users(migrated_engine)
    seed = _seed_ingestion_status_data(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    resp = client.get(
        "/admin/ingestion/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "jobs" in data
    assert "total" in data
    assert "summary" in data
    assert data["total"] == 3
    ids = [j["id"] for j in data["jobs"]]
    assert str(seed["jobs"]["pending"]) in ids
    assert str(seed["jobs"]["succeeded"]) in ids
    assert str(seed["jobs"]["dead"]) in ids


def test_list_status_filter(migrated_engine: Engine):
    _setup_users(migrated_engine)
    seed = _seed_ingestion_status_data(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    resp = client.get(
        "/admin/ingestion/status?status=pending",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["jobs"][0]["id"] == str(seed["jobs"]["pending"])


def test_list_source_id_filter(migrated_engine: Engine):
    _setup_users(migrated_engine)
    seed = _seed_ingestion_status_data(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    # Filter by matching source_id — should return all 3 jobs
    resp = client.get(
        f"/admin/ingestion/status?source_id={seed['source_id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3

    # Filter by a non-existent source_id — should return 0
    resp = client.get(
        f"/admin/ingestion/status?source_id={uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0


def test_list_since_filter(migrated_engine: Engine):
    _setup_users(migrated_engine)
    _seed_ingestion_status_data(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    # Far future — everything is older
    since = "2099-01-01T00:00:00Z"
    resp = client.get(
        f"/admin/ingestion/status?since={since}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0


def test_list_summary_counts(migrated_engine: Engine):
    _setup_users(migrated_engine)
    _seed_ingestion_status_data(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    resp = client.get(
        "/admin/ingestion/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    summary = data["summary"]
    assert summary.get("pending") == 1
    assert summary.get("succeeded") == 1
    assert summary.get("dead_letter") == 1


def test_document_trace_order(migrated_engine: Engine):
    _setup_users(migrated_engine)
    seed = _seed_ingestion_status_data(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    doc_id = seed["docs"]["pending"]
    resp = client.get(
        f"/admin/ingestion/status/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["document_id"] == str(doc_id)
    assert data["document_title"] is not None
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["id"] == str(seed["jobs"]["pending"])


def test_document_trace_no_jobs_returns_404(migrated_engine: Engine):
    _setup_users(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    # A random document ID with no pipeline jobs
    resp = client.get(
        f"/admin/ingestion/status/{uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
