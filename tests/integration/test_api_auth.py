from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from shared.config import Settings

TEST_JWT_SECRET = "x" * 32


def test_auth_api_login_me_logout_and_admin_guard(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repository = AuthRepository(connection)
        repository.create_local_user(
            email="admin@example.com",
            password_hash=hash_password("secret"),
            display_name="Admin",
            is_admin=True,
            group_names=["admins"],
        )

    client = TestClient(
        create_app(migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET))
    )

    login = client.post("/auth/login", json={"email": "admin@example.com", "password": "secret"})
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "admin@example.com"

    logout = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 200
    assert logout.json() == {"ok": True}

    admin = client.get("/admin/health", headers={"Authorization": f"Bearer {token}"})
    assert admin.status_code == 200


def test_auth_api_rejects_invalid_credentials_and_missing_token(migrated_engine: Engine) -> None:
    client = TestClient(
        create_app(migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET))
    )

    login = client.post("/auth/login", json={"email": "nobody@example.com", "password": "bad"})
    assert login.status_code == 401

    me = client.get("/auth/me")
    assert me.status_code == 401


def test_admin_route_forbids_non_admin_user(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        repository = AuthRepository(connection)
        repository.create_local_user(
            email="user@example.com",
            password_hash=hash_password("secret"),
            is_admin=False,
            group_names=["users"],
        )

    client = TestClient(
        create_app(migrated_engine, Settings(auth_provider="local", jwt_secret=TEST_JWT_SECRET))
    )
    login = client.post("/auth/login", json={"email": "user@example.com", "password": "secret"})
    token = login.json()["access_token"]

    response = client.get("/admin/health", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
