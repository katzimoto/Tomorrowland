"""Integration tests for TaskDefaultResolver wiring and reload endpoint."""

from __future__ import annotations

import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from services.intelligence.model_provider_models import ModelProviderCreate, ModelTaskDefaultCreate
from services.intelligence.model_provider_repository import ModelProviderRepository
from shared.config import Settings
from shared.db import db_uuid


def _settings(**overrides: object) -> Settings:
    return Settings(
        feature_meilisearch_search=False,
        feature_meilisearch_shadow_index=False,
        credential_store_key="test-key",
        **overrides,
    )


def _setup_admin(engine: Engine) -> None:
    with engine.begin() as conn:
        repo = AuthRepository(conn)
        repo.create_local_user(
            email="admin@example.com",
            password_hash=hash_password("secret"),
            display_name="Admin",
            is_admin=True,
            group_names=["admins"],
        )
        row = conn.execute(sa.text("SELECT id FROM groups WHERE name = 'admins'")).scalar()
        if row is None:
            from uuid import uuid4

            conn.execute(
                sa.text("INSERT INTO groups (id, name) VALUES (:id, :name)"),
                {"id": db_uuid(uuid4()), "name": "admins"},
            )


def _admin_token(client: TestClient) -> str:
    resp = client.post("/auth/login", json={"email": "admin@example.com", "password": "secret"})
    assert resp.status_code == 200, f"login failed: {resp.text}"
    return str(resp.json()["access_token"])


# ---------------------------------------------------------------------------
# Zero-row backward compatibility
# ---------------------------------------------------------------------------


def test_resolver_state_with_empty_task_defaults(migrated_engine: Engine) -> None:
    """With no model_task_defaults rows, resolver is loaded and returns None for
    all task types — callers keep their existing env/Settings behaviour."""
    app = create_app(migrated_engine, _settings())
    resolver = app.state.task_default_resolver

    assert resolver.loaded is True
    assert resolver.resolve("chat") is None
    assert resolver.resolve("utility") is None
    assert resolver.resolve("reranking") is None
    assert resolver.build_llm_provider("chat") is None


# ---------------------------------------------------------------------------
# Reload endpoint
# ---------------------------------------------------------------------------


def test_reload_endpoint_refreshes_resolver(migrated_engine: Engine) -> None:
    """POST /admin/model-providers/reload rebuilds in-process resolver state;
    subsequent resolve() calls return the newly configured default."""
    _setup_admin(migrated_engine)
    app = create_app(migrated_engine, _settings())
    client = TestClient(app)

    resolver = app.state.task_default_resolver
    assert resolver.resolve("chat") is None

    # Insert a provider + task default directly into the DB
    with migrated_engine.begin() as conn:
        repo = ModelProviderRepository(conn)
        prov = repo.create_provider(
            ModelProviderCreate(
                name="TestOllama",
                provider_type="ollama",
                base_url="http://ollama:11434",
                enabled=True,
            )
        )
        repo.set_task_default(ModelTaskDefaultCreate(task_type="chat", provider_id=prov.id))

    # Resolver not yet reloaded — still sees the old empty state
    assert resolver.resolve("chat") is None

    # Reload via the admin endpoint
    token = _admin_token(client)
    resp = client.post(
        "/admin/model-providers/reload",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"reloaded": True}

    # Resolver now reflects the new row
    res = resolver.resolve("chat")
    assert res is not None
    assert res.provider_name == "TestOllama"
    assert res.provider_type == "ollama"
