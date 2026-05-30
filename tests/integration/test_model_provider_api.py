"""Integration tests for the admin model provider API."""

from __future__ import annotations

from uuid import uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.intelligence.model_provider_models import ModelProviderCreate
from services.intelligence.model_provider_repository import ModelProviderRepository
from shared.config import Settings
from shared.db import db_uuid


def _settings(**overrides):
    return Settings(
        feature_meilisearch_search=False,
        feature_meilisearch_shadow_index=False,
        credential_store_key="test-key",
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


def _seed_admins_group(engine: Engine) -> None:
    """Ensure the 'admins' group exists (migrated DB might not have it)."""
    with engine.begin() as conn:
        row = conn.execute(sa.text("SELECT id FROM groups WHERE name = 'admins'")).scalar()
        if row is None:
            from uuid import uuid4 as _u4

            conn.execute(
                sa.text("INSERT INTO groups (id, name) VALUES (:id, :name)"),
                {"id": db_uuid(_u4()), "name": "admins"},
            )
        row = conn.execute(sa.text("SELECT id FROM groups WHERE name = 'users'")).scalar()
        if row is None:
            from uuid import uuid4 as _u4

            conn.execute(
                sa.text("INSERT INTO groups (id, name) VALUES (:id, :name)"),
                {"id": db_uuid(_u4()), "name": "users"},
            )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine(migrated_engine: Engine) -> Engine:
    _seed_admins_group(migrated_engine)
    _setup_users(migrated_engine)
    return migrated_engine


# ---------------------------------------------------------------------------
# Provider CRUD
# ---------------------------------------------------------------------------


class TestProviderCRUD:
    def test_create_provider(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        resp = client.post(
            "/admin/model-providers",
            json={
                "name": "Test Ollama",
                "provider_type": "ollama",
                "base_url": "http://ollama:11434",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Ollama"
        assert data["provider_type"] == "ollama"
        assert data["locality"] == "local"
        assert data["credential_set"] is False
        assert "credential_value" not in data
        assert "api_key" not in data

    def test_create_provider_duplicate_name(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        client.post(
            "/admin/model-providers",
            json={"name": "Duplicate", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = client.post(
            "/admin/model-providers",
            json={"name": "Duplicate", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 409

    def test_get_provider(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        created = client.post(
            "/admin/model-providers",
            json={"name": "GetTest", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        resp = client.get(
            f"/admin/model-providers/{created['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "GetTest"

    def test_get_provider_not_found(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        resp = client.get(
            f"/admin/model-providers/{uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    def test_list_providers(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        client.post(
            "/admin/model-providers",
            json={"name": "A", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        )
        client.post(
            "/admin/model-providers",
            json={"name": "B", "provider_type": "openai-compatible"},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = client.get("/admin/model-providers", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_providers_enabled_only(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        client.post(
            "/admin/model-providers",
            json={"name": "Active", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        )
        client.post(
            "/admin/model-providers",
            json={"name": "Inactive", "provider_type": "ollama", "enabled": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = client.get(
            "/admin/model-providers?enabled_only=true",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["name"] == "Active"

    def test_update_provider(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        created = client.post(
            "/admin/model-providers",
            json={"name": "Orig", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        resp = client.put(
            f"/admin/model-providers/{created['id']}",
            json={"name": "Updated", "enabled": False},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"
        assert resp.json()["enabled"] is False

    def test_update_provider_not_found(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        resp = client.put(
            f"/admin/model-providers/{uuid4()}",
            json={"name": "Nope"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    def test_delete_provider(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        created = client.post(
            "/admin/model-providers",
            json={"name": "DeleteMe", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        resp = client.delete(
            f"/admin/model-providers/{created['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        get_resp = client.get(
            f"/admin/model-providers/{created['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_resp.status_code == 404

    def test_non_admin_cannot_manage_providers(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _user_token(client)
        resp = client.post(
            "/admin/model-providers",
            json={"name": "Hack", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Credential handling
# ---------------------------------------------------------------------------


class TestCredentialHandling:
    def test_credential_value_accepted_on_create(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        resp = client.post(
            "/admin/model-providers",
            json={
                "name": "WithCreds",
                "provider_type": "openai-compatible",
                "base_url": "https://api.openai.com",
                "credential_value": "sk-test123",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["credential_set"] is True
        assert data["api_key_ref"] is not None
        assert "credential_value" not in data
        assert "sk-test123" not in str(data)

    def test_credential_value_not_exposed_in_list(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        client.post(
            "/admin/model-providers",
            json={
                "name": "SecretProvider",
                "provider_type": "openai-compatible",
                "credential_value": "super-secret-key",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = client.get("/admin/model-providers", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["credential_set"] is True
        assert "super-secret-key" not in str(data)
        assert "credential_value" not in data[0]

    def test_update_credential(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        created = client.post(
            "/admin/model-providers",
            json={"name": "CredUpd", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        assert created["credential_set"] is False

        resp = client.put(
            f"/admin/model-providers/{created['id']}",
            json={"credential_value": "new-key"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["credential_set"] is True

    def test_clear_credential(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        created = client.post(
            "/admin/model-providers",
            json={
                "name": "CredClear",
                "provider_type": "ollama",
                "credential_value": "temp-key",
            },
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        assert created["credential_set"] is True

        resp = client.put(
            f"/admin/model-providers/{created['id']}",
            json={"credential_value": ""},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["credential_set"] is False


# ---------------------------------------------------------------------------
# SSRF validation
# ---------------------------------------------------------------------------


class TestSSRFValidation:
    def test_external_private_ip_rejected(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        resp = client.post(
            "/admin/model-providers",
            json={
                "name": "Evil",
                "provider_type": "openai-compatible",
                "base_url": "http://192.168.1.1:8000",
                "locality": "external",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422
        assert "private" in resp.json()["detail"].lower()

    def test_local_private_ip_allowed(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        resp = client.post(
            "/admin/model-providers",
            json={
                "name": "LocalOllama",
                "provider_type": "ollama",
                "base_url": "http://127.0.0.1:11434",
                "locality": "local",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        assert resp.json()["base_url"] == "http://127.0.0.1:11434"

    def test_invalid_locality_rejected(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        resp = client.post(
            "/admin/model-providers",
            json={
                "name": "BadLocality",
                "provider_type": "ollama",
                "locality": "public",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    def test_invalid_url_scheme_rejected(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        resp = client.post(
            "/admin/model-providers",
            json={
                "name": "BadScheme",
                "provider_type": "ollama",
                "base_url": "ftp://ollama:11434",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    def test_no_url_allowed(self, engine: Engine) -> None:
        """Providers without a base URL are valid (e.g. auto-discovery)."""
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        resp = client.post(
            "/admin/model-providers",
            json={"name": "NoUrl", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Descriptor CRUD
# ---------------------------------------------------------------------------


class TestDescriptorCRUD:
    def test_create_descriptor(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        prov = client.post(
            "/admin/model-providers",
            json={"name": "DescProv", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        resp = client.post(
            f"/admin/model-providers/{prov['id']}/descriptors",
            json={"model_name": "mistral", "context_window": 8192},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        assert resp.json()["model_name"] == "mistral"
        assert resp.json()["context_window"] == 8192

    def test_create_descriptor_for_missing_provider(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        resp = client.post(
            f"/admin/model-providers/{uuid4()}/descriptors",
            json={"model_name": "test"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    def test_create_duplicate_descriptor(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        prov = client.post(
            "/admin/model-providers",
            json={"name": "DupDesc", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        client.post(
            f"/admin/model-providers/{prov['id']}/descriptors",
            json={"model_name": "dup-model"},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = client.post(
            f"/admin/model-providers/{prov['id']}/descriptors",
            json={"model_name": "dup-model"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 409

    def test_get_descriptor(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        prov = client.post(
            "/admin/model-providers",
            json={"name": "GetDesc", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        created = client.post(
            f"/admin/model-providers/{prov['id']}/descriptors",
            json={"model_name": "llama3"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        resp = client.get(
            f"/admin/model-descriptors/{created['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["model_name"] == "llama3"

    def test_get_descriptor_not_found(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        resp = client.get(
            f"/admin/model-descriptors/{uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    def test_list_descriptors_by_provider(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        prov = client.post(
            "/admin/model-providers",
            json={"name": "ListDesc", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        client.post(
            f"/admin/model-providers/{prov['id']}/descriptors",
            json={"model_name": "m1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        client.post(
            f"/admin/model-providers/{prov['id']}/descriptors",
            json={"model_name": "m2"},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = client.get(
            f"/admin/model-providers/{prov['id']}/descriptors",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_update_descriptor(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        prov = client.post(
            "/admin/model-providers",
            json={"name": "UpdDesc", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        created = client.post(
            f"/admin/model-providers/{prov['id']}/descriptors",
            json={"model_name": "orig"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        resp = client.put(
            f"/admin/model-descriptors/{created['id']}",
            json={"display_name": "Updated"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Updated"

    def test_delete_descriptor(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        prov = client.post(
            "/admin/model-providers",
            json={"name": "DelDesc", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        created = client.post(
            f"/admin/model-providers/{prov['id']}/descriptors",
            json={"model_name": "delete-me"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        resp = client.delete(
            f"/admin/model-descriptors/{created['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        get_resp = client.get(
            f"/admin/model-descriptors/{created['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# Task Defaults
# ---------------------------------------------------------------------------


class TestTaskDefaults:
    def test_set_task_default(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        prov = client.post(
            "/admin/model-providers",
            json={"name": "TaskProv", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        resp = client.put(
            "/admin/model-task-defaults/chat",
            json={"task_type": "chat", "provider_id": prov["id"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["task_type"] == "chat"
        assert resp.json()["provider_id"] == prov["id"]

    def test_get_task_default(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        prov = client.post(
            "/admin/model-providers",
            json={"name": "GetTD", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        client.put(
            "/admin/model-task-defaults/summary",
            json={"task_type": "summary", "provider_id": prov["id"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = client.get(
            "/admin/model-task-defaults/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["task_type"] == "summary"

    def test_get_task_default_not_found(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        resp = client.get(
            "/admin/model-task-defaults/nonexistent",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    def test_list_task_defaults(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        prov = client.post(
            "/admin/model-providers",
            json={"name": "ListTD", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        client.put(
            "/admin/model-task-defaults/chat",
            json={"task_type": "chat", "provider_id": prov["id"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        client.put(
            "/admin/model-task-defaults/embedding",
            json={"task_type": "embedding", "provider_id": prov["id"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = client.get(
            "/admin/model-task-defaults",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_update_task_default(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        p1 = client.post(
            "/admin/model-providers",
            json={"name": "TD1", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        p2 = client.post(
            "/admin/model-providers",
            json={"name": "TD2", "provider_type": "openai-compatible"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        client.put(
            "/admin/model-task-defaults/chat",
            json={"task_type": "chat", "provider_id": p1["id"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = client.patch(
            "/admin/model-task-defaults/chat",
            json={"provider_id": p2["id"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["provider_id"] == p2["id"]

    def test_delete_task_default(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        prov = client.post(
            "/admin/model-providers",
            json={"name": "DelTD", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        client.put(
            "/admin/model-task-defaults/translate",
            json={"task_type": "translate", "provider_id": prov["id"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = client.delete(
            "/admin/model-task-defaults/translate",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        get_resp = client.get(
            "/admin/model-task-defaults/translate",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_resp.status_code == 404

    def test_set_task_default_for_missing_provider(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        resp = client.put(
            "/admin/model-task-defaults/chat",
            json={"task_type": "chat", "provider_id": str(uuid4())},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Provider health / test
# ---------------------------------------------------------------------------


class TestProviderHealth:
    def test_test_provider_no_url(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        prov = client.post(
            "/admin/model-providers",
            json={"name": "NoUrlProv", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        resp = client.post(
            f"/admin/model-providers/{prov['id']}/test",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["healthy"] is False
        assert resp.json()["error"] == "No base URL configured"

    def test_test_provider_not_found(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        resp = client.post(
            f"/admin/model-providers/{uuid4()}/test",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Discover models
# ---------------------------------------------------------------------------


class TestDiscoverModels:
    def test_discover_no_url(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        prov = client.post(
            "/admin/model-providers",
            json={"name": "NoUrlDisc", "provider_type": "ollama"},
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        resp = client.post(
            f"/admin/model-providers/{prov['id']}/discover",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422
        assert "no base url" in resp.json()["detail"].lower()

    def test_discover_not_found(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _admin_token(client)
        resp = client.post(
            f"/admin/model-providers/{uuid4()}/discover",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------


class TestAuthEnforcement:
    def test_unauthenticated_request_rejected(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        resp = client.get("/admin/model-providers")
        assert resp.status_code == 401

    def test_non_admin_user_rejected(self, engine: Engine) -> None:
        client = TestClient(create_app(engine, _settings()))
        token = _user_token(client)
        resp = client.get(
            "/admin/model-providers",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# No change to existing behavior
# ---------------------------------------------------------------------------


class TestNoExistingBehaviorChange:
    def test_existing_provider_repository_unaffected(self, engine: Engine) -> None:
        """Verify that the existing repository still works independently."""
        with engine.begin() as conn:
            repo = ModelProviderRepository(conn)
            p = repo.create_provider(ModelProviderCreate(name="Existing", provider_type="ollama"))
            assert p.name == "Existing"
            assert repo.get_provider(p.id) is not None
