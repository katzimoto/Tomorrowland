"""Integration tests for subscriptions, notifications, and alert matching."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.documents.repository import DocumentRepository
from shared.config import Settings

TEST_JWT_SECRET = "x" * 32


def _settings() -> Settings:
    return Settings(
        app_env="test",
        auth_provider="local",
        jwt_secret=TEST_JWT_SECRET,
    )


def _token(client: TestClient, email: str) -> str:
    login = client.post("/auth/login", json={"email": email, "password": "secret"})
    assert login.status_code == 200
    return str(login.json()["access_token"])


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
        auth_repo.create_local_user(
            email="outsider@example.com",
            password_hash=hash_password("secret"),
            display_name="Outsider",
            is_admin=False,
            group_names=["outsiders"],
        )


def _create_doc(engine: Engine, group_name: str, path: str) -> UUID:
    with engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group(group_name)
        source_id = auth_repo.create_ingestion_source("Alert Source")
        auth_repo.grant_source_to_group(source_id, group_id)

        doc_repo = DocumentRepository(connection)
        doc = doc_repo.create(
            source_id=source_id,
            external_id=f"file:{path}",
            source="folder",
            mime_type="text/plain",
            title="Alert Doc",
            path=path,
        )
        assert doc is not None
        return doc.id


def test_subscription_crud(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _token(client, "user@example.com")

    created = client.post(
        "/subscriptions",
        json={"name": "Procurement", "query": "procurement fraud", "similarity_threshold": 0.8},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 201
    subscription_id = created.json()["id"]
    assert created.json()["name"] == "Procurement"

    listed = client.get("/subscriptions", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == subscription_id

    updated = client.put(
        f"/subscriptions/{subscription_id}",
        json={"enabled": False, "name": "Muted procurement"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert updated.json()["name"] == "Muted procurement"

    deleted = client.delete(
        f"/subscriptions/{subscription_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert deleted.status_code == 204


def test_subscription_feature_flag_disabled(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(migrated_engine, _settings().model_copy(update={"feature_subscriptions": False}))
    )
    token = _token(client, "user@example.com")

    response = client.get("/subscriptions", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 404


def test_alert_trigger_creates_access_filtered_notification(
    migrated_engine: Engine,
    tmp_path: Path,
) -> None:
    _setup_users(migrated_engine)
    doc_path = tmp_path / "procurement.txt"
    doc_path.write_text("procurement fraud")
    doc_id = _create_doc(migrated_engine, "users", str(doc_path))

    client = TestClient(create_app(migrated_engine, _settings()))
    user_token = _token(client, "user@example.com")
    outsider_token = _token(client, "outsider@example.com")
    admin_token = _token(client, "admin@example.com")

    user_sub = client.post(
        "/subscriptions",
        json={"name": "Procurement", "query": "procurement fraud", "similarity_threshold": 0.9},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert user_sub.status_code == 201
    outsider_sub = client.post(
        "/subscriptions",
        json={"name": "No Access", "query": "procurement fraud", "similarity_threshold": 0.9},
        headers={"Authorization": f"Bearer {outsider_token}"},
    )
    assert outsider_sub.status_code == 201

    triggered = client.post(
        f"/admin/alerts/{doc_id}/trigger",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert triggered.status_code == 200
    assert triggered.json()["notifications_created"] == 1

    notifications = client.get("/notifications", headers={"Authorization": f"Bearer {user_token}"})
    assert notifications.status_code == 200
    assert len(notifications.json()) == 1
    notification = notifications.json()[0]
    assert notification["doc_id"] == str(doc_id)
    assert notification["subscription_name"] == "Procurement"

    outsider_notifications = client.get(
        "/notifications", headers={"Authorization": f"Bearer {outsider_token}"}
    )
    assert outsider_notifications.status_code == 200
    assert outsider_notifications.json() == []


def test_mark_notification_read(migrated_engine: Engine, tmp_path: Path) -> None:
    _setup_users(migrated_engine)
    doc_path = tmp_path / "topic.txt"
    doc_path.write_text("security update")
    doc_id = _create_doc(migrated_engine, "users", str(doc_path))

    client = TestClient(create_app(migrated_engine, _settings()))
    user_token = _token(client, "user@example.com")
    admin_token = _token(client, "admin@example.com")
    client.post(
        "/subscriptions",
        json={"name": "Security", "query": "security update", "similarity_threshold": 0.9},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    client.post(
        f"/admin/alerts/{doc_id}/trigger", headers={"Authorization": f"Bearer {admin_token}"}
    )

    notification_id = client.get(
        "/notifications", headers={"Authorization": f"Bearer {user_token}"}
    ).json()[0]["id"]
    response = client.put(
        f"/notifications/{notification_id}/read",
        headers={"Authorization": f"Bearer {user_token}"},
    )

    assert response.status_code == 200
    assert response.json()["read"] is True
    assert (
        client.get("/notifications", headers={"Authorization": f"Bearer {user_token}"}).json() == []
    )


def test_migration_creates_alert_tables(migrated_engine: Engine) -> None:
    inspector = sa.inspect(migrated_engine)

    assert {"alert_subscriptions", "alert_notifications"} <= set(inspector.get_table_names())
    notification_indexes = {index["name"] for index in inspector.get_indexes("alert_notifications")}
    assert "ix_alert_notifications_user_read_created" in notification_indexes
    assert "uq_alert_notifications_subscription_doc" in notification_indexes
