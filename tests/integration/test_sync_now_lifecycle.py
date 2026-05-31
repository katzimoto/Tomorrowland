"""Integration tests for manual sync-now lifecycle + source health (#540).

Focus: a sync that fails before any document is processed must still be
recorded in source health and the sync-run history. Because the ingestion
handler runs inside a single DB transaction that rolls back on error, the
failure is recorded in a separate, independently-committed transaction.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.connectors.sync_models import SyncRunCreate
from services.connectors.sync_repository import SyncRunRepository
from shared.config import Settings
from shared.db import db_uuid


def _settings() -> Settings:
    return Settings(
        feature_meilisearch_search=False,
        feature_meilisearch_shadow_index=False,
    )


def _setup_admin(engine: Engine) -> None:
    with engine.begin() as conn:
        AuthRepository(conn).create_local_user(
            email="admin@example.com",
            password_hash=hash_password("secret"),
            display_name="Admin",
            is_admin=True,
            group_names=["admins"],
        )


def _admin_token(client: TestClient) -> str:
    login = client.post("/auth/login", json={"email": "admin@example.com", "password": "secret"})
    assert login.status_code == 200, f"login failed: {login.text}"
    return login.json()["access_token"]


def _insert_folder_source_without_path(engine: Engine) -> UUID:
    """A folder source with no path makes build_connector raise ValueError."""
    sid = uuid4()
    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO ingestion_sources (id, name, type) VALUES (:id, :name, :type)"),
            {"id": db_uuid(sid), "name": "broken-folder", "type": "folder"},
        )
    return sid


def test_sync_now_failure_is_recorded_in_health(migrated_engine: Engine) -> None:
    _setup_admin(migrated_engine)
    source_id = _insert_folder_source_without_path(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(f"/admin/ingestion/{source_id}/sync-now", headers=headers)
    assert resp.status_code == 400, resp.text

    # Health must reflect the failure even though the ingestion transaction
    # rolled back.
    health = client.get(f"/admin/sources/{source_id}/health", headers=headers)
    assert health.status_code == 200, health.text
    body = health.json()
    assert body["last_sync_status"] == "failed"
    assert body["failure_count"] >= 1
    assert body["last_sync_error"]
    assert body["last_sync_id"] is not None

    # And a failed sync run must be visible in the history.
    runs = client.get(f"/admin/sources/{source_id}/sync-runs", headers=headers)
    assert runs.status_code == 200, runs.text
    run_list = runs.json()
    assert len(run_list) == 1
    assert run_list[0]["status"] == "failed"
    assert run_list[0]["completed_at"] is not None


def test_sync_now_blocked_by_active_sync(migrated_engine: Engine) -> None:
    _setup_admin(migrated_engine)
    source_id = _insert_folder_source_without_path(migrated_engine)

    # Seed a running sync run so the concurrent guard trips.
    with migrated_engine.begin() as conn:
        repo = SyncRunRepository(conn)
        run = repo.create(SyncRunCreate(source_id=source_id, connector_type="folder"))
        repo.start(run.id)

    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post(f"/admin/ingestion/{source_id}/sync-now", headers=headers)
    assert resp.status_code == 409, resp.text


def test_sync_runs_endpoint_requires_admin(migrated_engine: Engine) -> None:
    _setup_admin(migrated_engine)
    source_id = _insert_folder_source_without_path(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))

    # No auth header → not authorized.
    resp = client.get(f"/admin/sources/{source_id}/sync-runs")
    assert resp.status_code in (401, 403), resp.text
