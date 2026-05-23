"""Unit tests for GET /admin/rabbit/queues."""
from unittest.mock import patch
import json
from fastapi.testclient import TestClient
from services.api.main import create_app
from services.auth.passwords import hash_password
from services.auth.repository import AuthRepository
from shared.config import Settings
from sqlalchemy import Engine


def _settings(**overrides):
    return Settings(
        feature_meilisearch_search=False,
        feature_meilisearch_shadow_index=False,
        rabbitmq_enabled=True,
        **overrides,
    )


def _admin_token(client: TestClient, engine: Engine):
    with engine.begin() as conn:
        AuthRepository(conn).create_local_user(
            email="admin@example.com",
            password_hash=hash_password("secret"),
            display_name="Admin",
            is_admin=True,
            group_names=["admins"],
        )
    login = client.post(
        "/auth/login", json={"email": "admin@example.com", "password": "secret"}
    )
    assert login.status_code == 200
    return login.json()["access_token"]


def test_admin_rabbit_queues_returns_shape(migrated_engine):
    mock_queues = [
        {"name": "document.parse.requested", "messages_ready": 3, "messages_unacknowledged": 1, "consumers": 1},
        {"name": "document.parse.dead", "messages_ready": 1, "messages_unacknowledged": 0, "consumers": 0},
    ]
    with patch("services.api.routers.admin.rabbit._mgmt_get", return_value=mock_queues):
        client = TestClient(create_app(migrated_engine, _settings()))
        token = _admin_token(client, migrated_engine)
        resp = client.get("/admin/rabbit/queues", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "queues" in data
        assert len(data["queues"]) == 6
        parse_queue = next(q for q in data["queues"] if q["queue"] == "document.parse.requested")
        assert parse_queue["depth"] == 4
        assert parse_queue["consumers"] == 1
        assert parse_queue["dlq"] == "document.parse.dead"
        assert parse_queue["dlq_depth"] == 1
