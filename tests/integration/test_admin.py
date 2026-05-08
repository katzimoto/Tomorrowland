from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from shared.config import Settings

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


# Users


def test_admin_list_users(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET))
    )
    token = _admin_token(client)

    response = client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    emails = {u["email"] for u in data}
    assert emails == {"admin@example.com", "user@example.com"}


def test_admin_create_user(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET))
    )
    token = _admin_token(client)

    response = client.post(
        "/admin/users",
        json={"email": "new@example.com", "password": "newpass", "display_name": "New User"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "new@example.com"
    assert data["display_name"] == "New User"


def test_admin_delete_user(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET))
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
    assert len(users.json()) == 1


# Groups


def test_admin_list_groups(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET))
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
        create_app(migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET))
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
        create_app(migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET))
    )
    token = _admin_token(client)

    # Create a source
    with migrated_engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO ingestion_sources (id, name, type, source_language)
                VALUES (:id, 'Test', 'folder', 'en')
                """
            ),
            {"id": uuid4().hex},
        )

    response = client.get("/admin/sources", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Test"


def test_admin_create_source(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET))
    )
    token = _admin_token(client)

    response = client.post(
        "/admin/sources",
        json={"name": "New Source", "type": "folder", "path": "/data", "source_language": "en"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "New Source"


# Permissions


def test_admin_grant_and_revoke_permission(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET))
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
        create_app(migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET))
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
        create_app(migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET))
    )
    token = _admin_token(client)

    response = client.put(
        "/admin/config/search.vector_weight",
        json={"value": 0.8},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["value"] == 0.8


# Non-admin forbidden


def test_non_admin_cannot_access_admin_users(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET))
    )
    token = _user_token(client)

    response = client.get("/admin/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_non_admin_cannot_access_admin_config(migrated_engine: Engine) -> None:
    _setup_users(migrated_engine)
    client = TestClient(
        create_app(migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET))
    )
    token = _user_token(client)

    response = client.get("/admin/config", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
