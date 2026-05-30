"""Integration tests for the SourceProfiles admin API."""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from shared.config import Settings
from shared.db import db_uuid, to_uuid

# Default test strategy values
_DOMAIN = "generic"
_CHUNKING = "paragraph"
_RETRIEVAL = "hybrid"
_EXTRACTION = "full_text"


def _settings(**overrides):
    return Settings(
        feature_meilisearch_search=False,
        feature_meilisearch_shadow_index=False,
        rabbitmq_enabled=False,
        **overrides,
    )


def _admin_token(client: TestClient, engine) -> str:
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


def _user_token(client: TestClient, engine) -> str:
    with engine.begin() as conn:
        AuthRepository(conn).create_local_user(
            email="user@example.com",
            password_hash=hash_password("secret"),
            display_name="User",
            is_admin=False,
            group_names=["users"],
        )
    login = client.post("/auth/login", json={"email": "user@example.com", "password": "secret"})
    assert login.status_code == 200
    return login.json()["access_token"]


def _create_source(conn: sa.Connection, source_id: str) -> None:
    conn.execute(
        sa.text("""
            INSERT INTO ingestion_sources (id, name, type, path, enabled, created_at, updated_at)
            VALUES (:id, :name, :type, :path, :enabled, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """),
        {
            "id": source_id,
            "name": "Test Source",
            "type": "folder",
            "path": "/tmp/test",
            "enabled": True,
        },
    )


def _create_provider(conn: sa.Connection, provider_id: str) -> None:
    conn.execute(
        sa.text("""
            INSERT INTO model_providers
                (id, name, provider_type, locality, enabled, created_at, updated_at)
            VALUES (:id, :name, :provider_type, :locality, :enabled, :created_at, :updated_at)
        """),
        {
            "id": provider_id,
            "name": "Test Provider",
            "provider_type": "ollama",
            "locality": "local",
            "enabled": True,
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        },
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_unauthorized_blocked(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    resp = client.get("/admin/source-profiles")
    assert resp.status_code == 401


def test_non_admin_blocked(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _user_token(client, migrated_engine)
    resp = client.get(
        "/admin/source-profiles",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_profile(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)

    source_id = db_uuid(uuid4())
    with migrated_engine.begin() as conn:
        _create_source(conn, source_id)

    resp = client.post(
        "/admin/source-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "source_id": source_id,
            "name": "Test Profile",
            "domain_type": _DOMAIN,
            "chunking_strategy": _CHUNKING,
            "retrieval_strategy": _RETRIEVAL,
            "extraction_strategy": _EXTRACTION,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Profile"
    assert data["status"] == "draft"
    assert to_uuid(data["source_id"]) == to_uuid(source_id)


def test_create_profile_404_for_unknown_source(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)

    resp = client.post(
        "/admin/source-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "source_id": uuid4().hex,
            "name": "Test Profile",
            "domain_type": _DOMAIN,
            "chunking_strategy": _CHUNKING,
            "retrieval_strategy": _RETRIEVAL,
            "extraction_strategy": _EXTRACTION,
        },
    )
    assert resp.status_code == 404
    assert "Source not found" in resp.json()["detail"]


def test_create_profile_invalid_enum_rejected(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)

    source_id = db_uuid(uuid4())
    with migrated_engine.begin() as conn:
        _create_source(conn, source_id)

    resp = client.post(
        "/admin/source-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "source_id": source_id,
            "name": "Bad Profile",
            "domain_type": "nonexistent_type",
            "chunking_strategy": _CHUNKING,
            "retrieval_strategy": _RETRIEVAL,
            "extraction_strategy": _EXTRACTION,
        },
    )
    assert resp.status_code == 422  # Pydantic validation error


def test_create_with_provider(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)

    source_id = db_uuid(uuid4())
    provider_id = db_uuid(uuid4())
    with migrated_engine.begin() as conn:
        _create_source(conn, source_id)
        _create_provider(conn, provider_id)

    resp = client.post(
        "/admin/source-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "source_id": source_id,
            "name": "With Provider",
            "domain_type": _DOMAIN,
            "chunking_strategy": _CHUNKING,
            "retrieval_strategy": _RETRIEVAL,
            "extraction_strategy": _EXTRACTION,
            "model_policy_provider_id": provider_id,
        },
    )
    assert resp.status_code == 201
    from uuid import UUID

    assert UUID(resp.json()["model_policy_provider_id"]) == UUID(provider_id)


def test_create_with_missing_provider_404(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)

    source_id = db_uuid(uuid4())
    with migrated_engine.begin() as conn:
        _create_source(conn, source_id)

    resp = client.post(
        "/admin/source-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "source_id": source_id,
            "name": "With Provider",
            "domain_type": _DOMAIN,
            "chunking_strategy": _CHUNKING,
            "retrieval_strategy": _RETRIEVAL,
            "extraction_strategy": _EXTRACTION,
            "model_policy_provider_id": db_uuid(uuid4()),
        },
    )
    assert resp.status_code == 404
    assert "Model policy provider not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def test_get_profile(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)

    source_id = db_uuid(uuid4())
    with migrated_engine.begin() as conn:
        _create_source(conn, source_id)

    create_resp = client.post(
        "/admin/source-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "source_id": source_id,
            "name": "Get Test",
            "domain_type": _DOMAIN,
            "chunking_strategy": _CHUNKING,
            "retrieval_strategy": _RETRIEVAL,
            "extraction_strategy": _EXTRACTION,
        },
    )
    profile_id = create_resp.json()["id"]

    resp = client.get(
        f"/admin/source-profiles/{profile_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Get Test"


def test_get_profile_404(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)

    resp = client.get(
        f"/admin/source-profiles/{uuid4().hex}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def test_list_profiles(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)

    source_id = db_uuid(uuid4())
    with migrated_engine.begin() as conn:
        _create_source(conn, source_id)

    client.post(
        "/admin/source-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "source_id": source_id,
            "name": "Profile 1",
            "domain_type": _DOMAIN,
            "chunking_strategy": _CHUNKING,
            "retrieval_strategy": _RETRIEVAL,
            "extraction_strategy": _EXTRACTION,
        },
    )
    client.post(
        "/admin/source-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "source_id": source_id,
            "name": "Profile 2",
            "domain_type": _DOMAIN,
            "chunking_strategy": _CHUNKING,
            "retrieval_strategy": _RETRIEVAL,
            "extraction_strategy": _EXTRACTION,
        },
    )

    resp = client.get(
        "/admin/source-profiles",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_profiles_filtered_by_source(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)

    source_id1 = db_uuid(uuid4())
    source_id2 = db_uuid(uuid4())
    with migrated_engine.begin() as conn:
        _create_source(conn, source_id1)
        _create_source(conn, source_id2)

    client.post(
        "/admin/source-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "source_id": source_id1,
            "name": "A",
            "domain_type": _DOMAIN,
            "chunking_strategy": _CHUNKING,
            "retrieval_strategy": _RETRIEVAL,
            "extraction_strategy": _EXTRACTION,
        },
    )
    client.post(
        "/admin/source-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "source_id": source_id2,
            "name": "B",
            "domain_type": _DOMAIN,
            "chunking_strategy": _CHUNKING,
            "retrieval_strategy": _RETRIEVAL,
            "extraction_strategy": _EXTRACTION,
        },
    )

    resp = client.get(
        f"/admin/source-profiles?source_id={source_id1}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# Update (PATCH)
# ---------------------------------------------------------------------------


def test_update_profile(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)

    source_id = db_uuid(uuid4())
    with migrated_engine.begin() as conn:
        _create_source(conn, source_id)

    create_resp = client.post(
        "/admin/source-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "source_id": source_id,
            "name": "Original",
            "domain_type": _DOMAIN,
            "chunking_strategy": _CHUNKING,
            "retrieval_strategy": _RETRIEVAL,
            "extraction_strategy": _EXTRACTION,
        },
    )
    profile_id = create_resp.json()["id"]

    resp = client.patch(
        f"/admin/source-profiles/{profile_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Updated"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated"


def test_update_profile_invalid_enum(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)

    source_id = db_uuid(uuid4())
    with migrated_engine.begin() as conn:
        _create_source(conn, source_id)

    create_resp = client.post(
        "/admin/source-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "source_id": source_id,
            "name": "Original",
            "domain_type": _DOMAIN,
            "chunking_strategy": _CHUNKING,
            "retrieval_strategy": _RETRIEVAL,
            "extraction_strategy": _EXTRACTION,
        },
    )
    profile_id = create_resp.json()["id"]

    resp = client.patch(
        f"/admin/source-profiles/{profile_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"domain_type": "invalid_type"},
    )
    assert resp.status_code == 422  # Pydantic validates the pattern


# ---------------------------------------------------------------------------
# Activate / Deprecate
# ---------------------------------------------------------------------------


def test_activate_profile(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)

    source_id = db_uuid(uuid4())
    with migrated_engine.begin() as conn:
        _create_source(conn, source_id)

    create_resp = client.post(
        "/admin/source-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "source_id": source_id,
            "name": "Activate Me",
            "domain_type": _DOMAIN,
            "chunking_strategy": _CHUNKING,
            "retrieval_strategy": _RETRIEVAL,
            "extraction_strategy": _EXTRACTION,
        },
    )
    profile_id = create_resp.json()["id"]

    resp = client.post(
        f"/admin/source-profiles/{profile_id}/activate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_activate_enforces_one_active(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)

    source_id = db_uuid(uuid4())
    with migrated_engine.begin() as conn:
        _create_source(conn, source_id)

    p1 = client.post(
        "/admin/source-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "source_id": source_id,
            "name": "First",
            "domain_type": _DOMAIN,
            "chunking_strategy": _CHUNKING,
            "retrieval_strategy": _RETRIEVAL,
            "extraction_strategy": _EXTRACTION,
        },
    ).json()
    p2 = client.post(
        "/admin/source-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "source_id": source_id,
            "name": "Second",
            "domain_type": _DOMAIN,
            "chunking_strategy": _CHUNKING,
            "retrieval_strategy": _RETRIEVAL,
            "extraction_strategy": _EXTRACTION,
        },
    ).json()

    # Activate first
    client.post(
        f"/admin/source-profiles/{p1['id']}/activate",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Activate second — should deprecate first
    resp = client.post(
        f"/admin/source-profiles/{p2['id']}/activate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"

    # First should be deprecated
    get_p1 = client.get(
        f"/admin/source-profiles/{p1['id']}",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert get_p1["status"] == "deprecated"


def test_deprecate_profile(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)

    source_id = db_uuid(uuid4())
    with migrated_engine.begin() as conn:
        _create_source(conn, source_id)

    create_resp = client.post(
        "/admin/source-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "source_id": source_id,
            "name": "To Deprecate",
            "domain_type": _DOMAIN,
            "chunking_strategy": _CHUNKING,
            "retrieval_strategy": _RETRIEVAL,
            "extraction_strategy": _EXTRACTION,
        },
    )
    profile_id = create_resp.json()["id"]

    client.post(
        f"/admin/source-profiles/{profile_id}/activate",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = client.post(
        f"/admin/source-profiles/{profile_id}/deprecate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "deprecated"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_profile(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)

    source_id = db_uuid(uuid4())
    with migrated_engine.begin() as conn:
        _create_source(conn, source_id)

    create_resp = client.post(
        "/admin/source-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "source_id": source_id,
            "name": "Delete Me",
            "domain_type": _DOMAIN,
            "chunking_strategy": _CHUNKING,
            "retrieval_strategy": _RETRIEVAL,
            "extraction_strategy": _EXTRACTION,
            "status": "draft",
        },
    )
    profile_id = create_resp.json()["id"]

    resp = client.delete(
        f"/admin/source-profiles/{profile_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # Verify deleted
    get_resp = client.get(
        f"/admin/source-profiles/{profile_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_resp.status_code == 404


def test_delete_active_rejected(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)

    source_id = db_uuid(uuid4())
    with migrated_engine.begin() as conn:
        _create_source(conn, source_id)

    create_resp = client.post(
        "/admin/source-profiles",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "source_id": source_id,
            "name": "Active Profile",
            "domain_type": _DOMAIN,
            "chunking_strategy": _CHUNKING,
            "retrieval_strategy": _RETRIEVAL,
            "extraction_strategy": _EXTRACTION,
        },
    )
    profile_id = create_resp.json()["id"]

    client.post(
        f"/admin/source-profiles/{profile_id}/activate",
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = client.delete(
        f"/admin/source-profiles/{profile_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert "Cannot delete an active profile" in resp.json()["detail"]
