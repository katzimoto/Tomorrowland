"""Integration tests for admin document timeline and retry endpoints (#673)."""

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


def _seed_timeline_data(engine: Engine):
    """Seed sources, documents, and pipeline_jobs for timeline tests."""
    with engine.begin() as conn:
        source_id = uuid4()
        conn.execute(
            sa.text("INSERT INTO ingestion_sources (id, name, type) VALUES (:id, :name, :type)"),
            {"id": db_uuid(source_id), "name": "test-source", "type": "folder"},
        )

        doc_id = uuid4()
        conn.execute(
            sa.text(
                "INSERT INTO documents (id, source_id, external_id, source, "
                "mime_type, title) "
                "VALUES (:id, :source_id, :ext, :source, :mime, :title)"
            ),
            {
                "id": db_uuid(doc_id),
                "source_id": db_uuid(source_id),
                "ext": "doc-1",
                "source": "folder",
                "mime": "application/pdf",
                "title": "Test Document",
            },
        )

        now = datetime.now(UTC)

        # Stage 1: parsed (completed)
        conn.execute(
            sa.text(
                "INSERT INTO pipeline_jobs "
                "(id, document_id, source_id, job_type, status, stage, "
                "attempts, max_attempts, created_at, updated_at) "
                "VALUES (:id, :document_id, :source_id, :job_type, :status, "
                ":stage, :attempts, :max_attempts, :created_at, :updated_at)"
            ),
            {
                "id": db_uuid(uuid4()),
                "document_id": db_uuid(doc_id),
                "source_id": db_uuid(source_id),
                "job_type": "process_document",
                "status": "succeeded",
                "stage": "parsed",
                "attempts": 1,
                "max_attempts": 5,
                "created_at": now - timedelta(minutes=10),
                "updated_at": now - timedelta(minutes=9),
            },
        )

        # Stage 2: translated (completed)
        conn.execute(
            sa.text(
                "INSERT INTO pipeline_jobs "
                "(id, document_id, source_id, job_type, status, stage, "
                "attempts, max_attempts, created_at, updated_at) "
                "VALUES (:id, :document_id, :source_id, :job_type, :status, "
                ":stage, :attempts, :max_attempts, :created_at, :updated_at)"
            ),
            {
                "id": db_uuid(uuid4()),
                "document_id": db_uuid(doc_id),
                "source_id": db_uuid(source_id),
                "job_type": "translate_document",
                "status": "succeeded",
                "stage": "translated",
                "attempts": 1,
                "max_attempts": 5,
                "created_at": now - timedelta(minutes=8),
                "updated_at": now - timedelta(minutes=5),
            },
        )

        # Stage 3: embedded (dead_letter / failed)
        dead_job_id = uuid4()
        conn.execute(
            sa.text(
                "INSERT INTO pipeline_jobs "
                "(id, document_id, source_id, job_type, status, stage, "
                "attempts, max_attempts, last_error, created_at, updated_at) "
                "VALUES (:id, :document_id, :source_id, :job_type, :status, "
                ":stage, :attempts, :max_attempts, :last_error, "
                ":created_at, :updated_at)"
            ),
            {
                "id": db_uuid(dead_job_id),
                "document_id": db_uuid(doc_id),
                "source_id": db_uuid(source_id),
                "job_type": "vector_index_document",
                "status": "dead_letter",
                "stage": "embedded",
                "attempts": 5,
                "max_attempts": 5,
                "last_error": "UnexpectedResponse:process",
                "created_at": now - timedelta(minutes=4),
                "updated_at": now - timedelta(minutes=2),
            },
        )

        return {
            "source_id": source_id,
            "document_id": doc_id,
            "dead_job_id": dead_job_id,
        }


def _seed_timeline_no_jobs(engine: Engine):
    """Seed a document with no pipeline jobs (for 404 tests)."""
    with engine.begin() as conn:
        source_id = uuid4()
        conn.execute(
            sa.text("INSERT INTO ingestion_sources (id, name, type) VALUES (:id, :name, :type)"),
            {"id": db_uuid(source_id), "name": "empty-source", "type": "folder"},
        )
        doc_id = uuid4()
        conn.execute(
            sa.text(
                "INSERT INTO documents (id, source_id, external_id, source, "
                "mime_type, title) "
                "VALUES (:id, :source_id, :ext, :source, :mime, :title)"
            ),
            {
                "id": db_uuid(doc_id),
                "source_id": db_uuid(source_id),
                "ext": "empty",
                "source": "folder",
                "mime": "text/plain",
                "title": "Empty Doc",
            },
        )
        return {"document_id": doc_id}


# ── Permission tests ──


def test_timeline_non_admin_denied(migrated_engine: Engine):
    _setup_users(migrated_engine)
    seed = _seed_timeline_data(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _user_token(client)

    resp = client.get(
        f"/admin/documents/{seed['document_id']}/timeline",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_retry_non_admin_denied(migrated_engine: Engine):
    _setup_users(migrated_engine)
    seed = _seed_timeline_data(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _user_token(client)

    resp = client.post(
        f"/admin/documents/{seed['document_id']}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── Timeline endpoint tests ──


def test_timeline_returns_stages_ordered(migrated_engine: Engine):
    _setup_users(migrated_engine)
    seed = _seed_timeline_data(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    resp = client.get(
        f"/admin/documents/{seed['document_id']}/timeline",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["document_id"] == str(seed["document_id"])
    assert data["document_title"] == "Test Document"
    assert data["source_name"] == "test-source"
    assert "stages" in data
    assert len(data["stages"]) == 3

    # Stages should be ordered by created_at (ascending)
    stage_names = [s["stage"] for s in data["stages"]]
    assert stage_names == ["parsed", "translated", "embedded"]

    # Check statuses
    assert data["stages"][0]["status"] == "completed"
    assert data["stages"][1]["status"] == "completed"
    assert data["stages"][2]["status"] == "failed"

    # Completed stages should have duration
    assert data["stages"][0]["duration_ms"] is not None
    assert data["stages"][0]["duration_ms"] > 0

    # Failed stage should have error
    assert data["stages"][2]["error"] is not None


def test_timeline_no_jobs_returns_404(migrated_engine: Engine):
    _setup_users(migrated_engine)
    seed = _seed_timeline_no_jobs(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    resp = client.get(
        f"/admin/documents/{seed['document_id']}/timeline",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_timeline_nonexistent_document_returns_404(migrated_engine: Engine):
    _setup_users(migrated_engine)
    _seed_timeline_data(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    resp = client.get(
        f"/admin/documents/{uuid4()}/timeline",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ── Retry endpoint tests ──


def test_retry_creates_audit_entry(migrated_engine: Engine):
    _setup_users(migrated_engine)
    seed = _seed_timeline_data(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    resp = client.post(
        f"/admin/documents/{seed['document_id']}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["requeued"] == 1  # One dead_letter job
    assert data["action"] == "retry"

    # Verify audit entry was created
    with migrated_engine.begin() as conn:
        audit_count = conn.execute(
            sa.text(
                "SELECT COUNT(*) FROM audit_log WHERE resource_id = :doc_id "
                "AND action = 'retry_document'"
            ),
            {"doc_id": str(seed["document_id"])},
        ).scalar()
        assert audit_count == 1

    # Verify job was reset to pending
    with migrated_engine.begin() as conn:
        status = conn.execute(
            sa.text("SELECT status FROM pipeline_jobs WHERE id = :id"),
            {"id": db_uuid(seed["dead_job_id"])},
        ).scalar()
        assert status == "pending"


def test_retry_with_no_dead_letter_returns_zero(migrated_engine: Engine):
    _setup_users(migrated_engine)
    seed = _seed_timeline_data(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    # First retry clears the dead_letter job
    client.post(
        f"/admin/documents/{seed['document_id']}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Second retry should return 0
    resp = client.post(
        f"/admin/documents/{seed['document_id']}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["requeued"] == 0


def test_retry_nonexistent_document_returns_404(migrated_engine: Engine):
    _setup_users(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    resp = client.post(
        f"/admin/documents/{uuid4()}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_reprocess_audit_entry(migrated_engine: Engine):
    _setup_users(migrated_engine)
    seed = _seed_timeline_data(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    resp = client.post(
        f"/admin/documents/{seed['document_id']}/reprocess",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "reprocess"

    # Verify audit entry was created
    with migrated_engine.begin() as conn:
        audit_count = conn.execute(
            sa.text(
                "SELECT COUNT(*) FROM audit_log WHERE resource_id = :doc_id "
                "AND action = 'reprocess'"
            ),
            {"doc_id": str(seed["document_id"])},
        ).scalar()
        assert audit_count == 1


def test_reembed_audit_entry(migrated_engine: Engine):
    _setup_users(migrated_engine)
    seed = _seed_timeline_data(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    resp = client.post(
        f"/admin/documents/{seed['document_id']}/reembed",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "reembed"

    # Verify audit entry was created
    with migrated_engine.begin() as conn:
        audit_count = conn.execute(
            sa.text(
                "SELECT COUNT(*) FROM audit_log WHERE resource_id = :doc_id AND action = 'reembed'"
            ),
            {"doc_id": str(seed["document_id"])},
        ).scalar()
        assert audit_count == 1


def test_duplicate_retry_prevention(migrated_engine: Engine):
    """Verify that reprocessing when an active job exists doesn't create duplicates."""
    _setup_users(migrated_engine)
    seed = _seed_timeline_data(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)

    # First reprocess creates a process_document job
    resp1 = client.post(
        f"/admin/documents/{seed['document_id']}/reprocess",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp1.status_code == 200

    # Second reprocess should find the existing active job
    resp2 = client.post(
        f"/admin/documents/{seed['document_id']}/reprocess",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["requeued"] == 1  # Returns 1 for the existing active job

    # Should only have one pending process_document job
    with migrated_engine.begin() as conn:
        count = conn.execute(
            sa.text(
                "SELECT COUNT(*) FROM pipeline_jobs "
                "WHERE document_id = :doc_id "
                "AND job_type = 'process_document' "
                "AND status IN ('pending', 'running', 'retry')"
            ),
            {"doc_id": db_uuid(seed["document_id"])},
        ).scalar()
        assert count == 1
