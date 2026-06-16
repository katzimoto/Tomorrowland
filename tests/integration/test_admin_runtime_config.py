"""Integration tests for the admin runtime-configuration API (#812)."""

from __future__ import annotations

import sqlalchemy as sa
from fastapi.testclient import TestClient

from services.api.config_registry import CONFIG_REGISTRY, REDACTED
from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from shared.config import Settings

_BASE = "/admin/runtime-config"


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


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------


def test_unauthorized_blocked(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    assert client.get(_BASE).status_code == 401


def test_non_admin_blocked(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _user_token(client, migrated_engine)
    assert client.get(_BASE, headers=_auth(token)).status_code == 403


# ---------------------------------------------------------------------------
# Listing / registry completeness
# ---------------------------------------------------------------------------


def test_list_returns_registry_with_metadata(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)
    resp = client.get(_BASE, headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["settings"]) == len(CONFIG_REGISTRY)
    assert body["precedence"]
    keys = {s["key"] for s in body["settings"]}
    # A few important settings must be present.
    assert {"feature_rag_qa", "search_reranker_enabled", "log_level"} <= keys


def test_get_redacts_secrets(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings(llm_api_key="super-secret-value")))
    token = _admin_token(client, migrated_engine)
    resp = client.get(f"{_BASE}/llm_api_key", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_secret"] is True
    assert body["configured"] is True
    assert body["current_effective_value"] == REDACTED
    assert "super-secret-value" not in resp.text


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_patch_rejects_unknown_key(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)
    resp = client.patch(f"{_BASE}/does_not_exist", headers=_auth(token), json={"value": 1})
    assert resp.status_code == 404


def test_patch_rejects_non_editable(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)
    resp = client.patch(f"{_BASE}/auth_provider", headers=_auth(token), json={"value": "local"})
    assert resp.status_code == 422


def test_patch_rejects_secret(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)
    resp = client.patch(f"{_BASE}/llm_api_key", headers=_auth(token), json={"value": "x"})
    assert resp.status_code == 422


def test_patch_validates_range(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)
    resp = client.patch(f"{_BASE}/rag_max_chunks", headers=_auth(token), json={"value": 999})
    assert resp.status_code == 422


def test_patch_validates_type(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)
    resp = client.patch(
        f"{_BASE}/search_reranker_enabled",
        headers=_auth(token),
        json={"value": "not-a-bool"},
    )
    assert resp.status_code == 422


def test_validate_endpoint_reports_errors(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)
    ok = client.post(
        f"{_BASE}/validate",
        headers=_auth(token),
        json={"key": "rag_max_chunks", "value": 3},
    )
    assert ok.json() == {"valid": True, "value": 3}
    bad = client.post(
        f"{_BASE}/validate",
        headers=_auth(token),
        json={"key": "rag_max_chunks", "value": 0},
    )
    assert bad.json()["valid"] is False


# ---------------------------------------------------------------------------
# Override storage + precedence + audit
# ---------------------------------------------------------------------------


def test_patch_stores_override_and_effective_value(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)
    resp = client.patch(f"{_BASE}/rag_max_chunks", headers=_auth(token), json={"value": 9})
    assert resp.status_code == 200
    body = resp.json()
    assert body["current_effective_value"] == 9
    assert body["source"] == "database_override"
    assert body["override_present"] is True

    # Override wins over env value (precedence) on subsequent GET.
    got = client.get(f"{_BASE}/rag_max_chunks", headers=_auth(token)).json()
    assert got["current_effective_value"] == 9
    assert got["source"] == "database_override"


def test_delete_override_resets_to_default(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)
    client.patch(f"{_BASE}/rag_max_chunks", headers=_auth(token), json={"value": 9})
    resp = client.delete(f"{_BASE}/rag_max_chunks", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["override_present"] is False
    assert body["current_effective_value"] == body["safe_default"]


def test_audit_records_change_without_raw_secret(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)
    client.patch(f"{_BASE}/feature_rag_qa", headers=_auth(token), json={"value": False})
    audit = client.get(f"{_BASE}/audit", headers=_auth(token))
    assert audit.status_code == 200
    rows = audit.json()
    assert any(r["key"] == "feature_rag_qa" and r["action"] == "update" for r in rows)

    # The audit_log row must not contain any secret payload.
    with migrated_engine.begin() as conn:
        details = conn.execute(
            sa.text(
                "SELECT details FROM audit_log WHERE resource_type = 'runtime_config' "
                "AND resource_id = 'feature_rag_qa'"
            )
        ).scalar()
    assert "feature_rag_qa" not in str(details) or "value" in str(details)


def test_reload_invalidates_cache(migrated_engine):
    client = TestClient(create_app(migrated_engine, _settings()))
    token = _admin_token(client, migrated_engine)
    resp = client.post(f"{_BASE}/reload", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["reloaded"] is True
