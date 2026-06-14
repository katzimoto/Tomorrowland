"""Integration tests for Permission Simulator admin API endpoints (#717)."""

from __future__ import annotations

from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from shared.config import Settings
from shared.db import to_uuid

TEST_JWT_SECRET = "x" * 32


def _settings() -> Settings:
    return Settings(
        auth_provider="local",
        jwt_secret=TEST_JWT_SECRET,
        feature_meilisearch_search=False,
    )


def _ensure_users(engine: Engine) -> tuple[str, str]:
    """Create admin + regular user if they don't exist; return (admin_id, user_id).
    Idempotent — safe to call multiple times."""
    with engine.begin() as connection:
        repo = AuthRepository(connection)
        existing_admin = repo.get_user_by_email("admin@example.com")
        if existing_admin is None:
            admin = repo.create_local_user(
                email="admin@example.com",
                password_hash=hash_password("secret"),
                is_admin=True,
                group_names=["admins"],
            )
        else:
            admin = existing_admin
        existing_user = repo.get_user_by_email("user@example.com")
        if existing_user is None:
            user = repo.create_local_user(
                email="user@example.com",
                password_hash=hash_password("secret"),
                is_admin=False,
                group_names=["users"],
            )
        else:
            user = existing_user
        return str(admin.id), str(user.id)


def _admin_token(client: TestClient) -> str:
    login = client.post("/auth/login", json={"email": "admin@example.com", "password": "secret"})
    assert login.status_code == 200, login.json()
    return login.json()["access_token"]


def _user_token(client: TestClient) -> str:
    login = client.post("/auth/login", json={"email": "user@example.com", "password": "secret"})
    assert login.status_code == 200
    return login.json()["access_token"]


def _ensure_source_with_group(
    engine: Engine,
    group_name: str = "analysts",
) -> tuple[str, str]:
    """Create a source granted to a group (idempotent)."""
    with engine.begin() as connection:
        repo = AuthRepository(connection)
        group_id = repo.ensure_group(group_name)
        existing = connection.execute(
            sa.text("SELECT id FROM ingestion_sources WHERE name = :name"),
            {"name": "Test Source"},
        ).scalar_one_or_none()
        if existing is not None:
            source_id = to_uuid(existing)
        else:
            source_id = repo.create_ingestion_source("Test Source")
        repo.grant_source_to_group(source_id, group_id)
        return str(source_id), str(group_id)


def _make_client_with_admin(engine: Engine) -> tuple[TestClient, str]:
    """Return a TestClient and admin token, with users seeded."""
    _ensure_users(engine)
    client = TestClient(create_app(engine, _settings()))
    return client, _admin_token(client)


def _create_user_in_group(engine: Engine, email: str, group_name: str) -> str:
    """Create a user in a specific group (idempotent). Returns user_id string."""
    with engine.begin() as connection:
        repo = AuthRepository(connection)
        existing = repo.get_user_by_email(email)
        if existing is not None:
            return str(existing.id)
        user = repo.create_local_user(
            email=email,
            password_hash=hash_password("secret"),
            group_names=[group_name],
        )
        return str(user.id)


def _create_doc_for_source(engine: Engine, source_id: str) -> str:
    """Create a document tied to a source. Returns document_id string."""
    with engine.begin() as connection:
        repo = AuthRepository(connection)
        doc_id = repo.create_document(UUID(source_id))
        return str(doc_id)


# ── Admin-only guard ─────────────────────────────────────────────────────


def test_non_admin_cannot_access_simulator(migrated_engine: Engine) -> None:
    _ensure_users(migrated_engine)
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _user_token(client)

    endpoints = [
        "/admin/permission-simulator/check-source",
        "/admin/permission-simulator/check-document",
        "/admin/permission-simulator/search",
        "/admin/permission-simulator/audit",
    ]
    for path in endpoints:
        resp = client.post(path, json={}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403, f"POST {path} should be 403 for non-admin"


# ── check-source ─────────────────────────────────────────────────────────


def test_check_source_admin_bypass(migrated_engine: Engine) -> None:
    client, token = _make_client_with_admin(migrated_engine)
    _ensure_source_with_group(migrated_engine)

    resp = client.post(
        "/admin/permission-simulator/check-source",
        json={
            "source_id": "00000000-0000-0000-0000-000000000000",
            "user_id": _ensure_users(migrated_engine)[0],
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "allow"
    assert data["reason_category"] == "admin_bypass"


def test_check_source_group_membership(migrated_engine: Engine) -> None:
    client, token = _make_client_with_admin(migrated_engine)
    source_id, _ = _ensure_source_with_group(migrated_engine, "analysts")
    user_id = _create_user_in_group(migrated_engine, "analyst@example.com", "analysts")

    resp = client.post(
        "/admin/permission-simulator/check-source",
        json={"source_id": source_id, "user_id": user_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "allow"
    assert data["reason_category"] == "group_membership"


def test_check_source_no_match(migrated_engine: Engine) -> None:
    client, token = _make_client_with_admin(migrated_engine)
    source_id, _ = _ensure_source_with_group(migrated_engine, "analysts")
    user_id = _create_user_in_group(migrated_engine, "outsider@example.com", "other-group")

    resp = client.post(
        "/admin/permission-simulator/check-source",
        json={"source_id": source_id, "user_id": user_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "deny"
    assert data["reason_category"] == "no_group_match"


def test_check_source_by_group_ids(migrated_engine: Engine) -> None:
    client, token = _make_client_with_admin(migrated_engine)
    source_id, group_id = _ensure_source_with_group(migrated_engine, "analysts")

    resp = client.post(
        "/admin/permission-simulator/check-source",
        json={"source_id": source_id, "group_ids": [group_id]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "allow"


def test_check_source_anonymous(migrated_engine: Engine) -> None:
    client, token = _make_client_with_admin(migrated_engine)
    source_id, _ = _ensure_source_with_group(migrated_engine)

    resp = client.post(
        "/admin/permission-simulator/check-source",
        json={"source_id": source_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "deny"


def test_check_source_no_source_permissions(migrated_engine: Engine) -> None:
    client, token = _make_client_with_admin(migrated_engine)
    with migrated_engine.begin() as connection:
        repo = AuthRepository(connection)
        source_id = repo.create_ingestion_source("Orphan Source")

    resp = client.post(
        "/admin/permission-simulator/check-source",
        json={"source_id": str(source_id), "user_id": _ensure_users(migrated_engine)[1]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "deny"
    assert data["reason_category"] == "no_source_permissions"


def test_check_source_missing_source_id(migrated_engine: Engine) -> None:
    client, token = _make_client_with_admin(migrated_engine)

    resp = client.post(
        "/admin/permission-simulator/check-source",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 422


# ── check-document ───────────────────────────────────────────────────────


def test_check_document_valid(migrated_engine: Engine) -> None:
    client, token = _make_client_with_admin(migrated_engine)
    source_id, _ = _ensure_source_with_group(migrated_engine, "analysts")
    user_id = _create_user_in_group(migrated_engine, "analyst@example.com", "analysts")
    doc_id = _create_doc_for_source(migrated_engine, source_id)

    resp = client.post(
        "/admin/permission-simulator/check-document",
        json={"document_id": doc_id, "user_id": user_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "allow"
    assert data["document_id"] == doc_id


def test_check_document_not_found(migrated_engine: Engine) -> None:
    client, token = _make_client_with_admin(migrated_engine)
    _ensure_users(migrated_engine)

    resp = client.post(
        "/admin/permission-simulator/check-document",
        json={"document_id": str(uuid4()), "user_id": _ensure_users(migrated_engine)[1]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "deny"
    assert data["reason_category"] == "document_not_found"


def test_check_document_missing_document_id(migrated_engine: Engine) -> None:
    client, token = _make_client_with_admin(migrated_engine)

    resp = client.post(
        "/admin/permission-simulator/check-document",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 422


def test_check_document_nested_group_inheritance(migrated_engine: Engine) -> None:
    """User in child group accesses document whose source is granted to parent group."""
    client, token = _make_client_with_admin(migrated_engine)

    # Create user OUTSIDE the transaction to avoid SQLite locking.
    user_id = _create_user_in_group(migrated_engine, "childuser@example.com", "child-g")

    with migrated_engine.begin() as connection:
        repo = AuthRepository(connection)
        parent_id = repo.ensure_group("parent-g")
        child_id = repo.ensure_group("child-g")
        connection.execute(
            sa.text(
                "INSERT INTO group_memberships (parent_group_id, child_group_id) VALUES (:p, :c)"
            ),
            {"p": parent_id.hex, "c": child_id.hex},
        )
        source_id = repo.create_ingestion_source("Nested Source")
        repo.grant_source_to_group(source_id, parent_id)
        doc_id = repo.create_document(source_id)

    resp = client.post(
        "/admin/permission-simulator/check-document",
        json={"document_id": str(doc_id), "user_id": user_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "allow"
    assert "parent-g" in str(data["effective_groups"])


# ── simulate-search ──────────────────────────────────────────────────────


def test_simulate_search_returns_filter_info(migrated_engine: Engine) -> None:
    client, token = _make_client_with_admin(migrated_engine)
    _ensure_source_with_group(migrated_engine, "analysts")
    user_id = _create_user_in_group(migrated_engine, "analyst@example.com", "analysts")

    resp = client.post(
        "/admin/permission-simulator/search",
        json={"query": "test query", "user_id": user_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "allowedGroupIds IN" in data["search_filter"]
    assert len(data["filter_explanation"]) > 0
    assert len(data["effective_group_names"]) > 0


def test_simulate_search_admin_empty_filter(migrated_engine: Engine) -> None:
    client, token = _make_client_with_admin(migrated_engine)

    resp = client.post(
        "/admin/permission-simulator/search",
        json={"query": "test", "user_id": _ensure_users(migrated_engine)[0]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["search_filter"] == ""
    assert data["is_admin"] is True


def test_simulate_search_missing_query(migrated_engine: Engine) -> None:
    client, token = _make_client_with_admin(migrated_engine)

    resp = client.post(
        "/admin/permission-simulator/search",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200


def test_simulate_search_with_filters(migrated_engine: Engine) -> None:
    client, token = _make_client_with_admin(migrated_engine)
    _ensure_users(migrated_engine)

    resp = client.post(
        "/admin/permission-simulator/search",
        json={
            "query": "test",
            "source_filter": ["folder"],
            "mime_type_filter": ["application/pdf"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "filter_explanation" in data


# ── audit ────────────────────────────────────────────────────────────────


def test_audit_source_and_document(migrated_engine: Engine) -> None:
    client, token = _make_client_with_admin(migrated_engine)
    source_id, _ = _ensure_source_with_group(migrated_engine, "analysts")
    user_id = _create_user_in_group(migrated_engine, "analyst@example.com", "analysts")
    doc_id = _create_doc_for_source(migrated_engine, source_id)

    resp = client.post(
        "/admin/permission-simulator/audit",
        json={"user_id": user_id, "source_id": source_id, "document_id": doc_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["simulated_user"]["email"] == "analyst@example.com"
    assert len(data["checks"]) == 2
    assert all(c["verdict"] == "allow" for c in data["checks"])


def test_audit_no_targets(migrated_engine: Engine) -> None:
    client, token = _make_client_with_admin(migrated_engine)
    _ensure_users(migrated_engine)

    resp = client.post(
        "/admin/permission-simulator/audit",
        json={"user_id": _ensure_users(migrated_engine)[1]},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 422
    detail = resp.json()["detail"].lower()
    assert "source_id" in detail or "document_id" in detail


def test_audit_source_only(migrated_engine: Engine) -> None:
    client, token = _make_client_with_admin(migrated_engine)
    source_id, _ = _ensure_source_with_group(migrated_engine, "analysts")
    user_id = _create_user_in_group(migrated_engine, "analyst@example.com", "analysts")

    resp = client.post(
        "/admin/permission-simulator/audit",
        json={"user_id": user_id, "source_id": source_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["checks"]) == 1
    assert data["checks"][0]["type"] == "source_access"


def test_audit_invalid_user(migrated_engine: Engine) -> None:
    client, token = _make_client_with_admin(migrated_engine)
    source_id, _ = _ensure_source_with_group(migrated_engine)

    resp = client.post(
        "/admin/permission-simulator/audit",
        json={"user_id": "bad-uuid", "source_id": source_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data.get("error") == "invalid_user"


def test_audit_reasoning_path_present(migrated_engine: Engine) -> None:
    """Verify that detailed reasoning is returned in audit results."""
    client, token = _make_client_with_admin(migrated_engine)
    source_id, _ = _ensure_source_with_group(migrated_engine, "analysts")
    user_id = _create_user_in_group(migrated_engine, "analyst@example.com", "analysts")

    resp = client.post(
        "/admin/permission-simulator/audit",
        json={"user_id": user_id, "source_id": source_id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    data = resp.json()
    check = data["checks"][0]
    assert len(check["reasoning_path"]) > 0
    assert len(check["effective_groups"]) > 0
    assert len(check["source_permission_groups"]) > 0
    assert len(check["matching_groups"]) > 0
