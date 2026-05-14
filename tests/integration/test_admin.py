from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from shared.config import Settings

TEST_JWT_SECRET = "x" * 32


def _admin_token(client: TestClient) -> str:
    login = client.post(
        "/auth/login", json={"email": "admin@example.com", "password": "secret"}
    )
    assert login.status_code == 200
    return login.json()["access_token"]


def _user_token(client: TestClient) -> str:
    login = client.post(
        "/auth/login", json={"email": "user@example.com", "password": "secret"}
    )
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


# Users


def test_admin_list_users(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    response = client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    emails = {u["email"] for u in data}
    assert emails == {"admin@local.com", "admin@example.com", "user@example.com"}


def test_admin_create_user(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    response = client.post(
        "/admin/users",
        json={
            "email": "new@example.com",
            "password": "newpass",
            "display_name": "New User",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "new@example.com"
    assert data["display_name"] == "New User"


def test_admin_delete_user(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    # Get user ID
    users = client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})
    user_id = [u["id"] for u in users.json() if u["email"] == "user@example.com"][0]

    response = client.delete(
        f"/admin/users/{user_id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 204

    # Verify user is gone
    users = client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert len(users.json()) == 2


def test_admin_cannot_delete_self(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    # Get admin's own ID
    users = client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})
    admin_id = [u["id"] for u in users.json() if u["email"] == "admin@example.com"][0]

    response = client.delete(
        f"/admin/users/{admin_id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 400
    assert "yourself" in response.json()["detail"].lower()


def test_admin_delete_nonexistent_user_returns_404(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    response = client.delete(
        f"/admin/users/{uuid4()}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


# Groups


def test_admin_list_groups(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    response = client.get("/admin/groups", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    names = {g["name"] for g in data}
    assert "admins" in names
    assert "users" in names


def test_admin_create_group(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    response = client.post(
        "/admin/groups",
        json={"name": "analysts"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "analysts"


# Sources


def test_admin_list_sources(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    # Create a source
    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text("""
                INSERT INTO ingestion_sources (id, name, type, source_language)
                VALUES (:id, 'Test', 'folder', 'en')
                """),
            {"id": uuid4().hex},
        )

    response = client.get(
        "/admin/sources", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Test"


def test_admin_create_source(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    response = client.post(
        "/admin/sources",
        json={
            "name": "New Source",
            "type": "folder",
            "path": "/data",
            "source_language": "en",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "New Source"


# Permissions


def test_admin_create_source_always_grants_admins(migrated_engine: Engine) -> None:
    """Source created without explicit groups still receives the admins grant."""
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    response = client.post(
        "/admin/sources",
        json={"name": "No Groups Source", "type": "folder"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    source_id = response.json()["id"]

    with migrated_engine.connect() as connection:
        group_names = (
            connection.execute(
                sa.text("""
                SELECT g.name FROM source_permissions sp
                JOIN groups g ON g.id = sp.group_id
                WHERE sp.source_id = :source_id
            """),
                {"source_id": UUID(source_id).hex},
            )
            .scalars()
            .all()
        )
    assert "admins" in group_names


def test_admin_create_source_admins_not_duplicated(migrated_engine: Engine) -> None:
    """Granting admins a second time after creation does not create a duplicate row."""
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    response = client.post(
        "/admin/sources",
        json={"name": "Dup Test Source", "type": "folder"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    source_id = response.json()["id"]

    with migrated_engine.connect() as connection:
        admins_group_id = connection.execute(
            sa.text("SELECT id FROM groups WHERE name = 'admins'"),
        ).scalar_one()

    # Grant admins again via the permissions endpoint — must be idempotent
    grant_response = client.post(
        f"/admin/sources/{source_id}/permissions",
        json={"group_id": str(admins_group_id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert grant_response.status_code in (200, 201, 204)

    with migrated_engine.connect() as connection:
        count = connection.execute(
            sa.text("""
                SELECT COUNT(*) FROM source_permissions sp
                JOIN groups g ON g.id = sp.group_id
                WHERE sp.source_id = :source_id AND g.name = 'admins'
            """),
            {"source_id": UUID(source_id).hex},
        ).scalar_one()
    assert count == 1


def test_admin_grant_and_revoke_permission(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    # Create source and group
    with migrated_engine.begin() as connection:
        auth_repo = AuthRepository(connection)
        group_id = auth_repo.ensure_group("analysts")
        source_id = auth_repo.create_ingestion_source("Test Source")

    # Grant
    response = client.post(
        f"/admin/sources/{source_id}/permissions",
        json={"group_id": str(group_id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201

    # Revoke
    response = client.delete(
        f"/admin/sources/{source_id}/permissions/{group_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 204


# System Config


def test_admin_read_config(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    response = client.get("/admin/config", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_admin_update_config(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    response = client.put(
        "/admin/config/search.vector_weight",
        json={"value": 0.8},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["value"] == 0.8


def test_admin_update_nonexistent_config_returns_404(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    response = client.put(
        "/admin/config/nonexistent.key",
        json={"value": "test"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_admin_reset_config(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    # First change a value
    client.put(
        "/admin/config/search.vector_weight",
        json={"value": 0.99},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Reset
    response = client.post(
        "/admin/config/reset",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["reset"] is True
    assert "search.vector_weight" in data["keys"]

    # Verify value was restored
    config = client.get("/admin/config", headers={"Authorization": f"Bearer {token}"})
    vector_weight = [c for c in config.json() if c["key"] == "search.vector_weight"][0]
    assert vector_weight["value"] == 0.7


# DLQ


def test_admin_list_dlq_empty(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    response = client.get("/admin/dlq", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == []


def test_admin_dlq_retry_and_list(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    # Insert a DLQ item manually
    doc_id = uuid4()
    dlq_id = uuid4()
    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text("""
                INSERT INTO documents (id, source_id, external_id, source, mime_type)
                VALUES (:id, :source_id, 'file:/data/test.txt', 'folder', 'text/plain')
                """),
            {"id": doc_id.hex, "source_id": uuid4().hex},
        )
        connection.execute(
            sa.text("""
                INSERT INTO dlq (id, doc_id, error_message, status)
                VALUES (:id, :doc_id, 'Test error', 'pending')
                """),
            {"id": dlq_id.hex, "doc_id": doc_id.hex},
        )

    # List DLQ
    response = client.get("/admin/dlq", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["status"] == "pending"
    assert data[0]["error_message"] == "Test error"

    # Retry
    response = client.post(
        f"/admin/dlq/{dlq_id}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "retried"

    # Verify status changed
    response = client.get("/admin/dlq", headers={"Authorization": f"Bearer {token}"})
    assert response.json()[0]["status"] == "retried"
    assert response.json()[0]["retry_count"] == 1


def test_admin_retry_nonexistent_dlq_returns_404(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    response = client.post(
        f"/admin/dlq/{uuid4()}/retry",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


# Activity / Audit Log


def test_admin_activity_log_captures_mutations(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    # Perform a mutation
    client.post(
        "/admin/groups",
        json={"name": "audited-group"},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Check activity log
    response = client.get(
        "/admin/activity", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["action"] == "create"
    assert data[0]["resource_type"] == "group"


def test_non_admin_cannot_access_admin_activity(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _user_token(client)

    response = client.get(
        "/admin/activity", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


# Non-admin forbidden


def test_non_admin_cannot_access_admin_users(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _user_token(client)

    response = client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_non_admin_cannot_access_admin_config(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _user_token(client)

    response = client.get("/admin/config", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


# Connector types


def test_admin_connector_types_returns_folder_and_nifi(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    response = client.get(
        "/admin/connector-types", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()
    types = {item["type"] for item in data}
    assert "folder" in types
    assert "nifi" in types
    # Each type has a non-empty fields list
    for item in data:
        assert isinstance(item["fields"], list)
        assert len(item["fields"]) > 0
        assert all(
            {"key", "label", "sensitive"} <= set(f.keys()) for f in item["fields"]
        )


def test_admin_connector_types_requires_admin(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _user_token(client)

    response = client.get(
        "/admin/connector-types", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


# Source config persistence


def test_admin_create_source_persists_config(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    response = client.post(
        "/admin/sources",
        json={
            "name": "NiFi Prod",
            "type": "nifi",
            "source_language": "en",
            "config": {
                "base_url": "http://nifi:8080",
                "flow_id": "abc",
                "api_token": "secret",
            },
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "nifi"
    assert "config" not in data

    with migrated_engine.connect() as connection:
        row = connection.execute(
            sa.text("SELECT config FROM ingestion_sources WHERE id = :id"),
            {"id": data["id"].replace("-", "")},
        ).scalar_one()
    stored_config = json.loads(row) if isinstance(row, str) else row
    assert stored_config["api_token"] == "secret"
    assert stored_config["base_url"] == "http://nifi:8080"


def test_admin_test_source_connection_validates_without_leaking_config(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)
    missing_folder = tmp_path / "missing"
    response = client.post(
        "/admin/sources",
        json={
            "name": "Folder",
            "type": "folder",
            "path": str(missing_folder),
            "source_language": "en",
            "config": {"path": str(missing_folder), "api_token": "secret-token"},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    source_id = response.json()["id"]
    assert "config" not in response.json()

    test_response = client.post(
        f"/admin/sources/{source_id}/test-connection",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert test_response.status_code == 200
    result = test_response.json()
    assert result["status"] == "unreachable"
    assert "does not exist" in result["error"]
    assert "secret-token" not in result["error"]


def test_admin_test_source_connection_succeeds_for_valid_source(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)
    valid_folder = tmp_path / "valid"
    valid_folder.mkdir()
    response = client.post(
        "/admin/sources",
        json={
            "name": "ValidFolder",
            "type": "folder",
            "path": str(valid_folder),
            "source_language": "en",
            "config": {"path": str(valid_folder)},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    source_id = response.json()["id"]

    test_response = client.post(
        f"/admin/sources/{source_id}/test-connection",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert test_response.status_code == 200
    result = test_response.json()
    assert result["status"] == "ok"
    assert result["source_id"] == source_id
    assert "checked_at" in result


def test_admin_list_sources_returns_last_sync_state(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    source_id = uuid4()
    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text("""
                INSERT INTO ingestion_sources (
                    id, name, type, source_language, last_sync_status,
                    last_sync_indexed, last_sync_skipped, last_sync_failed, last_sync_error
                )
                VALUES (
                    :id, 'Synced', 'folder', 'en', 'failed', 2, 1, 1,
                    'Source path does not exist'
                )
                """),
            {"id": source_id.hex},
        )

    response = client.get(
        "/admin/sources", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()[0]
    assert data["last_sync_status"] == "failed"
    assert data["last_sync_indexed"] == 2
    assert data["last_sync_skipped"] == 1
    assert data["last_sync_failed"] == 1
    assert data["last_sync_error"] == "Source path does not exist"
    assert "config" not in data


def test_admin_list_sources_omits_config(migrated_engine: Engine) -> None:
    """Config is not returned in the list response (may contain credentials)."""
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(
            migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET)
        )
    )
    token = _admin_token(client)

    client.post(
        "/admin/sources",
        json={"name": "Secure NiFi", "type": "nifi", "config": {"api_token": "secret"}},
        headers={"Authorization": f"Bearer {token}"},
    )

    response = client.get(
        "/admin/sources", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    for src in response.json():
        assert "config" not in src
